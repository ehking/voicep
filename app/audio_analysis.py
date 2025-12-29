import importlib.util
import math
from dataclasses import dataclass
from typing import Iterable, List

import numpy as np
import soundfile as sf
from loguru import logger


@dataclass
class AnalysisResult:
    duration_sec: float
    speech_ratio: float
    music_prob: float
    snr_estimate: float
    type: str

    def to_dict(self) -> dict:
        return {
            "duration_sec": float(self.duration_sec),
            "speech_ratio": float(self.speech_ratio),
            "music_prob": float(self.music_prob),
            "snr_estimate": float(self.snr_estimate),
            "type": self.type,
        }


def _frame_audio(data: np.ndarray, sr: int, frame_ms: int = 30, hop_ms: int = 15) -> Iterable[np.ndarray]:
    frame_len = int(sr * frame_ms / 1000)
    hop_len = int(sr * hop_ms / 1000)
    for start in range(0, len(data) - frame_len + 1, hop_len):
        yield data[start : start + frame_len]


def _speech_ratio_vad(data: np.ndarray, sr: int) -> float:
    try:
        if importlib.util.find_spec("webrtcvad") is None:
            raise ImportError
        import webrtcvad

        vad = webrtcvad.Vad(2)
        frame_duration_ms = 30
        frame_len = int(sr * frame_duration_ms / 1000)
        if sr != 16000:
            # Resample to 16k for VAD consistency
            import scipy.signal as signal

            data_resampled = signal.resample(data, int(len(data) * 16000 / sr))
            sr = 16000
            data = data_resampled.astype(np.float32)
        speech_frames = 0
        total_frames = 0
        for frame in _frame_audio(data, sr, frame_duration_ms, frame_duration_ms):
            total_frames += 1
            int16 = np.clip(frame * 32768, -32768, 32767).astype(np.int16)
            pcm_bytes = int16.tobytes()
            if vad.is_speech(pcm_bytes, sr):
                speech_frames += 1
        if total_frames == 0:
            return 0.0
        return speech_frames / total_frames
    except Exception as exc:  # pragma: no cover - fallback path
        logger.debug(f"webrtcvad unavailable or failed ({exc}), using energy VAD fallback")
        return _speech_ratio_energy(data, sr)


def _speech_ratio_energy(data: np.ndarray, sr: int) -> float:
    energies = []
    for frame in _frame_audio(data, sr):
        if len(frame) == 0:
            continue
        energies.append(float(np.mean(frame**2)))
    if not energies:
        return 0.0
    energies = np.array(energies)
    threshold = np.median(energies) * 1.5
    speech_frames = (energies > threshold).sum()
    return float(speech_frames / len(energies))


def _spectral_features(frames: Iterable[np.ndarray], sr: int) -> tuple[float, float, float]:
    flatness_values: List[float] = []
    centroid_values: List[float] = []
    harmonic_ratios: List[float] = []
    eps = 1e-10
    for frame in frames:
        if not len(frame):
            continue
        spectrum = np.fft.rfft(frame * np.hamming(len(frame)))
        power = np.abs(spectrum) ** 2
        if power.sum() == 0:
            continue
        geo_mean = np.exp(np.mean(np.log(power + eps)))
        arith_mean = np.mean(power + eps)
        flatness = float(geo_mean / arith_mean)
        freqs = np.fft.rfftfreq(len(frame), d=1.0 / sr)
        centroid = float(np.sum(freqs * power) / (power.sum() + eps))
        sorted_power = np.sort(power)
        if len(sorted_power) >= 3:
            top_energy = sorted_power[-3:].sum()
            rest_energy = max(sorted_power[:-3].sum(), eps)
            harmonic_ratio = float(top_energy / (rest_energy + top_energy))
        else:
            harmonic_ratio = 0.0
        flatness_values.append(flatness)
        centroid_values.append(centroid)
        harmonic_ratios.append(harmonic_ratio)
    if not flatness_values:
        return 0.0, 0.0, 0.0
    flatness_mean = float(np.mean(flatness_values))
    centroid_var = float(np.var(centroid_values))
    harmonicity = float(np.mean(harmonic_ratios))
    return flatness_mean, centroid_var, harmonicity


def _music_probability(data: np.ndarray, sr: int, speech_ratio: float) -> float:
    frames = list(_frame_audio(data, sr, frame_ms=46, hop_ms=23))
    flatness_mean, centroid_var, harmonicity = _spectral_features(frames, sr)
    flatness_score = min(max(flatness_mean * 1.2, 0.0), 1.0)
    centroid_score = min(centroid_var / (sr * 10), 1.0)
    harmonic_score = min(harmonicity * 1.1, 1.0)
    base_music = (0.45 * flatness_score) + (0.25 * centroid_score) + (0.3 * harmonic_score)
    speech_penalty = (1.0 - speech_ratio) * 0.5
    music_prob = min(max((base_music * 0.5) + speech_penalty, 0.0), 1.0)
    return float(music_prob)


def _estimate_snr(data: np.ndarray, sr: int, speech_ratio: float) -> float:
    energies = []
    for frame in _frame_audio(data, sr):
        if len(frame) == 0:
            continue
        energies.append(float(np.mean(frame**2)))
    if not energies:
        return 0.0
    energies = np.array(energies)
    noise_floor = np.percentile(energies, 10)
    signal_level = np.percentile(energies, 90)
    if speech_ratio > 0.05:
        speech_frames = energies[energies > noise_floor * 1.5]
        if len(speech_frames):
            signal_level = max(signal_level, float(np.mean(speech_frames)))
    snr = 10 * math.log10((signal_level + 1e-9) / (noise_floor + 1e-9))
    return float(max(snr, 0.0))


def _classify_type(speech_ratio: float, music_prob: float) -> str:
    if music_prob >= 0.70 and speech_ratio < 0.12:
        return "music"
    if music_prob >= 0.45 and 0.12 <= speech_ratio <= 0.60:
        return "mixed"
    return "speech"


def analyze_audio(wav_path: str) -> dict:
    data, sr = sf.read(wav_path)
    if data.ndim > 1:
        data = data.mean(axis=1)
    if sr <= 0 or len(data) == 0:
        raise ValueError("invalid audio")
    duration_sec = len(data) / sr
    speech_ratio = _speech_ratio_vad(data.astype(np.float32), sr)
    music_prob = _music_probability(data, sr, speech_ratio)
    snr_estimate = _estimate_snr(data, sr, speech_ratio)
    audio_type = _classify_type(speech_ratio, music_prob)
    result = AnalysisResult(
        duration_sec=duration_sec,
        speech_ratio=speech_ratio,
        music_prob=music_prob,
        snr_estimate=snr_estimate,
        type=audio_type,
    )
    logger.info(
        "Audio analysis: duration={:.2f}s speech_ratio={:.3f} music_prob={:.3f} snr={:.2f} type={}".format(
            duration_sec, speech_ratio, music_prob, snr_estimate, audio_type
        )
    )
    return result.to_dict()


__all__ = ["analyze_audio"]

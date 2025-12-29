import importlib.util
import os
import shutil
import subprocess
from pathlib import Path

import numpy as np
import soundfile as sf
from loguru import logger
from scipy.signal import butter, filtfilt

from .settings import settings

FFMPEG = shutil.which("ffmpeg") or "ffmpeg"
FFPROBE = shutil.which("ffprobe") or "ffprobe"


class AudioError(Exception):
    pass


def convert_to_wav_16k_mono(input_path: str, output_path: str):
    cmd = [
        FFMPEG,
        "-y",
        "-i",
        input_path,
        "-ac",
        "1",
        "-ar",
        "16000",
        "-f",
        "wav",
        output_path,
    ]
    logger.info(f"Converting to wav: {' '.join(cmd)}")
    result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if result.returncode != 0:
        raise AudioError(f"ffmpeg conversion failed: {result.stderr.decode(errors='ignore')}")


def probe_duration(path: str) -> float:
    cmd = [
        FFPROBE,
        "-v",
        "error",
        "-show_entries",
        "format=duration",
        "-of",
        "default=noprint_wrappers=1:nokey=1",
        path,
    ]
    result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if result.returncode != 0:
        raise AudioError(f"ffprobe failed: {result.stderr.decode(errors='ignore')}")
    try:
        return float(result.stdout.decode().strip())
    except ValueError as exc:
        raise AudioError("unable to parse duration") from exc


def _rnnoise_available() -> str | None:
    for candidate in ["rnnoise", "rnnoise-demo", "rnnoise-nu"]:
        path = shutil.which(candidate)
        if path:
            return path
    return None


def denoise_wav(input_wav: str, output_wav: str):
    os.makedirs(Path(output_wav).parent, exist_ok=True)
    rnnoise_path = _rnnoise_available()
    if rnnoise_path:
        logger.info("Using RNNoise for denoising")
        cmd = [rnnoise_path, input_wav, output_wav]
        result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        if result.returncode == 0:
            return
        logger.warning("RNNoise failed, falling back to spectral gating")
    logger.info("Using noisereduce fallback")
    if importlib.util.find_spec("noisereduce") is None:
        raise AudioError("noisereduce not available")
    import noisereduce as nr

    data, sr = sf.read(input_wav)
    if data.ndim > 1:
        data = data.mean(axis=1)
    reduced = nr.reduce_noise(y=data, sr=sr)
    sf.write(output_wav, reduced, sr)


def _bandpass_filter(data: np.ndarray, sr: int, low: float = 85.0, high: float = 4000.0) -> np.ndarray:
    nyquist = 0.5 * sr
    low_norm = max(low / nyquist, 0.001)
    high_norm = min(high / nyquist, 0.99)
    b, a = butter(4, [low_norm, high_norm], btype="band")
    return filtfilt(b, a, data)


def _soft_compress(signal: np.ndarray, drive: float = 1.5) -> np.ndarray:
    return np.tanh(signal * drive)


def suppress_music(input_wav: str, output_wav: str):
    os.makedirs(Path(output_wav).parent, exist_ok=True)
    demucs_path = shutil.which("demucs") if settings.DEMUCS_ENABLED else None
    if demucs_path:
        try:
            tmp_dir = Path(output_wav).parent / "demucs"
            tmp_dir.mkdir(parents=True, exist_ok=True)
            cmd = [
                demucs_path,
                "--two-stems",
                "vocals",
                "-o",
                str(tmp_dir),
                input_wav,
            ]
            logger.info(f"Running demucs for music suppression: {' '.join(cmd)}")
            result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            if result.returncode == 0:
                # demucs creates subfolders: <tmp_dir>/htdemucs/<filename>/vocals.wav
                vocals = next(tmp_dir.rglob("vocals.wav"), None)
                if vocals and vocals.exists():
                    shutil.move(str(vocals), output_wav)
                    logger.info("Demucs vocals track extracted")
                    return
            logger.warning("Demucs failed or vocals missing, falling back to band-pass")
        except Exception as exc:  # pragma: no cover - best effort
            logger.warning(f"Demucs suppression failed: {exc}")
    # Fallback: band-pass filter + gentle compression + denoise
    data, sr = sf.read(input_wav)
    if data.ndim > 1:
        data = data.mean(axis=1)
    filtered = _bandpass_filter(data, sr)
    compressed = _soft_compress(filtered)
    sf.write(output_wav, compressed, sr)
    try:
        temp_path = str(Path(output_wav).with_suffix(".denoised.wav"))
        denoise_wav(output_wav, temp_path)
        shutil.move(temp_path, output_wav)
    except Exception as exc:  # pragma: no cover
        logger.warning(f"Denoise after suppression failed: {exc}")


convert_to_wav = convert_to_wav_16k_mono

__all__ = [
    "convert_to_wav_16k_mono",
    "convert_to_wav",
    "probe_duration",
    "denoise_wav",
    "suppress_music",
    "AudioError",
]

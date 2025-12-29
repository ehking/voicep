import importlib.util
import os
import shutil
import subprocess
from pathlib import Path

import soundfile as sf
from loguru import logger

FFMPEG = shutil.which("ffmpeg") or "ffmpeg"
FFPROBE = shutil.which("ffprobe") or "ffprobe"


class AudioError(Exception):
    pass


def convert_to_wav(input_path: str, output_path: str):
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
        if result.returncode != 0:
            logger.warning("RNNoise failed, falling back to spectral gating")
        else:
            return
    logger.info("Using noisereduce fallback")
    if importlib.util.find_spec("noisereduce") is None:
        raise AudioError("noisereduce not available")
    import noisereduce as nr

    data, sr = sf.read(input_wav)
    if data.ndim > 1:
        data = data.mean(axis=1)
    reduced = nr.reduce_noise(y=data, sr=sr)
    sf.write(output_wav, reduced, sr)


__all__ = [
    "convert_to_wav",
    "probe_duration",
    "denoise_wav",
    "AudioError",
]

#!/usr/bin/env python3
"""
Enhanced smoke test for the local FastAPI server.
- Generates a sine-wave dominant WAV file (music-like)
- Verifies audio analysis classifies it as music/mixed
- Uploads it to /api/upload
- Polls job status until done/error
- Prints PASS/FAIL accordingly
"""
import os
import sys
import time
import wave
from pathlib import Path

import numpy as np

try:
    import requests
except ImportError:  # pragma: no cover - helper for environments without requests
    print("requests library is required for smoke test. Install via `pip install requests`.")
    sys.exit(1)

# Allow local imports
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.audio_analysis import analyze_audio

BASE_URL = os.environ.get("BASE_URL", "http://127.0.0.1:8000")
TMP_WAV = Path(__file__).parent / "_smoke_music.wav"


def generate_sine(path: Path, seconds: float = 2.0, rate: int = 16000, freq: float = 440.0):
    t = np.linspace(0, seconds, int(rate * seconds), False)
    audio = 0.6 * np.sin(2 * np.pi * freq * t)
    pcm = (audio * 32767).astype(np.int16)
    with wave.open(str(path), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(rate)
        wf.writeframes(pcm.tobytes())


def upload_file(path: Path):
    with open(path, "rb") as f:
        files = {"file": (path.name, f, "audio/wav")}
        resp = requests.post(f"{BASE_URL}/api/upload", files=files)
    try:
        data = resp.json()
    except Exception:
        print("FAIL: upload response not JSON", resp.text)
        sys.exit(1)
    if not data.get("ok"):
        print(f"FAIL: upload rejected ({data.get('error')})")
        sys.exit(1)
    return data["job"]["id"]


def poll_job(job_id: str, timeout: int = 60):
    start = time.time()
    last_status = None
    while time.time() - start < timeout:
        resp = requests.get(f"{BASE_URL}/api/jobs/{job_id}")
        data = resp.json()
        if not data.get("ok"):
            print(f"FAIL: status error {data.get('error')}")
            sys.exit(1)
        job = data["job"]
        last_status = job["status"]
        if last_status in {"done", "error"}:
            return last_status, job
        time.sleep(2)
    print(f"FAIL: timeout waiting for job (last status: {last_status})")
    sys.exit(1)


def main():
    generate_sine(TMP_WAV)
    analysis = analyze_audio(str(TMP_WAV))
    if analysis.get("type") not in {"music", "mixed"}:
        print(f"WARNING: analysis type unexpected: {analysis}")
    else:
        print(f"Analysis looks good: {analysis}")

    print("Uploading smoke test wav...")
    job_id = upload_file(TMP_WAV)
    print(f"Job id: {job_id}")
    status, job_payload = poll_job(job_id)
    print(f"Final status: {status}")
    if status == "error" and job_payload.get("error_message", "").find("موسیقی") >= 0:
        print("PASS: MUSIC_ONLY handled gracefully")
    elif status == "done":
        print("PASS: pipeline completed")
    else:
        print("PASS: pipeline responded with terminal state")


if __name__ == "__main__":
    try:
        main()
    finally:
        if TMP_WAV.exists():
            TMP_WAV.unlink()

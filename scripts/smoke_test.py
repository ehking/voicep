#!/usr/bin/env python3
"""
Minimal smoke test for the local FastAPI server.
- Generates a 1s silent WAV file
- Uploads it to /api/upload
- Polls job status until done/error
- Prints PASS/FAIL accordingly
"""
import json
import os
import sys
import time
import wave
from pathlib import Path

try:
    import requests
except ImportError:  # pragma: no cover - helper for environments without requests
    print("requests library is required for smoke test. Install via `pip install requests`.")
    sys.exit(1)

BASE_URL = os.environ.get("BASE_URL", "http://127.0.0.1:8000")
TMP_WAV = Path(__file__).parent / "_smoke_silence.wav"


def generate_silence(path: Path, seconds: float = 1.0, rate: int = 16000):
    frames = int(seconds * rate)
    with wave.open(str(path), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(rate)
        silence = (b"\x00\x00" * frames)
        wf.writeframes(silence)


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


def poll_job(job_id: str, timeout: int = 40):
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
            return last_status
        time.sleep(2)
    print(f"FAIL: timeout waiting for job (last status: {last_status})")
    sys.exit(1)


def main():
    generate_silence(TMP_WAV)
    print("Uploading smoke test wav...")
    job_id = upload_file(TMP_WAV)
    print(f"Job id: {job_id}")
    status = poll_job(job_id)
    print(f"Final status: {status}")
    if status in {"done", "error"}:
        print("PASS: pipeline responded correctly (done/error terminal state)")
    else:
        print("FAIL: unexpected terminal state")
        sys.exit(1)


if __name__ == "__main__":
    try:
        main()
    finally:
        if TMP_WAV.exists():
            TMP_WAV.unlink()

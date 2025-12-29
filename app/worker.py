import threading
import time
from datetime import datetime, timezone
from queue import Empty, Full, Queue
from typing import Dict, Set, Tuple

from loguru import logger
from sqlalchemy.orm import Session

from . import audio, asr, text_clean
from .audio_analysis import analyze_audio
from .db import SessionLocal
from .models import Job
from .settings import settings
from .utils import delete_expired_jobs, ensure_storage_dirs

job_queue: Queue[str] = Queue(maxsize=settings.MAX_QUEUE_SIZE)
_queued_jobs: Set[str] = set()
_queue_lock = threading.Lock()
_job_locks: Dict[str, threading.Lock] = {}
_job_locks_lock = threading.Lock()


MUSIC_ONLY_MESSAGE = "فایل بیشتر شامل موسیقی است و گفتاری پیدا نشد. لطفاً فایل دیگری آپلود کنید."


def _get_job_lock(job_id: str) -> threading.Lock:
    with _job_locks_lock:
        if job_id not in _job_locks:
            _job_locks[job_id] = threading.Lock()
        return _job_locks[job_id]


def enqueue_job(job_id: str) -> bool:
    with _queue_lock:
        if job_id in _queued_jobs:
            return True
        try:
            job_queue.put_nowait(job_id)
        except Full:
            return False
        _queued_jobs.add(job_id)
        return True


def _update_job(session: Session, job: Job, **kwargs):
    for key, value in kwargs.items():
        setattr(job, key, value)
    job.updated_at = datetime.now(timezone.utc)
    session.add(job)
    session.commit()


def _select_profile(analysis: dict) -> Tuple[str, str]:
    speech_ratio = float(analysis.get("speech_ratio") or 0.0)
    music_prob = float(analysis.get("music_prob") or 0.0)
    snr_estimate = float(analysis.get("snr_estimate") or 0.0)
    if music_prob >= 0.70 and speech_ratio < 0.12:
        return "music", "music_mixed"
    if music_prob >= 0.45 and 0.12 <= speech_ratio <= 0.60:
        return "mixed", "music_mixed"
    if snr_estimate < 6:
        return "speech", "noisy"
    return "speech", "balanced"


def _persist_analysis(session: Session, job: Job, analysis: dict, audio_type: str, profile: str, progress: int | None = None):
    updates = {
        "duration_seconds": int(analysis.get("duration_sec") or 0),
        "speech_ratio": float(analysis.get("speech_ratio") or 0.0),
        "music_prob": float(analysis.get("music_prob") or 0.0),
        "snr_estimate": float(analysis.get("snr_estimate") or 0.0),
        "audio_type": audio_type,
        "asr_profile": profile,
    }
    if progress is not None:
        updates["progress"] = progress
    _update_job(session, job, **updates)


def _process_job(job_id: str):
    job_lock = _get_job_lock(job_id)
    if not job_lock.acquire(blocking=False):
        logger.info(f"Job {job_id} is already being processed; skipping duplicate queue entry")
        return
    session = SessionLocal()
    try:
        job = session.get(Job, job_id)
        if not job:
            logger.error(f"Job {job_id} not found")
            return
        _update_job(session, job, status="processing", progress=max(job.progress or 0, 10))

        base_dir = settings.STORAGE_DIR.rstrip("/")
        wav_path = f"{base_dir}/wav/{job_id}.wav"
        try:
            audio.convert_to_wav_16k_mono(job.file_path, wav_path)
            _update_job(session, job, wav_path=wav_path, progress=15)
        except Exception as exc:
            _update_job(session, job, status="error", error_message=f"تبدیل فایل ناموفق بود: {exc}")
            return

        try:
            analysis = analyze_audio(wav_path)
            audio_type, profile = _select_profile(analysis)
            if analysis.get("duration_sec", 0) > settings.MAX_SECONDS:
                _update_job(
                    session,
                    job,
                    status="error",
                    error_message="طول فایل بیشتر از ۵ دقیقه است",
                    progress=20,
                    duration_seconds=int(analysis.get("duration_sec") or 0),
                )
                return
            _persist_analysis(session, job, analysis, audio_type, profile, progress=25)
        except Exception as exc:
            _update_job(session, job, status="error", error_message=f"تحلیل صوت ناموفق بود: {exc}", progress=20)
            return

        current_wav = wav_path
        suppressed = False

        if audio_type == "music":
            suppressed_path = f"{base_dir}/processed/{job_id}_suppressed.wav"
            try:
                audio.suppress_music(current_wav, suppressed_path)
                current_wav = suppressed_path
                suppressed = True
                analysis = analyze_audio(current_wav)
                audio_type, profile = _select_profile(analysis)
                if float(analysis.get("speech_ratio") or 0.0) < 0.10:
                    _persist_analysis(session, job, analysis, "music", "music_mixed", progress=30)
                    _update_job(session, job, status="error", error_message=MUSIC_ONLY_MESSAGE, progress=35)
                    return
                _persist_analysis(session, job, analysis, audio_type, profile, progress=30)
            except Exception as exc:
                _update_job(session, job, status="error", error_message=f"کاهش موسیقی ناموفق بود: {exc}", progress=30)
                return

        if audio_type == "mixed" and not suppressed:
            suppressed_path = f"{base_dir}/processed/{job_id}_suppressed.wav"
            try:
                audio.suppress_music(current_wav, suppressed_path)
                current_wav = suppressed_path
                suppressed = True
            except Exception as exc:
                _update_job(session, job, status="error", error_message=f"کاهش موسیقی ناموفق بود: {exc}", progress=30)
                return

        denoised_path = f"{base_dir}/denoised/{job_id}.wav"
        try:
            audio.denoise_wav(current_wav, denoised_path)
            current_wav = denoised_path
            _update_job(session, job, progress=35, wav_path=denoised_path, audio_type=audio_type, asr_profile=profile)
        except Exception as exc:
            _update_job(session, job, status="error", error_message=f"حذف نویز ناموفق بود: {exc}", progress=35)
            return

        try:
            text = asr.transcribe(current_wav, profile)
            _update_job(session, job, progress=80, raw_text=text, audio_type=audio_type, asr_profile=profile)
        except Exception as exc:
            _update_job(session, job, status="error", error_message=f"تشخیص گفتار ناموفق بود: {exc}", progress=80)
            return

        try:
            cleaned = text_clean.clean_text(text)
            _update_job(session, job, progress=95, cleaned_text=cleaned)
        except Exception as exc:
            _update_job(session, job, status="error", error_message=f"پاکسازی متن ناموفق بود: {exc}", progress=95)
            return

        _update_job(session, job, status="done", progress=100)
    finally:
        session.close()
        job_lock.release()


def worker_loop():
    logger.info("Worker thread started")
    while True:
        try:
            job_id = job_queue.get(timeout=1)
        except Empty:
            continue
        with _queue_lock:
            _queued_jobs.discard(job_id)
        try:
            _process_job(job_id)
        except Exception as exc:  # pragma: no cover
            logger.exception(f"Unhandled worker error for {job_id}: {exc}")
        finally:
            job_queue.task_done()


def start_workers():
    ensure_storage_dirs()
    for _ in range(settings.WORKER_THREADS):
        t = threading.Thread(target=worker_loop, daemon=True)
        t.start()


def cleanup_loop():
    logger.info("Cleanup thread started")
    while True:
        time.sleep(3600)
        session = SessionLocal()
        try:
            delete_expired_jobs(session, settings.RETENTION_HOURS)
        except Exception as exc:  # pragma: no cover
            logger.error(f"Cleanup failed: {exc}")
        finally:
            session.close()


def start_cleanup():
    t = threading.Thread(target=cleanup_loop, daemon=True)
    t.start()

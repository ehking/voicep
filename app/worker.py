import threading
import time
from queue import Queue, Empty

from loguru import logger
from sqlalchemy.orm import Session

from . import audio, asr, text_clean
from .db import SessionLocal
from .models import Job
from .settings import settings
from .utils import delete_expired_jobs, ensure_storage_dirs

job_queue: Queue[str] = Queue()


def enqueue_job(job_id: str):
    job_queue.put(job_id)


def _update_job(session: Session, job: Job, **kwargs):
    for key, value in kwargs.items():
        setattr(job, key, value)
    session.add(job)
    session.commit()


def _process_job(job_id: str):
    session = SessionLocal()
    try:
        job = session.get(Job, job_id)
        if not job:
            logger.error(f"Job {job_id} not found")
            return
        _update_job(session, job, status="processing", progress=10)

        wav_path = f"{settings.STORAGE_DIR.rstrip('/')}/wav/{job_id}.wav"
        try:
            audio.convert_to_wav(job.file_path, wav_path)
            _update_job(session, job, wav_path=wav_path, progress=15)
        except Exception as exc:
            _update_job(session, job, status="error", error_message=f"تبدیل فایل ناموفق بود: {exc}")
            return

        try:
            duration = audio.probe_duration(wav_path)
            job.duration_seconds = int(duration)
            session.commit()
            if duration > settings.MAX_SECONDS:
                _update_job(session, job, status="error", error_message="طول فایل بیشتر از ۵ دقیقه است", progress=15)
                return
        except Exception as exc:
            _update_job(session, job, status="error", error_message=f"خواندن مدت زمان ناموفق بود: {exc}", progress=15)
            return

        denoised_path = f"{settings.STORAGE_DIR.rstrip('/')}/denoised/{job_id}.wav"
        try:
            audio.denoise_wav(wav_path, denoised_path)
            _update_job(session, job, progress=35, wav_path=denoised_path)
        except Exception as exc:
            _update_job(session, job, status="error", error_message=f"حذف نویز ناموفق بود: {exc}")
            return

        try:
            text = asr.transcribe(denoised_path)
            _update_job(session, job, progress=80, raw_text=text)
        except Exception as exc:
            _update_job(session, job, status="error", error_message=f"تشخیص گفتار ناموفق بود: {exc}")
            return

        try:
            cleaned = text_clean.clean(text)
            _update_job(session, job, progress=95, cleaned_text=cleaned)
        except Exception as exc:
            _update_job(session, job, status="error", error_message=f"پاکسازی متن ناموفق بود: {exc}")
            return

        _update_job(session, job, status="done", progress=100)
    finally:
        session.close()


def worker_loop():
    logger.info("Worker thread started")
    while True:
        try:
            job_id = job_queue.get(timeout=1)
        except Empty:
            continue
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

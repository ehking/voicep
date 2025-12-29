import os
import re
import uuid
from pathlib import Path

from loguru import logger

from .settings import settings


SAFE_CHARS = re.compile(r"[^\w\-\.آ-ی]+", re.UNICODE)


def ensure_storage_dirs():
    base = Path(settings.STORAGE_DIR)
    (base / "uploads").mkdir(parents=True, exist_ok=True)
    (base / "wav").mkdir(parents=True, exist_ok=True)
    (base / "denoised").mkdir(parents=True, exist_ok=True)
    (base / "results").mkdir(parents=True, exist_ok=True)


def safe_filename(name: str) -> str:
    name = SAFE_CHARS.sub("_", name)
    if not name:
        name = "file"
    return name[:150]


def generate_job_id() -> str:
    return uuid.uuid4().hex


def remove_file(path: str):
    try:
        if path and os.path.exists(path):
            os.remove(path)
    except Exception as exc:  # pragma: no cover - best effort cleanup
        logger.warning(f"Failed to remove file {path}: {exc}")


def reset_processing_jobs(session):
    from .models import Job

    jobs = session.query(Job).filter(Job.status == "processing").all()
    for job in jobs:
        job.status = "queued"
        job.progress = max(job.progress or 0, 5)
        job.error_message = None
    if jobs:
        session.commit()


def delete_expired_jobs(session, retention_hours: int):
    from datetime import datetime, timedelta, timezone
    from .models import Job

    threshold = datetime.now(timezone.utc) - timedelta(hours=retention_hours)
    old_jobs = session.query(Job).filter(Job.created_at < threshold).all()
    for job in old_jobs:
        for path in [job.file_path, job.wav_path]:
            remove_file(path)
        session.delete(job)
    if old_jobs:
        session.commit()

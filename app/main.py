from datetime import datetime, timezone
from pathlib import Path

from fastapi import Depends, FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import text
from sqlalchemy.orm import Session

from .db import Base, SessionLocal, engine
from .models import Job
from .settings import settings
from .utils import ensure_storage_dirs, generate_job_id, reset_processing_jobs, safe_filename
from .worker import enqueue_job, job_queue, start_cleanup, start_workers

app = FastAPI(title="مترجم ویس‌های شلوغ ایرانی")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def migrate_jobs_table():
    Base.metadata.create_all(bind=engine)
    with engine.begin() as conn:
        result = conn.execute(text("PRAGMA table_info(jobs);"))
        existing = {row[1] for row in result.fetchall()}
        columns = {
            "duration_seconds": "INTEGER",
            "audio_type": "TEXT",
            "music_prob": "REAL",
            "speech_ratio": "REAL",
            "snr_estimate": "REAL",
            "asr_profile": "TEXT",
        }
        for column, ddl in columns.items():
            if column not in existing:
                conn.execute(text(f"ALTER TABLE jobs ADD COLUMN {column} {ddl}"))


def startup_requeue():
    session = SessionLocal()
    try:
        reset_processing_jobs(session)
        queued = session.query(Job).filter(Job.status == "queued").all()
        for job in queued:
            if not enqueue_job(job.id):
                job.status = "error"
                job.error_message = "صف پردازش پر است"
                job.progress = job.progress or 0
        session.commit()
    finally:
        session.close()


migrate_jobs_table()
ensure_storage_dirs()


@app.on_event("startup")
def startup_event():
    ensure_storage_dirs()
    startup_requeue()
    start_workers()
    start_cleanup()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def error_response(code: str, message: str, status_code: int = 400):
    return JSONResponse(status_code=status_code, content={"ok": False, "error": {"code": code, "message": message}})


@app.post("/api/upload")
async def upload_file(file: UploadFile = File(...), db: Session = Depends(get_db)):
    if not file.filename:
        raise HTTPException(status_code=400, detail="فایل نامعتبر است")

    if job_queue.full():
        return error_response("QUEUE_FULL", "صف پردازش پر است، لطفاً بعداً تلاش کنید", status_code=429)

    safe_name = safe_filename(file.filename)
    job_id = generate_job_id()
    upload_dir = Path(settings.STORAGE_DIR) / "uploads"
    upload_dir.mkdir(parents=True, exist_ok=True)
    file_path = upload_dir / f"{job_id}_{safe_name}"

    max_bytes = settings.MAX_MB * 1024 * 1024
    size = 0
    with open(file_path, "wb") as f:
        while True:
            chunk = await file.read(1024 * 1024)
            if not chunk:
                break
            size += len(chunk)
            if size > max_bytes:
                f.close()
                file_path.unlink(missing_ok=True)
                return error_response("FILE_TOO_LARGE", "حجم فایل بیش از حد مجاز است", status_code=413)
            f.write(chunk)

    job = Job(
        id=job_id,
        original_filename=safe_name,
        file_path=str(file_path),
        status="queued",
        progress=5,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    db.add(job)
    db.commit()

    if not enqueue_job(job_id):
        job.status = "error"
        job.error_message = "صف پردازش پر است"
        job.progress = 0
        db.add(job)
        db.commit()
        file_path.unlink(missing_ok=True)
        return error_response("QUEUE_FULL", "صف پردازش پر است، لطفاً بعداً تلاش کنید", status_code=429)

    return {"ok": True, "job": job.to_dict()}


@app.get("/api/jobs/{job_id}")
def get_job(job_id: str, db: Session = Depends(get_db)):
    job = db.get(Job, job_id)
    if not job:
        return error_response("NOT_FOUND", "درخواست پیدا نشد", status_code=404)
    return {"ok": True, "job": job.to_dict()}


@app.get("/api/jobs/{job_id}/result")
def job_result(job_id: str, db: Session = Depends(get_db)):
    job = db.get(Job, job_id)
    if not job:
        return error_response("NOT_FOUND", "درخواست پیدا نشد", status_code=404)
    if job.status != "done":
        return error_response("NOT_READY", "پردازش هنوز کامل نشده است", status_code=409)
    return {"ok": True, "result": {"raw_text": job.raw_text or "", "cleaned_text": job.cleaned_text or ""}}


@app.get("/api/jobs/{job_id}/download")
def download_result(job_id: str, db: Session = Depends(get_db)):
    job = db.get(Job, job_id)
    if not job:
        return error_response("NOT_FOUND", "درخواست پیدا نشد", status_code=404)
    if job.status != "done":
        return error_response("NOT_READY", "پردازش هنوز کامل نشده است", status_code=409)
    filename = f"{job.original_filename}_cleaned.txt"
    return PlainTextResponse(job.cleaned_text or "", headers={"Content-Disposition": f"attachment; filename={filename}"})


@app.get("/api/history")
def history(limit: int = 10, db: Session = Depends(get_db)):
    limit = min(max(limit, 1), 20)
    jobs = db.query(Job).order_by(Job.created_at.desc()).limit(limit).all()
    return {"ok": True, "jobs": [j.to_dict() for j in jobs]}


@app.get("/")
def index():
    return FileResponse(Path(__file__).resolve().parent.parent / "web" / "index.html")


app.mount("/web", StaticFiles(directory=Path(__file__).resolve().parent.parent / "web"), name="web")

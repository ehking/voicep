from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, Float, Integer, String, Text

from .db import Base


class Job(Base):
    __tablename__ = "jobs"

    id = Column(String, primary_key=True, index=True)
    original_filename = Column(String, nullable=False)
    file_path = Column(String, nullable=False)
    wav_path = Column(String, nullable=True)
    status = Column(String, nullable=False, default="queued")
    progress = Column(Integer, nullable=False, default=0)
    error_message = Column(Text, nullable=True)
    raw_text = Column(Text, nullable=True)
    cleaned_text = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    duration_seconds = Column(Integer, nullable=True)
    audio_type = Column(String, nullable=True)
    music_prob = Column(Float, nullable=True)
    speech_ratio = Column(Float, nullable=True)
    snr_estimate = Column(Float, nullable=True)
    asr_profile = Column(String, nullable=True)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "status": self.status,
            "progress": self.progress,
            "error_message": self.error_message,
            "original_filename": self.original_filename,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
            "duration_seconds": self.duration_seconds,
            "audio_type": self.audio_type,
            "music_prob": float(self.music_prob) if self.music_prob is not None else None,
            "speech_ratio": float(self.speech_ratio) if self.speech_ratio is not None else None,
            "snr_estimate": float(self.snr_estimate) if self.snr_estimate is not None else None,
            "asr_profile": self.asr_profile,
        }

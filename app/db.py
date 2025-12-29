from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import create_engine, event
from sqlalchemy.orm import declarative_base, sessionmaker

from .settings import settings

storage_path = Path(settings.STORAGE_DIR)
storage_path.mkdir(parents=True, exist_ok=True)

engine = create_engine(f"sqlite:///{storage_path / 'app.sqlite'}", echo=False, future=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
Base = declarative_base()


@event.listens_for(SessionLocal, "before_flush")
def update_timestamps(session, flush_context, instances):  # pragma: no cover - small hook
    now = datetime.now(timezone.utc)
    for instance in session.new.union(session.dirty):
        if hasattr(instance, "updated_at"):
            instance.updated_at = now
        if hasattr(instance, "created_at") and getattr(instance, "created_at", None) is None:
            instance.created_at = now

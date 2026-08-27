"""Persistence operations for speech jobs."""
import uuid
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import SpeechJob, JobStatus


def create(
    db: Session,
    *,
    kind: str,
    engine: str,
    lang: str,
    input_hash: str,
    audio_path: str | None,
    params: dict | None = None,
    request_id: str | None = None,
    status: str = JobStatus.QUEUED,
) -> SpeechJob:
    job = SpeechJob(
        id=uuid.uuid4().hex,
        kind=kind,
        engine=engine,
        lang=lang,
        input_hash=input_hash,
        audio_path=audio_path,
        params=params or {},
        request_id=request_id,
        status=status,
    )
    db.add(job)
    db.commit()
    db.refresh(job)
    return job


def get(db: Session, job_id: str) -> SpeechJob | None:
    return db.get(SpeechJob, job_id)


def find_completed_by_hash(db: Session, input_hash: str) -> SpeechJob | None:
    stmt = (
        select(SpeechJob)
        .where(SpeechJob.input_hash == input_hash, SpeechJob.status == JobStatus.COMPLETED)
        .order_by(SpeechJob.completed_at.desc())
        .limit(1)
    )
    return db.execute(stmt).scalar_one_or_none()


def mark_processing(db: Session, job: SpeechJob) -> None:
    job.status = JobStatus.PROCESSING
    db.commit()


def mark_completed(db: Session, job: SpeechJob, result: dict) -> None:
    job.status = JobStatus.COMPLETED
    job.result = result
    job.error = None
    job.completed_at = datetime.now(timezone.utc)
    db.commit()


def mark_failed(db: Session, job: SpeechJob, error: str) -> None:
    job.status = JobStatus.FAILED
    job.error = error
    job.completed_at = datetime.now(timezone.utc)
    db.commit()


def find_orphans(db: Session) -> list[SpeechJob]:
    """Jobs left queued/processing (e.g. after a worker crash)."""
    stmt = select(SpeechJob).where(SpeechJob.status.in_(JobStatus.ACTIVE))
    return list(db.execute(stmt).scalars().all())

"""Shared STT processing used by both the synchronous route and the Celery worker.

Keeps a single source of truth for how a job's audio becomes a result, so the
sync endpoints and the async worker can never drift apart.
"""
from sqlalchemy.orm import Session

from app.db.models import SpeechJob, JobKind
from app.engines import create_stt_engine
from app.services import jobs as jobs_service, storage
from app.utils.audio import ms_to_timestamp


def build_result(stt, kind: str, audio: bytes, lang: str) -> dict:
    if kind == JobKind.TRANSCRIBE:
        channels = stt.transcribe(audio, lang=lang)
        for ch in channels:
            for utt in ch["utterances"]:
                utt["start"] = ms_to_timestamp(utt["start_ms"])
                utt["end"] = ms_to_timestamp(utt["end_ms"])
        return {"speakers": channels}
    text = stt.recognize(audio, lang=lang)
    return {"text": text}


def process(db: Session, job: SpeechJob, audio: bytes | None = None) -> dict:
    """Run the engine for a job, persisting state transitions. Returns the result.

    Raises on engine failure after marking the job failed.
    """
    if audio is None:
        audio = storage.load_audio(job.audio_path)

    jobs_service.mark_processing(db, job)
    stt = create_stt_engine(job.engine)
    try:
        result = build_result(stt, job.kind, audio, job.lang)
    except Exception as e:
        jobs_service.mark_failed(db, job, str(e))
        raise
    jobs_service.mark_completed(db, job, result)
    return result

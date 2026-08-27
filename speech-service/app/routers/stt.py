import logging

from fastapi import APIRouter, HTTPException, UploadFile, File, Form, Request, Depends
from sqlalchemy.orm import Session

from app.engines import create_stt_engine
from app.engines.base import EngineError
from app.db.database import get_db
from app.db.models import JobKind
from app.services import jobs as jobs_service, storage, dedup, stt_runner
from app.schemas.jobs import JobSubmitResponse
from app.utils.audio import to_pcm_wav, wav_duration
from app.core.config import settings

logger = logging.getLogger("speech_service.stt")

router = APIRouter()


def _decode(data: bytes) -> bytes:
    try:
        return to_pcm_wav(data)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Could not decode audio: {e}")


def _resolve_engine(engine: str | None):
    try:
        return create_stt_engine(engine)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


# --------------------------------------------------------------------------- #
# Synchronous endpoints — block until the engine returns. Best for short audio.
# --------------------------------------------------------------------------- #

@router.post("/recognize")
async def recognize(
    file: UploadFile = File(..., description="Audio file"),
    lang: str = Form("ru-RU", description="Language code, e.g. ru-RU or kk-KZ"),
    engine: str = Form(default=None, description="STT engine (default from config)"),
):
    audio = _decode(await file.read())
    stt = _resolve_engine(engine)
    duration = wav_duration(audio)
    try:
        result = stt_runner.build_result(stt, JobKind.RECOGNIZE, audio, lang)
    except EngineError as e:
        logger.error("STT recognize error [%s]: %s", stt.engine_type.value, e)
        raise HTTPException(status_code=502, detail=str(e))

    return {**result, "lang": lang, "engine": stt.engine_type.value,
            "duration_seconds": round(duration, 2)}


@router.post("/transcribe")
async def transcribe(
    file: UploadFile = File(..., description="Audio file"),
    lang: str = Form("ru-RU", description="Language code, e.g. ru-RU or kk-KZ"),
    engine: str = Form(default=None, description="STT engine (default from config)"),
):
    audio = _decode(await file.read())
    stt = _resolve_engine(engine)
    duration = wav_duration(audio)
    try:
        result = stt_runner.build_result(stt, JobKind.TRANSCRIBE, audio, lang)
    except EngineError as e:
        logger.error("STT transcribe error [%s]: %s", stt.engine_type.value, e)
        raise HTTPException(status_code=502, detail=str(e))

    return {**result, "lang": lang, "engine": stt.engine_type.value,
            "duration_seconds": round(duration, 2)}


# --------------------------------------------------------------------------- #
# Async endpoints — enqueue a job and return immediately. Best for long audio.
# --------------------------------------------------------------------------- #

def _submit(db: Session, request: Request, kind: str, audio: bytes,
            lang: str, engine: str | None) -> JobSubmitResponse:
    stt = _resolve_engine(engine)
    engine_value = stt.engine_type.value
    input_hash = dedup.stt_hash(kind, engine_value, lang, audio)

    if settings.DEDUP_ENABLED:
        existing = jobs_service.find_completed_by_hash(db, input_hash)
        if existing is not None:
            return JobSubmitResponse(
                job_id=existing.id, status=existing.status, kind=kind,
                engine=engine_value, lang=lang, cached=True,
            )

    path = storage.save_audio(audio)
    request_id = getattr(request.state, "request_id", None)
    job = jobs_service.create(
        db, kind=kind, engine=engine_value, lang=lang,
        input_hash=input_hash, audio_path=path, request_id=request_id,
    )

    from app.tasks.stt_tasks import run_stt_job
    run_stt_job.delay(job.id)

    return JobSubmitResponse(
        job_id=job.id, status=job.status, kind=kind,
        engine=engine_value, lang=lang, cached=False,
    )


@router.post("/recognize/async", status_code=202, response_model=JobSubmitResponse)
async def recognize_async(
    request: Request,
    file: UploadFile = File(...),
    lang: str = Form("ru-RU"),
    engine: str = Form(default=None),
    db: Session = Depends(get_db),
):
    audio = _decode(await file.read())
    return _submit(db, request, JobKind.RECOGNIZE, audio, lang, engine)


@router.post("/transcribe/async", status_code=202, response_model=JobSubmitResponse)
async def transcribe_async(
    request: Request,
    file: UploadFile = File(...),
    lang: str = Form("ru-RU"),
    engine: str = Form(default=None),
    db: Session = Depends(get_db),
):
    audio = _decode(await file.read())
    return _submit(db, request, JobKind.TRANSCRIBE, audio, lang, engine)

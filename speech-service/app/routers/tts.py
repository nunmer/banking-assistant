import logging

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import Response
from pydantic import BaseModel

from app.engines import create_tts_engine
from app.engines.base import EngineError
from app.core.config import settings
from app.services import dedup, cache

logger = logging.getLogger("speech_service.tts")

router = APIRouter()

MIME = {
    "WAV": "audio/wav",
    "MP3": "audio/mpeg",
    "OGG_OPUS": "audio/ogg",
}


class SynthesizeRequest(BaseModel):
    text: str
    voice: str = "marina"
    lang: str = "ru-RU"
    format: str = "WAV"
    # Slightly above Yandex's neutral 1.0 — full-rate TTS reads noticeably
    # slower than natural conversational speech.
    speed: float = 1.15


@router.get("/voices")
def list_voices(engine: str = Query(default=None)):
    try:
        tts = create_tts_engine(engine)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"voices": tts.list_voices(), "engine": tts.engine_type.value}


@router.post("/synthesize")
def synthesize(req: SynthesizeRequest, engine: str = Query(default=None)):
    if not req.text.strip():
        raise HTTPException(status_code=400, detail="text must not be empty")
    try:
        tts = create_tts_engine(engine)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    cache_key = dedup.tts_hash(req.text, req.voice, req.lang, req.format, req.speed)
    audio = cache.get_tts_audio(cache_key) if settings.DEDUP_ENABLED else None
    if audio is None:
        try:
            audio = tts.synthesize(
                req.text, voice=req.voice, lang=req.lang, fmt=req.format, speed=req.speed
            )
        except EngineError as e:
            logger.error("TTS synthesize error [%s]: %s", tts.engine_type.value, e)
            raise HTTPException(status_code=502, detail=str(e))
        if settings.DEDUP_ENABLED:
            cache.set_tts_audio(cache_key, audio)

    ext = req.format.lower().replace("_opus", "")
    return Response(
        content=audio,
        media_type=MIME.get(req.format, "application/octet-stream"),
        headers={"Content-Disposition": f"attachment; filename=speech.{ext}"},
    )

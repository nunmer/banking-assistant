"""Thin STT/TTS wrapper service.

Exposes a stable interface to the bot (`POST /stt`, `POST /tts`) and routes to
a configurable provider. The speechkit provider proxies to the existing
speech-service; the whisper provider runs locally.
"""
import importlib
import logging

from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.responses import Response
from pydantic import BaseModel

import config

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("speech-api")

app = FastAPI(title="Forte Speech API")


def _provider():
    """Import the configured provider module lazily."""
    name = config.PROVIDER if config.PROVIDER in ("speechkit", "whisper") else "whisper"
    return importlib.import_module(f"providers.{name}")


class TTSRequest(BaseModel):
    text: str
    lang: str | None = None
    voice: str | None = None


@app.get("/health")
async def health() -> dict:
    return {"status": "ok", "provider": config.PROVIDER}


@app.post("/stt")
async def stt(request: Request, x_lang: str = Header(default=None)) -> dict:
    audio = await request.body()
    if not audio:
        raise HTTPException(status_code=400, detail="Empty audio body")

    lang = x_lang or config.DEFAULT_LANG
    try:
        text = await _provider().transcribe(audio, lang=lang)
    except Exception as e:  # noqa: BLE001 — surface provider failures as 502
        logger.error("STT failed [%s]: %s", config.PROVIDER, e)
        raise HTTPException(status_code=502, detail=f"STT failed: {e}")

    return {"text": text}


@app.post("/tts")
async def tts(req: TTSRequest) -> Response:
    if not req.text.strip():
        raise HTTPException(status_code=400, detail="text must not be empty")

    lang = req.lang or config.DEFAULT_LANG
    try:
        audio = await _provider().synthesize(req.text, lang=lang, voice=req.voice)
    except NotImplementedError:
        raise HTTPException(
            status_code=501,
            detail=f"TTS not supported by provider '{config.PROVIDER}'",
        )
    except Exception as e:  # noqa: BLE001
        logger.error("TTS failed [%s]: %s", config.PROVIDER, e)
        raise HTTPException(status_code=502, detail=f"TTS failed: {e}")

    return Response(content=audio, media_type="audio/ogg")

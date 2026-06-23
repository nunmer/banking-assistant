"""Speech API — thin proxy to the ForteBank speech-service.

All STT/TTS is delegated to the speech-service running on port 8000
(SPEECH_SERVICE_URL).  This service normalises the interface for the bot:
  POST /stt  — raw audio bytes + X-Lang header → {"text": "..."}
  POST /tts  — JSON {text, lang?, voice?} → audio/ogg bytes

Supported languages: kk-KZ, ru-RU, en-US.
"""
import logging

import httpx
from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.responses import Response
from pydantic import BaseModel

import config

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("speech-api")

app = FastAPI(title="Forte Speech API")


def _stt_url() -> str:
    return f"{config.SPEECH_SERVICE_URL}/stt/recognize"


def _tts_url() -> str:
    return f"{config.SPEECH_SERVICE_URL}/tts/synthesize"


class TTSRequest(BaseModel):
    text: str
    lang: str | None = None
    voice: str | None = None


@app.get("/health")
async def health() -> dict:
    return {"status": "ok", "speech_service": config.SPEECH_SERVICE_URL}


@app.post("/stt")
async def stt(request: Request, x_lang: str = Header(default=None)) -> dict:
    audio = await request.body()
    if not audio:
        raise HTTPException(status_code=400, detail="Empty audio body")

    lang = x_lang or config.DEFAULT_LANG
    logger.info("STT request lang=%s size=%d", lang, len(audio))

    try:
        async with httpx.AsyncClient(timeout=120.0) as client:
            resp = await client.post(
                _stt_url(),
                files={"file": ("audio.ogg", audio, "application/octet-stream")},
                data={"lang": lang, "engine": config.SPEECH_ENGINE},
            )
            resp.raise_for_status()
    except httpx.HTTPStatusError as e:
        logger.error("speech-service STT error %s: %s", e.response.status_code, e.response.text)
        raise HTTPException(status_code=502, detail=f"STT failed: {e.response.status_code}")
    except httpx.HTTPError as e:
        logger.error("speech-service unreachable: %s", e)
        raise HTTPException(status_code=502, detail="Speech service unavailable")

    text = resp.json().get("text", "")
    return {"text": text}


@app.post("/tts")
async def tts(req: TTSRequest) -> Response:
    if not req.text.strip():
        raise HTTPException(status_code=400, detail="text must not be empty")

    lang = req.lang or config.DEFAULT_LANG
    voice = req.voice or config.TTS_VOICE.get(lang, config.TTS_VOICE_DEFAULT)
    logger.info("TTS request lang=%s voice=%s chars=%d", lang, voice, len(req.text))

    try:
        async with httpx.AsyncClient(timeout=120.0) as client:
            resp = await client.post(
                _tts_url(),
                params={"engine": config.SPEECH_ENGINE},
                json={
                    "text": req.text,
                    "voice": voice,
                    "lang": lang,
                    "format": "OGG_OPUS",
                },
            )
            resp.raise_for_status()
    except httpx.HTTPStatusError as e:
        logger.error("speech-service TTS error %s: %s", e.response.status_code, e.response.text)
        raise HTTPException(status_code=502, detail=f"TTS failed: {e.response.status_code}")
    except httpx.HTTPError as e:
        logger.error("speech-service unreachable: %s", e)
        raise HTTPException(status_code=502, detail="Speech service unavailable")

    return Response(content=resp.content, media_type="audio/ogg")

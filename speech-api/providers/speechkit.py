"""SpeechKit provider — proxies to the existing speech-service.

Rather than re-implementing the Yandex REST contract, this delegates to the
running speech-service (https://github.com/nunmer/speechkit), which already
exposes `POST /stt/recognize` and `POST /tts/synthesize`.
"""
import httpx

import config


async def transcribe(audio: bytes, lang: str) -> str:
    """Send audio to speech-service /stt/recognize and return the transcript."""
    async with httpx.AsyncClient(timeout=120.0) as client:
        resp = await client.post(
            f"{config.SPEECHKIT_URL}/stt/recognize",
            files={"file": ("audio.ogg", audio, "application/octet-stream")},
            data={"lang": lang, "engine": config.SPEECHKIT_ENGINE},
        )
        resp.raise_for_status()
        return resp.json().get("text", "")


async def synthesize(text: str, lang: str, voice: str | None = None) -> bytes:
    """Send text to speech-service /tts/synthesize and return audio bytes."""
    async with httpx.AsyncClient(timeout=120.0) as client:
        resp = await client.post(
            f"{config.SPEECHKIT_URL}/tts/synthesize",
            params={"engine": config.SPEECHKIT_ENGINE},
            json={
                "text": text,
                "voice": voice or config.SPEECHKIT_TTS_VOICE,
                "lang": lang,
                "format": "OGG_OPUS",
            },
        )
        resp.raise_for_status()
        return resp.content

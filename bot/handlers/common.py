"""Shared helpers for talking to the orchestrator and speech API."""
import logging

import httpx

from bot.config import settings

logger = logging.getLogger("bot.common")


async def send_to_orchestrator(session_id: str, text: str, lang: str | None = None) -> dict:
    """POST a user utterance to the orchestrator /chat endpoint."""
    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.post(
            f"{settings.ORCHESTRATOR_URL}/chat",
            json={"session_id": session_id, "text": text, "lang": lang},
        )
        resp.raise_for_status()
        return resp.json()


async def synthesize(text: str, lang: str | None = None) -> bytes | None:
    """Call speech-api /tts and return OGG audio bytes, or None on failure."""
    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            resp = await client.post(
                f"{settings.SPEECH_API_URL}/tts",
                json={"text": text, "lang": lang or settings.SPEECH_DEFAULT_LANG},
            )
            resp.raise_for_status()
            return resp.content
    except httpx.HTTPError as e:
        logger.warning("TTS failed, falling back to text: %s", e)
        return None

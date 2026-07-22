"""Shared helpers for talking to the orchestrator and speech API."""
import logging

import httpx

from bot.config import settings, voice_for_lang

logger = logging.getLogger("bot.common")


def speech_headers() -> dict[str, str]:
    """Auth header for the speech-service, omitted when no key is configured."""
    return {"X-API-Key": settings.SPEECH_API_KEY} if settings.SPEECH_API_KEY else {}


async def send_to_orchestrator(
    session_id: str, text: str, lang: str | None = None, user_name: str | None = None
) -> dict:
    """POST a user utterance to the orchestrator /chat endpoint.

    `lang` is only sent when explicitly provided (e.g. to seed a new session).
    Normal messages omit it so the persisted session language — set via /lang —
    is never overwritten by the caller's Telegram locale.

    `user_name` (the Telegram first name) lets the orchestrator personalise a
    greeting reply — Telegram gives us this on every message, so it costs
    nothing to always pass it.
    """
    payload: dict = {"session_id": session_id, "text": text, "channel": "telegram"}
    if lang is not None:
        payload["lang"] = lang
    if user_name:
        payload["user_name"] = user_name
    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.post(f"{settings.ORCHESTRATOR_URL}/chat", json=payload)
        resp.raise_for_status()
        return resp.json()


async def get_user_lang(session_id: str, fallback: str | None = None) -> str:
    """Fetch the persisted session language from the orchestrator.

    Falls back to `fallback` (then SPEECH_DEFAULT_LANG) if the lookup fails.
    This is the source of truth for STT language and bot-side messages.
    """
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(
                f"{settings.ORCHESTRATOR_URL}/session/lang/{session_id}"
            )
            resp.raise_for_status()
            return resp.json().get("lang") or fallback or settings.SPEECH_DEFAULT_LANG
    except httpx.HTTPError as e:
        logger.warning("session lang lookup failed: %s", e)
        return fallback or settings.SPEECH_DEFAULT_LANG


async def synthesize(text: str, lang: str | None = None) -> bytes | None:
    """Call speech-service /tts/synthesize and return OGG audio bytes, or None on failure.

    The voice is chosen from the language so Kazakh text is read by a Kazakh
    voice rather than the default Russian one.
    """
    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            resp = await client.post(
                f"{settings.SPEECH_SERVICE_URL}/tts/synthesize",
                json={
                    "text": text,
                    "lang": lang or settings.SPEECH_DEFAULT_LANG,
                    "voice": voice_for_lang(lang),
                    "format": "OGG_OPUS",
                },
                headers=speech_headers(),
            )
            resp.raise_for_status()
            return resp.content
    except httpx.HTTPError as e:
        logger.warning("TTS failed, falling back to text: %s", e)
        return None

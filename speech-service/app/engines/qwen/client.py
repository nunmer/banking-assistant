"""Low-level HTTP transport for the self-hosted Qwen3-TTS server.

OpenAI-compatible /v1/audio/speech — plain REST, no gRPC. Response body is
raw audio bytes (no JSON/base64 wrapping, unlike Yandex).
"""
import requests

from app.core.config import settings


class QwenAPIError(Exception):
    pass


def synthesize_speech(text: str, voice: str, language: str) -> bytes:
    body = {
        "model": settings.QWEN_TTS_MODEL,
        "input": text,
        "voice": voice,
        "language": language,
    }
    try:
        resp = requests.post(
            settings.QWEN_TTS_URL, json=body, timeout=settings.QWEN_TIMEOUT,
            # requests honors HTTP_PROXY/HTTPS_PROXY env vars by default, which
            # corrupts requests to this internal-LAN host through a corporate
            # proxy that can't reach it properly — explicitly disable, same
            # reasoning as yandex/client.py's opt-in-only proxy handling.
            proxies={"http": None, "https": None},
        )
    except requests.RequestException as e:
        raise QwenAPIError(f"Request to {settings.QWEN_TTS_URL} failed: {e}") from e
    if not resp.ok:
        raise QwenAPIError(f"API error {resp.status_code}: {resp.text}")
    return resp.content

"""Shared Redis client + TTS audio cache.

The Redis client is created lazily so that importing this module never opens a
connection at import time (keeps unit tests and the API importable without Redis).
"""
import redis

from app.core.config import settings

_client: redis.Redis | None = None

_TTS_PREFIX = "tts:"


def client() -> redis.Redis:
    global _client
    if _client is None:
        _client = redis.from_url(settings.REDIS_URL)
    return _client


def get_tts_audio(key: str) -> bytes | None:
    try:
        return client().get(_TTS_PREFIX + key)
    except redis.RedisError:
        return None


def set_tts_audio(key: str, audio: bytes) -> None:
    try:
        client().set(_TTS_PREFIX + key, audio, ex=settings.TTS_CACHE_TTL_SECONDS)
    except redis.RedisError:
        pass

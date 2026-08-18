"""Live-editable bot behavior flags, layered over the env-var defaults.

`web/app.py`'s module constants (STREAMING_VOICE_ENABLED, TTS voices, STT
langs, rate limit, TTS char cap) stay the compile-time baseline — this module
independently reads the same env vars into `_DEFAULTS` (small duplication,
avoids a circular import with web.app) and layers a Redis-stored JSON patch
on top, so the admin panel can change behavior live without a redeploy.

`get_config()` never raises: a Redis outage falls back to `_DEFAULTS`
(identical to today's hardcoded behavior) rather than breaking the bot —
same "best-effort, log and continue" philosophy as orchestrator's
services/history.py. `update_config()` is the opposite: an explicit admin
write should surface a failure, not silently no-op.
"""
import asyncio
import json
import logging
import os

import redis.asyncio as aioredis

logger = logging.getLogger("web.admin.runtime_config")

REDIS_URL = os.getenv("REDIS_URL", "redis://redis:6379/0")
_redis = aioredis.from_url(
    REDIS_URL, decode_responses=True, socket_connect_timeout=1.5, socket_timeout=1.5
)
# get_config() is called on nearly every request and must fail fast into
# _DEFAULTS on a slow/unreachable Redis. redis-py's own socket timeouts above
# don't cover DNS resolution (a bad/unresolvable hostname can block in
# getaddrinfo for seconds before any socket is even opened) — wrapping the
# whole call in wait_for() caps the real end-to-end latency regardless of
# which stage is slow.
_GET_TIMEOUT = 0.5

_CONFIG_KEY = "admin:runtime_config"

_DEFAULTS = {
    "streaming_voice_enabled": os.getenv("STREAMING_VOICE_ENABLED", "false").strip().lower()
    in ("1", "true", "yes", "on"),
    "tts_voice_ru": os.getenv("TTS_VOICE_RU", "marina"),
    "tts_voice_kk": os.getenv("TTS_VOICE_KK", "amira"),
    "tts_voice_default": os.getenv("TTS_VOICE_DEFAULT", "marina"),
    "stt_langs": os.getenv("STT_LANGS", "ru-RU,kk-KZ"),
    "rate_limit_per_min": int(os.getenv("WEB_RATE_LIMIT_PER_MIN", "60")),
    "tts_max_chars": 250,
}

# Keys the admin panel is allowed to override — guards against an arbitrary
# patch key polluting the stored config with something no route ever reads.
_EDITABLE_KEYS = set(_DEFAULTS)


async def get_config() -> dict:
    cfg = dict(_DEFAULTS)
    try:
        raw = await asyncio.wait_for(_redis.get(_CONFIG_KEY), timeout=_GET_TIMEOUT)
        if raw:
            cfg.update(json.loads(raw))
    except Exception as e:  # noqa: BLE001 — never let a Redis hiccup break the bot
        logger.error("runtime config read failed, using defaults: %s", e)
    return cfg


async def update_config(patch: dict) -> dict:
    unknown = set(patch) - _EDITABLE_KEYS
    if unknown:
        raise ValueError(f"Unknown config key(s): {', '.join(sorted(unknown))}")
    cfg = await get_config()
    cfg.update(patch)
    await _redis.set(_CONFIG_KEY, json.dumps(cfg))
    return cfg

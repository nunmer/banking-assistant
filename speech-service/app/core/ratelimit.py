"""Per-key fixed-window rate limiting backed by Redis.

Fails open: if Redis is unreachable the request is allowed (availability over
strict enforcement). Disabled by default (RATE_LIMIT_ENABLED=false).
"""
import time

import redis
from fastapi import Depends, HTTPException

from app.core.auth import require_api_key
from app.core.config import settings
from app.db.models import ApiKey
from app.services import cache


def rate_limit(key: ApiKey | None = Depends(require_api_key)) -> None:
    if not settings.RATE_LIMIT_ENABLED:
        return

    identity = key.key_hash if key is not None else "anonymous"
    window = int(time.time() // settings.RATE_LIMIT_WINDOW_SECONDS)
    redis_key = f"rl:{identity}:{window}"

    try:
        client = cache.client()
        count = client.incr(redis_key)
        if count == 1:
            client.expire(redis_key, settings.RATE_LIMIT_WINDOW_SECONDS)
    except redis.RedisError:
        return  # fail open

    if count > settings.RATE_LIMIT_MAX_REQUESTS:
        raise HTTPException(status_code=429, detail="Rate limit exceeded")

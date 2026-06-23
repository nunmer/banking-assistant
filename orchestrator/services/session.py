"""User session store in Redis.

Key: session:{user_id}
Value: JSON — {account_id?, lang, ...}
TTL: SESSION_TTL (default 24 h).

lang defaults to "ru-RU" if never set.  It is written by the bot on /start
or /lang commands via the X-Lang header on /chat, and is used by the
orchestrator to return user-facing messages in the right language.
"""
import json

import redis.asyncio as aioredis

from orchestrator.config import settings

redis = aioredis.from_url(settings.REDIS_URL, decode_responses=True)

DEFAULT_LANG = "ru-RU"


def _key(session_id: str) -> str:
    return f"session:{session_id}"


async def get(session_id: str) -> dict:
    raw = await redis.get(_key(session_id))
    return json.loads(raw) if raw else {}


async def touch(session_id: str, updates: dict | None = None) -> dict:
    """Load the session, apply optional updates, persist, and return it."""
    data = await get(session_id)
    if "lang" not in data:
        data["lang"] = DEFAULT_LANG
    if updates:
        data.update(updates)
    await redis.setex(_key(session_id), settings.SESSION_TTL, json.dumps(data))
    return data

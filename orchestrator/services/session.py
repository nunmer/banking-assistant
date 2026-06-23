"""User session store in Redis.

Key: session:{user_id}
Value: JSON object — account_id, lang, and any future fields.
TTL: SESSION_TTL (default 24 h).

The session is created on first touch and refreshed on every interaction.
account_id is populated once real auth is wired in; for now it enables
balance/statement calls to pass account context to the MIB API as soon
as it becomes available (e.g., stored after a successful transfer).
"""
import json

import redis.asyncio as aioredis

from orchestrator.config import settings

redis = aioredis.from_url(settings.REDIS_URL, decode_responses=True)


def _key(session_id: str) -> str:
    return f"session:{session_id}"


async def get(session_id: str) -> dict:
    raw = await redis.get(_key(session_id))
    return json.loads(raw) if raw else {}


async def touch(session_id: str, updates: dict | None = None) -> dict:
    """Load the session, apply optional updates, persist, and return it."""
    data = await get(session_id)
    if updates:
        data.update(updates)
    await redis.setex(_key(session_id), settings.SESSION_TTL, json.dumps(data))
    return data

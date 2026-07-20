"""Multi-turn slot-filling state in Redis, keyed by session.

When a request is missing required parameters, the orchestrator asks for them
one at a time. This store remembers the intent, the parameters gathered so far,
and which slots are still missing, so each follow-up answer can be merged in
without re-deriving the whole request.

Separate from the 24h session (and from the pending-confirmation store): a
half-finished collection should expire quickly rather than persist all day.
"""
import json

import redis.asyncio as aioredis

from orchestrator.config import settings

redis = aioredis.from_url(settings.REDIS_URL, decode_responses=True)


def _key(session_id: str) -> str:
    return f"slotfill:{session_id}"


async def create(
    session_id: str, intent: str, params: dict, missing: list[str], lang: str
) -> None:
    """Persist (or replace) the in-progress collection for a session."""
    payload = json.dumps(
        {"intent": intent, "params": params, "missing": missing, "lang": lang}
    )
    await redis.setex(_key(session_id), settings.SLOTFILL_TTL, payload)


async def get(session_id: str) -> dict | None:
    raw = await redis.get(_key(session_id))
    if raw is None:
        return None
    return json.loads(raw)


async def clear(session_id: str) -> None:
    await redis.delete(_key(session_id))

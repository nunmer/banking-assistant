"""Pending-confirmation storage in Redis, keyed by session.

A pending confirmation captures everything needed to execute the operation
once the user approves, so the MIB call does not depend on re-running the LLM.
"""
import json

import redis.asyncio as aioredis

from orchestrator.config import settings
from orchestrator.db.models import Scenario

redis = aioredis.from_url(settings.REDIS_URL, decode_responses=True)


def _key(session_id: str) -> str:
    return f"confirm:{session_id}"


async def create_pending(session_id: str, scenario: Scenario, params: dict) -> None:
    payload = json.dumps(
        {
            "scenario_intent": scenario.intent,
            "mib_endpoint": scenario.mib_endpoint,
            "mib_method": scenario.mib_method,
            "params": params,
        }
    )
    await redis.setex(_key(session_id), settings.CONFIRM_TTL, payload)


async def get_pending(session_id: str) -> dict | None:
    raw = await redis.get(_key(session_id))
    if raw is None:
        return None
    return json.loads(raw)


async def clear_pending(session_id: str) -> None:
    await redis.delete(_key(session_id))

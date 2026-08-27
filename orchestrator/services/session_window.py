"""Rolling conversation-window id per identity (anonymous browser session

uuid) — groups the durable transcript (messages,
debug_events, session_identities) into separate "visits" instead of one
never-ending conversation, without changing the permanent identity itself.

A new turn arriving more than SESSION_WINDOW_TIMEOUT seconds after the last
one starts a new window — the same "state simply expires and looks fresh
next time" idea already used for pending confirmations (CONFIRM_TTL) and
slot-filling (SLOTFILL_TTL), just applied to the whole visit instead of one
pending step.

Deliberately NOT used for: account lookups (services/accounts.py calls MIB
with this identity as the real customer id), operation history
(services/history.py — a permanent record, not scoped to a visit), language
preference (services/session.py), or pending confirm/slot-fill (already
expire on their own, much faster than a visit boundary would ever need to).
"""
import asyncio
import logging
import time

import redis.asyncio as aioredis

from orchestrator.config import settings

logger = logging.getLogger("orchestrator.session_window")

# Short timeouts (same reasoning as web/admin/runtime_config.py): this is
# called on every single /chat turn, so a slow/unreachable Redis must fail
# fast into the fallback below rather than hang the reply behind the OS's
# own DNS/connect timeout.
redis = aioredis.from_url(
    settings.REDIS_URL, decode_responses=True, socket_connect_timeout=1.5, socket_timeout=1.5
)
_TIMEOUT = 0.5


def _state_key(identity: str) -> str:
    return f"session_window:{identity}"


def _counter_key(identity: str) -> str:
    return f"session_window_counter:{identity}"


async def _resolve_uncached(identity: str) -> str:
    key = _state_key(identity)
    raw = await redis.get(key)
    now = time.time()
    if raw:
        last_active_s, window_id = raw.split("|", 1)
        if now - float(last_active_s) <= settings.SESSION_WINDOW_TIMEOUT:
            await redis.setex(key, settings.SESSION_WINDOW_TIMEOUT, f"{now}|{window_id}")
            return window_id

    n = await redis.incr(_counter_key(identity))
    window_id = f"{identity}#{n}"
    await redis.setex(key, settings.SESSION_WINDOW_TIMEOUT, f"{now}|{window_id}")
    return window_id


async def resolve(identity: str) -> str:
    """Return the current window id for this identity, starting a new one

    (`"{identity}#{n}"`, so it stays searchable by the raw identity — see
    services/conversation.py's `q` substring search) if idle too long.

    Never raises: a Redis hiccup must never break the chat reply, so this
    falls back to the raw identity unchanged — the same "no windowing"
    behavior as before this feature existed, not a failure.
    """
    try:
        return await asyncio.wait_for(_resolve_uncached(identity), timeout=_TIMEOUT)
    except Exception as e:  # noqa: BLE001
        logger.error("session window resolution failed for %s: %s", identity, e)
        return identity

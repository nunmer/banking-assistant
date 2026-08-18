"""Unit tests for the rolling conversation-window id (services/session_window.py).

Regression coverage for "two visits under one Telegram account merge into
one never-ending conversation" — a new turn after SESSION_WINDOW_TIMEOUT
seconds of inactivity must start a new window; a turn within that window
must not.
"""
import time
from unittest.mock import AsyncMock, patch

import pytest

from orchestrator.services import session_window

# conftest.py's autouse fixture mocks session_window.resolve() to a plain
# passthrough for every other test's sake (suite speed — see its docstring).
# These tests exist specifically to exercise the real implementation, so they
# capture and restore it, on top of the fake redis client below.
_REAL_RESOLVE = session_window.resolve


class _FakeRedis:
    """Minimal in-memory stand-in for the two Redis calls session_window makes."""

    def __init__(self):
        self.store: dict[str, str] = {}
        self.counters: dict[str, int] = {}

    async def get(self, key):
        return self.store.get(key)

    async def setex(self, key, ttl, value):
        self.store[key] = value

    async def incr(self, key):
        self.counters[key] = self.counters.get(key, 0) + 1
        return self.counters[key]


@pytest.fixture
def fake_redis():
    fake = _FakeRedis()
    with (
        patch.object(session_window, "redis", fake),
        patch.object(session_window, "resolve", _REAL_RESOLVE),
    ):
        yield fake


class TestResolve:
    @pytest.mark.asyncio
    async def test_first_call_starts_window_one(self, fake_redis):
        assert await session_window.resolve("12345") == "12345#1"

    @pytest.mark.asyncio
    async def test_second_call_within_timeout_keeps_same_window(self, fake_redis):
        first = await session_window.resolve("12345")
        second = await session_window.resolve("12345")
        assert first == second == "12345#1"

    @pytest.mark.asyncio
    async def test_call_after_idle_timeout_starts_a_new_window(self, fake_redis):
        first = await session_window.resolve("12345")
        # Simulate the idle gap by back-dating the stored last-active timestamp
        # well beyond SESSION_WINDOW_TIMEOUT (30 min default).
        key = session_window._state_key("12345")
        stale_time = time.time() - 9999
        fake_redis.store[key] = f"{stale_time}|{first}"
        second = await session_window.resolve("12345")
        assert second == "12345#2"
        assert second != first

    @pytest.mark.asyncio
    async def test_different_identities_get_independent_counters(self, fake_redis):
        assert await session_window.resolve("user-a") == "user-a#1"
        assert await session_window.resolve("user-b") == "user-b#1"

    @pytest.mark.asyncio
    async def test_windowed_id_stays_substring_searchable_by_raw_identity(self, fake_redis):
        # The admin panel's session search does an ILIKE substring match on
        # the raw identity (see services/conversation.py) — the windowed id
        # must always contain it verbatim.
        window_id = await session_window.resolve("748371470")
        assert "748371470" in window_id

    @pytest.mark.asyncio
    async def test_redis_failure_falls_back_to_raw_identity(self):
        # Must never raise — a Redis hiccup must never break the chat reply.
        broken = AsyncMock()
        broken.get.side_effect = ConnectionError("down")
        with (
            patch.object(session_window, "redis", broken),
            patch.object(session_window, "resolve", _REAL_RESOLVE),
        ):
            result = await session_window.resolve("12345")
        assert result == "12345"

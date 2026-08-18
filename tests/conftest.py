"""Shared pytest fixtures for orchestrator and web-gateway unit tests."""
from unittest.mock import AsyncMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from orchestrator.main import app
from web.admin import runtime_config as web_runtime_config


@pytest.fixture(autouse=True)
def _slotfill_defaults():
    """Neutralise external stores/services for every test.

    Slot-fill (Redis), operation history (Postgres), conversation transcript
    logging (Postgres), and Telegram notification become no-ops. Tests that
    assert on them apply their own patches.
    """
    with (
        patch("orchestrator.services.slotfill.get", new=AsyncMock(return_value=None)),
        patch("orchestrator.services.slotfill.create", new=AsyncMock()),
        patch("orchestrator.services.slotfill.clear", new=AsyncMock()),
        patch("orchestrator.services.history.record", new=AsyncMock()),
        patch("orchestrator.services.history.list_recent", new=AsyncMock(return_value=[])),
        patch("orchestrator.services.notify.telegram_operation", new=AsyncMock()),
        patch("orchestrator.services.conversation.log", new=AsyncMock()),
        patch("orchestrator.services.debug_events.log_event", new=AsyncMock()),
        patch("orchestrator.services.session_identity.upsert", new=AsyncMock()),
        # session_window.resolve() already fails open to the raw identity on
        # a Redis error (see its own docstring), but paying real DNS/connect
        # latency for that fallback on every single /chat test call makes the
        # suite slow for no reason — short-circuit straight to the no-op
        # passthrough tests actually rely on (history_session_id == session_id).
        patch(
            "orchestrator.services.session_window.resolve",
            new=AsyncMock(side_effect=lambda identity: identity),
        ),
    ):
        yield


@pytest.fixture(autouse=True)
def _web_runtime_config_defaults():
    """No test environment has a reachable Redis at the `redis` hostname —

    web.admin.runtime_config.get_config() already falls back to its
    _DEFAULTS on any Redis error, but paying real DNS/connect latency for
    that fallback on every single web-gateway test request makes the suite
    slow for no reason. Short-circuit straight to the same defaults; tests
    that specifically exercise flag overrides patch this themselves (their
    own `with patch(...)` takes precedence for that test).
    """
    with patch(
        "web.admin.runtime_config.get_config",
        new=AsyncMock(return_value=dict(web_runtime_config._DEFAULTS)),
    ):
        yield


@pytest.fixture
async def client():
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as ac:
        yield ac

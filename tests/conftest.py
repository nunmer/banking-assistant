"""Shared pytest fixtures for orchestrator unit tests."""
from unittest.mock import AsyncMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from orchestrator.main import app


@pytest.fixture(autouse=True)
def _slotfill_defaults():
    """Neutralise external stores/services for every test.

    Slot-fill (Redis), operation history (Postgres), and Telegram notification
    become no-ops. Tests that assert on them apply their own patches.
    """
    with (
        patch("orchestrator.services.slotfill.get", new=AsyncMock(return_value=None)),
        patch("orchestrator.services.slotfill.create", new=AsyncMock()),
        patch("orchestrator.services.slotfill.clear", new=AsyncMock()),
        patch("orchestrator.services.history.record", new=AsyncMock()),
        patch("orchestrator.services.history.list_recent", new=AsyncMock(return_value=[])),
        patch("orchestrator.services.notify.telegram_operation", new=AsyncMock()),
    ):
        yield


@pytest.fixture
async def client():
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as ac:
        yield ac

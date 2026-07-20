"""Shared pytest fixtures for orchestrator unit tests."""
from unittest.mock import AsyncMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from orchestrator.main import app


@pytest.fixture(autouse=True)
def _slotfill_defaults():
    """Neutralise the Redis-backed slot-fill store for every test.

    Default: no in-progress collection, writes are no-ops. Slot-filling tests
    override `slotfill.get` with their own patch.
    """
    with (
        patch("orchestrator.services.slotfill.get", new=AsyncMock(return_value=None)),
        patch("orchestrator.services.slotfill.create", new=AsyncMock()),
        patch("orchestrator.services.slotfill.clear", new=AsyncMock()),
    ):
        yield


@pytest.fixture
async def client():
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as ac:
        yield ac

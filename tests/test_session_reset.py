"""Tests for POST /session/reset — the "start fresh" action wired to /start.

Clears a stuck pending confirmation / in-progress slot-filling collection
without touching the durable conversation history or operations record.
"""
from unittest.mock import AsyncMock, patch

import pytest


class TestSessionReset:
    @pytest.mark.asyncio
    async def test_reset_clears_pending_confirm_and_slotfill(self, client):
        with (
            patch("orchestrator.services.confirm.clear_pending", new=AsyncMock()) as clear_confirm,
            patch("orchestrator.services.slotfill.clear", new=AsyncMock()) as clear_slotfill,
        ):
            resp = await client.post("/session/reset", json={"session_id": "12345"})

        assert resp.status_code == 200
        assert resp.json() == {"ok": True}
        clear_confirm.assert_awaited_once_with("12345")
        clear_slotfill.assert_awaited_once_with("12345")

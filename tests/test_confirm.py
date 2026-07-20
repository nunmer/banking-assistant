"""Unit tests for POST /confirm/reply — mocks confirm store, session, and MIB client."""
from unittest.mock import AsyncMock, patch

import pytest

from orchestrator.models import MIBResult

_SESSION = {"lang": "en-US"}

_PENDING = {
    "scenario_intent": "transfer",
    "mib_endpoint": "/transfer",
    "mib_method": "POST",
    "params": {"amount": "500", "currency": "USD", "to_account": "KZ123"},
}

_SUCCESS = MIBResult(
    status="success",
    tx_id="MOCK-ABCD1234",
    message="Transfer completed. Ref: MOCK-ABCD1234",
)

_ERROR = MIBResult(
    status="error",
    tx_id="",
    message="The bank could not process this operation. Please try again later.",
)


@pytest.mark.asyncio
async def test_confirm_approved_calls_mib(client):
    with (
        patch("orchestrator.services.session.get", new=AsyncMock(return_value=_SESSION)),
        patch("orchestrator.services.confirm.get_pending", new=AsyncMock(return_value=_PENDING)),
        patch("orchestrator.services.confirm.clear_pending", new=AsyncMock()),
        patch("orchestrator.services.mib.execute", new=AsyncMock(return_value=_SUCCESS)),
    ):
        resp = await client.post(
            "/confirm/reply", json={"session_id": "u1", "approved": True}
        )

    assert resp.status_code == 200
    data = resp.json()
    assert data["action"] == "reply"
    assert "MOCK-ABCD1234" in data["message"]


@pytest.mark.asyncio
async def test_confirm_rejected_cancels(client):
    with (
        patch("orchestrator.services.session.get", new=AsyncMock(return_value=_SESSION)),
        patch("orchestrator.services.confirm.get_pending", new=AsyncMock(return_value=_PENDING)),
        patch("orchestrator.services.confirm.clear_pending", new=AsyncMock()),
    ):
        resp = await client.post(
            "/confirm/reply", json={"session_id": "u1", "approved": False}
        )

    assert resp.status_code == 200
    assert "cancelled" in resp.json()["message"].lower()


@pytest.mark.asyncio
async def test_confirm_no_pending(client):
    with (
        patch("orchestrator.services.session.get", new=AsyncMock(return_value=_SESSION)),
        patch("orchestrator.services.confirm.get_pending", new=AsyncMock(return_value=None)),
    ):
        resp = await client.post(
            "/confirm/reply", json={"session_id": "u99", "approved": True}
        )

    assert resp.status_code == 200
    assert "expired" in resp.json()["message"].lower()


@pytest.mark.asyncio
async def test_confirm_mib_error_returns_friendly_message(client):
    with (
        patch("orchestrator.services.session.get", new=AsyncMock(return_value=_SESSION)),
        patch("orchestrator.services.confirm.get_pending", new=AsyncMock(return_value=_PENDING)),
        patch("orchestrator.services.confirm.clear_pending", new=AsyncMock()),
        patch("orchestrator.services.mib.execute", new=AsyncMock(return_value=_ERROR)),
    ):
        resp = await client.post(
            "/confirm/reply", json={"session_id": "u1", "approved": True}
        )

    assert resp.status_code == 200
    body = resp.json()
    assert body["action"] == "reply"
    assert "bank" in body["message"].lower() or "process" in body["message"].lower()


@pytest.mark.asyncio
async def test_confirm_clears_before_mib_to_prevent_double_execute(client):
    """clear_pending must be called before mib.execute to prevent re-execution on double-tap."""
    call_order = []

    async def fake_clear(sid):
        call_order.append("clear")

    async def fake_mib(**kwargs):
        call_order.append("mib")
        return _SUCCESS

    with (
        patch("orchestrator.services.session.get", new=AsyncMock(return_value=_SESSION)),
        patch("orchestrator.services.confirm.get_pending", new=AsyncMock(return_value=_PENDING)),
        patch("orchestrator.services.confirm.clear_pending", side_effect=fake_clear),
        patch("orchestrator.services.mib.execute", side_effect=fake_mib),
    ):
        await client.post(
            "/confirm/reply", json={"session_id": "u1", "approved": True}
        )

    assert call_order == ["clear", "mib"]


@pytest.mark.asyncio
async def test_confirm_kazakh_session_returns_kazakh_cancel(client):
    with (
        patch("orchestrator.services.session.get", new=AsyncMock(return_value={"lang": "kk-KZ"})),
        patch("orchestrator.services.confirm.get_pending", new=AsyncMock(return_value=_PENDING)),
        patch("orchestrator.services.confirm.clear_pending", new=AsyncMock()),
    ):
        resp = await client.post(
            "/confirm/reply", json={"session_id": "u20", "approved": False}
        )

    assert resp.status_code == 200
    assert "тарт" in resp.json()["message"]  # "бас тарттым" (kk cancel)

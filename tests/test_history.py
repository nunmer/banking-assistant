"""Tests for operation history recording, listing, and channel sync."""
from unittest.mock import AsyncMock, patch

import pytest

from orchestrator.models import MIBResult
from orchestrator.services import notify

_PENDING = {
    "scenario_intent": "transfer_phone",
    "mib_endpoint": "/transfer/phone",
    "mib_method": "POST",
    "params": {"phone": "87758155576", "amount": "5000"},
    "summary": "Перевожу 5000 на номер 8 (775) 815 55 76. Подтверждаете?",
    "lang": "ru-RU",
}

_OK = MIBResult(status="success", tx_id="MOCK-1234", message="done")


class TestIsTelegramSession:
    def test_numeric_id_is_telegram(self):
        assert notify.is_telegram_session("987654321")

    def test_uuid_is_not(self):
        assert not notify.is_telegram_session("3f6a2c9e-7b1d-4a5e-9c2f-1e8d7b6a5c4d")


@pytest.mark.asyncio
async def test_confirm_yes_records_operation_and_returns_it(client):
    """Approving via chat records history and returns the operation card data."""
    with (
        patch("orchestrator.services.confirm.get_pending", new=AsyncMock(return_value=_PENDING)),
        patch("orchestrator.services.confirm.clear_pending", new=AsyncMock()),
        patch("orchestrator.services.mib.execute", new=AsyncMock(return_value=_OK)),
        patch("orchestrator.services.session.touch", new=AsyncMock(return_value={"lang": "ru-RU"})),
        patch("orchestrator.services.history.record", new=AsyncMock()) as record,
        patch("orchestrator.services.notify.telegram_operation", new=AsyncMock()) as tg_notify,
    ):
        resp = await client.post(
            "/chat", json={"session_id": "111222333", "text": "да", "channel": "web"}
        )

    assert resp.status_code == 200
    body = resp.json()
    assert body["action"] == "reply"
    assert body["operation"]["summary"] == _PENDING["summary"]
    assert body["operation"]["status"] == "success"
    record.assert_awaited_once()
    kwargs = record.await_args.kwargs
    assert kwargs["session_id"] == "111222333"
    assert kwargs["intent"] == "transfer_phone"
    assert kwargs["channel"] == "web"
    # Web-executed operation for a Telegram-linked session → mirrored to chat.
    tg_notify.assert_awaited_once()


@pytest.mark.asyncio
async def test_telegram_channel_does_not_self_notify(client):
    """Operations done in Telegram are already visible there — no echo message."""
    with (
        patch("orchestrator.services.confirm.get_pending", new=AsyncMock(return_value=_PENDING)),
        patch("orchestrator.services.confirm.clear_pending", new=AsyncMock()),
        patch("orchestrator.services.mib.execute", new=AsyncMock(return_value=_OK)),
        patch("orchestrator.services.session.touch", new=AsyncMock(return_value={"lang": "ru-RU"})),
        patch("orchestrator.services.history.record", new=AsyncMock()),
        patch("orchestrator.services.notify.telegram_operation", new=AsyncMock()) as tg_notify,
    ):
        resp = await client.post(
            "/chat", json={"session_id": "111222333", "text": "да", "channel": "telegram"}
        )

    assert resp.status_code == 200
    tg_notify.assert_not_awaited()


@pytest.mark.asyncio
async def test_confirm_reply_endpoint_records_too(client):
    """The button path (/confirm/reply) records history like the chat path."""
    with (
        patch("orchestrator.services.confirm.get_pending", new=AsyncMock(return_value=_PENDING)),
        patch("orchestrator.services.confirm.clear_pending", new=AsyncMock()),
        patch("orchestrator.services.mib.execute", new=AsyncMock(return_value=_OK)),
        patch("orchestrator.services.session.get", new=AsyncMock(return_value={"lang": "ru-RU"})),
        patch("orchestrator.services.history.record", new=AsyncMock()) as record,
    ):
        resp = await client.post(
            "/confirm/reply",
            json={"session_id": "444555666", "approved": True, "channel": "telegram"},
        )

    assert resp.status_code == 200
    assert resp.json()["operation"]["status"] == "success"
    record.assert_awaited_once()
    assert record.await_args.kwargs["channel"] == "telegram"


@pytest.mark.asyncio
async def test_history_endpoint_lists_operations(client):
    ops = [{"intent": "transfer_phone", "summary": "…", "lang": "ru-RU",
            "status": "success", "tx_id": "MOCK-1", "channel": "telegram",
            "created_at": "2026-07-21T12:00:00+00:00"}]
    with patch("orchestrator.services.history.list_recent", new=AsyncMock(return_value=ops)):
        resp = await client.get("/history/12345?limit=10")
    assert resp.status_code == 200
    assert resp.json() == {"operations": ops}

"""Tests for the admin API: auth gate, scenario CRUD, conversation reads."""
import os
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# Matches the fixture values conftest.py sets before importing the app.
_CREDS = (os.environ["ADMIN_USER"], os.environ["ADMIN_PASSWORD"])

_SCENARIO = MagicMock(
    intent="transfer",
    display_name="Money Transfer",
    description="Transfer money between accounts",
    required_params=["amount", "currency", "to_account"],
    optional_params=[],
    confirm_template="Перевести {amount} {currency}?",
    confirm_templates={"ru-RU": "Перевести {amount} {currency}?"},
    mib_endpoint="/transfer",
    mib_method="POST",
    active=True,
    created_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
)


class TestAdminAuth:
    @pytest.mark.asyncio
    async def test_no_credentials_rejected(self, client):
        resp = await client.get("/admin/scenarios")
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_wrong_credentials_rejected(self, client):
        resp = await client.get("/admin/scenarios", auth=("admin", "wrong"))
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_correct_credentials_accepted(self, client):
        with patch(
            "orchestrator.services.scenario.list_all", new=AsyncMock(return_value=[])
        ):
            resp = await client.get("/admin/scenarios", auth=_CREDS)
        assert resp.status_code == 200


class TestScenarios:
    @pytest.mark.asyncio
    async def test_list_scenarios(self, client):
        with patch(
            "orchestrator.services.scenario.list_all",
            new=AsyncMock(return_value=[_SCENARIO]),
        ):
            resp = await client.get("/admin/scenarios", auth=_CREDS)
        assert resp.status_code == 200
        body = resp.json()
        assert len(body) == 1
        assert body[0]["intent"] == "transfer"
        assert body[0]["active"] is True

    @pytest.mark.asyncio
    async def test_get_scenario_not_found(self, client):
        with patch(
            "orchestrator.services.scenario.get_any", new=AsyncMock(return_value=None)
        ):
            resp = await client.get("/admin/scenarios/nonexistent", auth=_CREDS)
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_create_scenario(self, client):
        with (
            patch(
                "orchestrator.services.scenario.get_any", new=AsyncMock(return_value=None)
            ),
            patch(
                "orchestrator.services.scenario.create",
                new=AsyncMock(return_value=_SCENARIO),
            ) as create,
        ):
            resp = await client.post(
                "/admin/scenarios",
                auth=_CREDS,
                json={
                    "intent": "transfer",
                    "display_name": "Money Transfer",
                    "confirm_template": "Перевести {amount}?",
                    "mib_endpoint": "/transfer",
                },
            )
        assert resp.status_code == 201
        assert create.await_args.args[0]["intent"] == "transfer"

    @pytest.mark.asyncio
    async def test_create_scenario_conflict(self, client):
        with patch(
            "orchestrator.services.scenario.get_any", new=AsyncMock(return_value=_SCENARIO)
        ):
            resp = await client.post(
                "/admin/scenarios",
                auth=_CREDS,
                json={
                    "intent": "transfer",
                    "display_name": "Money Transfer",
                    "confirm_template": "x",
                    "mib_endpoint": "/transfer",
                },
            )
        assert resp.status_code == 409

    @pytest.mark.asyncio
    async def test_update_scenario_only_sends_provided_fields(self, client):
        with patch(
            "orchestrator.services.scenario.update", new=AsyncMock(return_value=_SCENARIO)
        ) as update:
            resp = await client.put(
                "/admin/scenarios/transfer", auth=_CREDS, json={"active": False}
            )
        assert resp.status_code == 200
        update.assert_awaited_once_with("transfer", {"active": False})

    @pytest.mark.asyncio
    async def test_update_scenario_not_found(self, client):
        with patch(
            "orchestrator.services.scenario.update", new=AsyncMock(return_value=None)
        ):
            resp = await client.put(
                "/admin/scenarios/nonexistent", auth=_CREDS, json={"active": False}
            )
        assert resp.status_code == 404


class TestConversations:
    @pytest.mark.asyncio
    async def test_list_sessions(self, client):
        rows = [
            {
                "session_id": "u1",
                "channel": "web",
                "last_message": "Здравствуйте!",
                "last_at": "2026-01-01T00:00:00+00:00",
                "message_count": 4,
            }
        ]
        with patch(
            "orchestrator.services.conversation.list_sessions",
            new=AsyncMock(return_value=rows),
        ):
            resp = await client.get("/admin/conversations/sessions", auth=_CREDS)
        assert resp.status_code == 200
        assert resp.json() == rows

    @pytest.mark.asyncio
    async def test_get_conversation_transcript(self, client):
        rows = [
            {"role": "user", "text": "Привет", "channel": "web", "lang": "ru-RU", "created_at": None},
            {"role": "bot", "text": "Здравствуйте!", "channel": "web", "lang": "ru-RU", "created_at": None},
        ]
        with patch(
            "orchestrator.services.conversation.list_messages",
            new=AsyncMock(return_value=rows),
        ) as list_messages:
            resp = await client.get("/admin/conversations/u1", auth=_CREDS)
        assert resp.status_code == 200
        assert resp.json() == rows
        list_messages.assert_awaited_once_with("u1", limit=200)

    @pytest.mark.asyncio
    async def test_list_sessions_forwards_search_query(self, client):
        with patch(
            "orchestrator.services.conversation.list_sessions", new=AsyncMock(return_value=[])
        ) as list_sessions:
            resp = await client.get(
                "/admin/conversations/sessions?q=sanzhar", auth=_CREDS
            )
        assert resp.status_code == 200
        list_sessions.assert_awaited_once_with(limit=50, offset=0, q="sanzhar")

    @pytest.mark.asyncio
    async def test_list_sessions_includes_identity_fields(self, client):
        rows = [
            {
                "session_id": "987654321", "channel": "telegram", "last_message": "hi",
                "last_at": None, "message_count": 3, "username": "sanzhar_k", "first_name": "Sanzhar",
            }
        ]
        with patch(
            "orchestrator.services.conversation.list_sessions", new=AsyncMock(return_value=rows)
        ):
            resp = await client.get("/admin/conversations/sessions", auth=_CREDS)
        assert resp.status_code == 200
        assert resp.json()[0]["username"] == "sanzhar_k"


class TestDebugEventsEndpoint:
    @pytest.mark.asyncio
    async def test_turn_events_requires_auth(self, client):
        resp = await client.get("/admin/turns/turn-1/events")
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_turn_events_returns_trace(self, client):
        events = [
            {"step": "stt", "detail": {"transcript": "hello"}, "created_at": None},
            {"step": "classify", "detail": {"intent": "balance", "confidence": 0.9}, "created_at": None},
            {"step": "mib_execute", "detail": {"status": "success"}, "created_at": None},
        ]
        with patch(
            "orchestrator.services.debug_events.list_events", new=AsyncMock(return_value=events)
        ) as list_events:
            resp = await client.get("/admin/turns/turn-1/events", auth=_CREDS)
        assert resp.status_code == 200
        assert resp.json() == events
        list_events.assert_awaited_once_with("turn-1")

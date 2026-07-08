"""Unit tests for POST /chat — mocks LLM, scenario DB, confirm store, session."""
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from orchestrator.models import IntentResult

# Scenario stub reused across tests.
_TRANSFER_SCENARIO = MagicMock(
    intent="transfer",
    display_name="Money Transfer",
    required_params=["amount", "currency", "to_account"],
    confirm_template="Transfer {amount} {currency} to account {to_account} — confirm?",
    mib_endpoint="/transfer",
    mib_method="POST",
)

_BALANCE_SCENARIO = MagicMock(
    intent="balance",
    display_name="Account Balance",
    required_params=[],
    confirm_template="Retrieve your account balance — confirm?",
    mib_endpoint="/balance",
    mib_method="POST",
)


@pytest.mark.asyncio
async def test_chat_returns_confirm_for_transfer(client):
    with (
        patch(
            "orchestrator.services.llm.classify",
            new=AsyncMock(
                return_value=IntentResult(
                    intent="transfer",
                    params={"amount": "500", "currency": "USD", "to_account": "KZ123"},
                    confidence=0.97,
                )
            ),
        ),
        patch(
            "orchestrator.services.scenario.get",
            new=AsyncMock(return_value=_TRANSFER_SCENARIO),
        ),
        patch(
            "orchestrator.services.confirm.create_pending",
            new=AsyncMock(),
        ),
        patch(
            "orchestrator.services.confirm.get_pending",
            new=AsyncMock(return_value=None),
        ),
        patch(
            "orchestrator.services.session.touch",
            new=AsyncMock(return_value={"lang": "en-US"}),
        ),
    ):
        resp = await client.post("/chat", json={"session_id": "u1", "text": "Transfer 500 USD to KZ123"})

    assert resp.status_code == 200
    data = resp.json()
    assert data["action"] == "confirm"
    assert "500" in data["message"]
    assert "KZ123" in data["message"]


@pytest.mark.asyncio
async def test_chat_unknown_intent_returns_reply(client):
    with (
        patch(
            "orchestrator.services.llm.classify",
            new=AsyncMock(
                return_value=IntentResult(intent="unknown", params={}, confidence=0.9)
            ),
        ),
        patch(
            "orchestrator.services.confirm.get_pending",
            new=AsyncMock(return_value=None),
        ),
        patch("orchestrator.services.session.touch", new=AsyncMock(return_value={"lang": "en-US"})),
    ):
        resp = await client.post("/chat", json={"session_id": "u2", "text": "Play music"})

    assert resp.status_code == 200
    assert resp.json()["action"] == "reply"


@pytest.mark.asyncio
async def test_chat_low_confidence_returns_reply(client):
    with (
        patch(
            "orchestrator.services.llm.classify",
            new=AsyncMock(
                return_value=IntentResult(intent="transfer", params={}, confidence=0.1)
            ),
        ),
        patch(
            "orchestrator.services.confirm.get_pending",
            new=AsyncMock(return_value=None),
        ),
        patch("orchestrator.services.session.touch", new=AsyncMock(return_value={"lang": "en-US"})),
    ):
        resp = await client.post("/chat", json={"session_id": "u3", "text": "hmm"})

    assert resp.status_code == 200
    assert resp.json()["action"] == "reply"


@pytest.mark.asyncio
async def test_chat_missing_params_returns_reply(client):
    with (
        patch(
            "orchestrator.services.llm.classify",
            new=AsyncMock(
                return_value=IntentResult(
                    intent="transfer",
                    params={"amount": "100"},  # missing currency + to_account
                    confidence=0.95,
                )
            ),
        ),
        patch(
            "orchestrator.services.scenario.get",
            new=AsyncMock(return_value=_TRANSFER_SCENARIO),
        ),
        patch(
            "orchestrator.services.confirm.get_pending",
            new=AsyncMock(return_value=None),
        ),
        patch("orchestrator.services.session.touch", new=AsyncMock(return_value={"lang": "en-US"})),
    ):
        resp = await client.post("/chat", json={"session_id": "u4", "text": "Transfer 100"})

    assert resp.status_code == 200
    body = resp.json()
    assert body["action"] == "reply"
    assert "currency" in body["message"] or "to_account" in body["message"]


@pytest.mark.asyncio
async def test_chat_session_account_id_fills_balance(client):
    """account_id from session should be merged into params for balance."""
    with (
        patch(
            "orchestrator.services.llm.classify",
            new=AsyncMock(
                return_value=IntentResult(intent="balance", params={}, confidence=0.99)
            ),
        ),
        patch(
            "orchestrator.services.scenario.get",
            new=AsyncMock(return_value=_BALANCE_SCENARIO),
        ),
        patch(
            "orchestrator.services.confirm.create_pending",
            new=AsyncMock(),
        ),
        patch(
            "orchestrator.services.confirm.get_pending",
            new=AsyncMock(return_value=None),
        ),
        patch(
            "orchestrator.services.session.touch",
            new=AsyncMock(return_value={"lang": "en-US", "account_id": "ACC-42"}),
        ),
    ):
        resp = await client.post("/chat", json={"session_id": "u5", "text": "balance"})

    assert resp.status_code == 200
    assert resp.json()["action"] == "confirm"

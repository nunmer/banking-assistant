"""Unit tests for POST /chat — mocks LLM, scenario DB, confirm/slotfill, session."""
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from orchestrator.models import IntentResult

# Scenario stub reused across tests.
_TRANSFER_SCENARIO = MagicMock(
    intent="transfer",
    display_name="Money Transfer",
    required_params=["amount", "currency", "to_account"],
    confirm_template="Transfer {amount} {currency} to account {to_account} — confirm?",
    confirm_templates={},
    mib_endpoint="/transfer",
    mib_method="POST",
)

_BALANCE_SCENARIO = MagicMock(
    intent="balance",
    display_name="Account Balance",
    required_params=[],
    confirm_template="Retrieve your account balance — confirm?",
    confirm_templates={},
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
        patch("orchestrator.services.scenario.get", new=AsyncMock(return_value=_TRANSFER_SCENARIO)),
        patch("orchestrator.services.confirm.create_pending", new=AsyncMock()),
        patch("orchestrator.services.confirm.get_pending", new=AsyncMock(return_value=None)),
        patch("orchestrator.services.session.touch", new=AsyncMock(return_value={"lang": "en-US"})),
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
            new=AsyncMock(return_value=IntentResult(intent="unknown", params={}, confidence=0.9)),
        ),
        patch("orchestrator.services.confirm.get_pending", new=AsyncMock(return_value=None)),
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
            new=AsyncMock(return_value=IntentResult(intent="transfer", params={}, confidence=0.1)),
        ),
        patch("orchestrator.services.confirm.get_pending", new=AsyncMock(return_value=None)),
        patch("orchestrator.services.session.touch", new=AsyncMock(return_value={"lang": "en-US"})),
    ):
        resp = await client.post("/chat", json={"session_id": "u3", "text": "hmm"})

    assert resp.status_code == 200
    assert resp.json()["action"] == "reply"


@pytest.mark.asyncio
async def test_chat_missing_params_starts_collection(client):
    """Missing required params now start slot-filling: ask for the first one."""
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
        patch("orchestrator.services.scenario.get", new=AsyncMock(return_value=_TRANSFER_SCENARIO)),
        patch("orchestrator.services.confirm.get_pending", new=AsyncMock(return_value=None)),
        patch("orchestrator.services.session.touch", new=AsyncMock(return_value={"lang": "en-US"})),
        patch("orchestrator.services.slotfill.create", new=AsyncMock()) as create,
    ):
        resp = await client.post("/chat", json={"session_id": "u4", "text": "Transfer 100"})

    assert resp.status_code == 200
    body = resp.json()
    assert body["action"] == "collect"
    assert "currency" in body["message"].lower()  # asks the first missing slot
    # Persisted the in-progress collection with the remaining slots.
    create.assert_awaited_once()
    assert create.await_args.kwargs["missing"] == ["currency", "to_account"]


@pytest.mark.asyncio
async def test_chat_session_account_id_fills_balance(client):
    """account_id from session should be merged into params for balance."""
    with (
        patch(
            "orchestrator.services.llm.classify",
            new=AsyncMock(return_value=IntentResult(intent="balance", params={}, confidence=0.99)),
        ),
        patch("orchestrator.services.scenario.get", new=AsyncMock(return_value=_BALANCE_SCENARIO)),
        patch("orchestrator.services.confirm.create_pending", new=AsyncMock()),
        patch("orchestrator.services.confirm.get_pending", new=AsyncMock(return_value=None)),
        patch(
            "orchestrator.services.session.touch",
            new=AsyncMock(return_value={"lang": "en-US", "account_id": "ACC-42"}),
        ),
    ):
        resp = await client.post("/chat", json={"session_id": "u5", "text": "balance"})

    assert resp.status_code == 200
    assert resp.json()["action"] == "confirm"


# ── Multi-turn slot-filling ──────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_slotfill_answer_completes_and_confirms(client):
    """A follow-up answer that fills the last slot proceeds to confirmation."""
    sf = {
        "intent": "transfer",
        "params": {"amount": "100", "currency": "USD"},
        "missing": ["to_account"],
        "lang": "en-US",
    }
    with (
        patch("orchestrator.services.confirm.get_pending", new=AsyncMock(return_value=None)),
        patch("orchestrator.services.session.touch", new=AsyncMock(return_value={"lang": "en-US"})),
        patch("orchestrator.services.slotfill.get", new=AsyncMock(return_value=sf)),
        patch("orchestrator.services.llm.extract_param", new=AsyncMock(return_value="KZ999")),
        patch("orchestrator.services.scenario.get", new=AsyncMock(return_value=_TRANSFER_SCENARIO)),
        patch("orchestrator.services.confirm.create_pending", new=AsyncMock()) as create_pending,
    ):
        resp = await client.post("/chat", json={"session_id": "u6", "text": "KZ999"})

    assert resp.status_code == 200
    data = resp.json()
    assert data["action"] == "confirm"
    assert "KZ999" in data["message"]
    assert "100" in data["message"]
    create_pending.assert_awaited_once()


@pytest.mark.asyncio
async def test_slotfill_answer_asks_next_slot(client):
    """Filling one of several missing slots asks for the next, not confirmation."""
    sf = {
        "intent": "transfer",
        "params": {"amount": "100"},
        "missing": ["currency", "to_account"],
        "lang": "en-US",
    }
    with (
        patch("orchestrator.services.confirm.get_pending", new=AsyncMock(return_value=None)),
        patch("orchestrator.services.session.touch", new=AsyncMock(return_value={"lang": "en-US"})),
        patch("orchestrator.services.slotfill.get", new=AsyncMock(return_value=sf)),
        patch("orchestrator.services.llm.extract_param", new=AsyncMock(return_value="USD")),
        patch("orchestrator.services.scenario.get", new=AsyncMock(return_value=_TRANSFER_SCENARIO)),
        patch("orchestrator.services.slotfill.create", new=AsyncMock()) as create,
    ):
        resp = await client.post("/chat", json={"session_id": "u7", "text": "in dollars"})

    assert resp.status_code == 200
    data = resp.json()
    assert data["action"] == "collect"
    assert "account" in data["message"].lower()  # now asks for to_account
    assert create.await_args.kwargs["missing"] == ["to_account"]


@pytest.mark.asyncio
async def test_slotfill_cancel_abandons_collection(client):
    sf = {"intent": "transfer", "params": {}, "missing": ["amount"], "lang": "en-US"}
    with (
        patch("orchestrator.services.confirm.get_pending", new=AsyncMock(return_value=None)),
        patch("orchestrator.services.session.touch", new=AsyncMock(return_value={"lang": "en-US"})),
        patch("orchestrator.services.slotfill.get", new=AsyncMock(return_value=sf)),
        patch("orchestrator.services.slotfill.clear", new=AsyncMock()) as clear,
        patch("orchestrator.services.llm.extract_param", new=AsyncMock()) as extract,
    ):
        resp = await client.post("/chat", json={"session_id": "u8", "text": "no"})

    assert resp.status_code == 200
    assert resp.json()["action"] == "reply"
    clear.assert_awaited_once()
    extract.assert_not_awaited()  # cancelled before any extraction


@pytest.mark.asyncio
async def test_slotfill_restatement_merges_params(client):
    """A full restatement of the same intent mid-collection merges its params."""
    sf = {
        "intent": "transfer",
        "params": {"amount": "100"},
        "missing": ["currency", "to_account"],
        "lang": "en-US",
    }
    with (
        patch("orchestrator.services.confirm.get_pending", new=AsyncMock(return_value=None)),
        patch("orchestrator.services.session.touch", new=AsyncMock(return_value={"lang": "en-US"})),
        patch("orchestrator.services.slotfill.get", new=AsyncMock(return_value=sf)),
        patch("orchestrator.services.llm.extract_param", new=AsyncMock(return_value=None)),
        patch(
            "orchestrator.services.llm.classify",
            new=AsyncMock(
                return_value=IntentResult(
                    intent="transfer",
                    params={"currency": "USD", "to_account": "KZ7"},
                    confidence=0.95,
                )
            ),
        ),
        patch("orchestrator.services.scenario.get", new=AsyncMock(return_value=_TRANSFER_SCENARIO)),
        patch("orchestrator.services.confirm.create_pending", new=AsyncMock()),
    ):
        resp = await client.post(
            "/chat", json={"session_id": "u12", "text": "in dollars to KZ7"}
        )

    assert resp.status_code == 200
    data = resp.json()
    assert data["action"] == "confirm"  # amount (kept) + currency + to_account
    assert "KZ7" in data["message"]
    assert "100" in data["message"]


@pytest.mark.asyncio
async def test_slotfill_context_switch_to_new_intent(client):
    """If the reply isn't the asked slot but is a new intent, switch to it."""
    sf = {
        "intent": "transfer",
        "params": {"amount": "100"},
        "missing": ["currency", "to_account"],
        "lang": "en-US",
    }
    with (
        patch("orchestrator.services.confirm.get_pending", new=AsyncMock(return_value=None)),
        patch("orchestrator.services.session.touch", new=AsyncMock(return_value={"lang": "en-US"})),
        patch("orchestrator.services.slotfill.get", new=AsyncMock(return_value=sf)),
        patch("orchestrator.services.llm.extract_param", new=AsyncMock(return_value=None)),
        patch(
            "orchestrator.services.llm.classify",
            new=AsyncMock(return_value=IntentResult(intent="balance", params={}, confidence=0.98)),
        ),
        patch("orchestrator.services.scenario.get", new=AsyncMock(return_value=_BALANCE_SCENARIO)),
        patch("orchestrator.services.confirm.create_pending", new=AsyncMock()),
        patch("orchestrator.services.slotfill.clear", new=AsyncMock()) as clear,
    ):
        resp = await client.post("/chat", json={"session_id": "u9", "text": "what's my balance"})

    assert resp.status_code == 200
    assert resp.json()["action"] == "confirm"  # balance needs no params → confirm
    clear.assert_awaited()  # abandoned the transfer collection

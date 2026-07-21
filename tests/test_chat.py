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

_TRANSFER_PHONE_SCENARIO = MagicMock(
    intent="transfer_phone",
    display_name="Transfer by Phone",
    required_params=["phone", "amount"],
    confirm_template="Transfer {amount} to number {phone} — confirm?",
    confirm_templates={},
    mib_endpoint="/transfer/phone",
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


@pytest.mark.asyncio
async def test_detected_language_switches_response(client):
    """Session is ru-RU, but a Kazakh message is detected → reply + persist as kk."""
    kk_scenario = MagicMock(
        intent="balance",
        display_name="Account Balance",
        required_params=[],
        confirm_template="Показать баланс вашего счёта?",
        confirm_templates={"kk-KZ": "Шотыңыздың балансын көрсетейін бе?"},
        mib_endpoint="/balance",
        mib_method="POST",
    )
    touch = AsyncMock(return_value={"lang": "ru-RU"})
    with (
        patch(
            "orchestrator.services.llm.classify",
            new=AsyncMock(
                return_value=IntentResult(
                    intent="balance", params={}, confidence=0.99, lang="kk-KZ"
                )
            ),
        ),
        patch("orchestrator.services.scenario.get", new=AsyncMock(return_value=kk_scenario)),
        patch("orchestrator.services.confirm.create_pending", new=AsyncMock()),
        patch("orchestrator.services.confirm.get_pending", new=AsyncMock(return_value=None)),
        patch("orchestrator.services.session.touch", new=touch),
    ):
        resp = await client.post("/chat", json={"session_id": "u-lang", "text": "балансым қанша"})

    assert resp.status_code == 200
    body = resp.json()
    assert body["message"] == "Шотыңыздың балансын көрсетейін бе?"  # kk reply
    assert body["lang"] == "kk-KZ"  # response carries its language for the bot's TTS voice
    # The detected language was persisted to the session.
    assert any(
        c.kwargs.get("updates") == {"lang": "kk-KZ"} for c in touch.await_args_list
    )


# ── Parameter validation ─────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_name_in_phone_is_rejected_and_reasked(client):
    """A name mistakenly placed in `phone` must not reach confirmation.

    Guards the reported bug: "Transfer 1500 to <name>" confirmed a transfer to a
    number that was actually a name. The value is dropped and phone is re-asked
    with a short "that's not right" note instead of confirming.
    """
    with (
        patch(
            "orchestrator.services.llm.classify",
            new=AsyncMock(
                return_value=IntentResult(
                    intent="transfer_phone",
                    params={"phone": "Aidar", "amount": "1500"},
                    confidence=0.95,
                )
            ),
        ),
        patch(
            "orchestrator.services.scenario.get",
            new=AsyncMock(return_value=_TRANSFER_PHONE_SCENARIO),
        ),
        patch("orchestrator.services.confirm.get_pending", new=AsyncMock(return_value=None)),
        patch("orchestrator.services.confirm.create_pending", new=AsyncMock()) as create_pending,
        patch("orchestrator.services.session.touch", new=AsyncMock(return_value={"lang": "en-US"})),
        patch("orchestrator.services.slotfill.create", new=AsyncMock()) as create,
    ):
        resp = await client.post(
            "/chat", json={"session_id": "u-ph", "text": "Transfer 1500 to Aidar"}
        )

    assert resp.status_code == 200
    body = resp.json()
    assert body["action"] == "collect"  # re-ask, not confirm
    assert "Aidar" not in body["message"]  # the bad value is not echoed back
    assert "phone" in body["message"].lower()  # asks for the phone number
    assert "quite right" in body["message"]  # invalid-value note prepended
    create_pending.assert_not_awaited()  # never reached confirmation
    # Only the valid param survived into the persisted collection.
    assert create.await_args.kwargs["params"] == {"amount": "1500"}
    assert create.await_args.kwargs["missing"] == ["phone"]


@pytest.mark.asyncio
async def test_valid_phone_reaches_confirmation(client):
    """A well-formed phone number passes validation and confirms as before."""
    with (
        patch(
            "orchestrator.services.llm.classify",
            new=AsyncMock(
                return_value=IntentResult(
                    intent="transfer_phone",
                    params={"phone": "+77012345678", "amount": "1500"},
                    confidence=0.96,
                )
            ),
        ),
        patch(
            "orchestrator.services.scenario.get",
            new=AsyncMock(return_value=_TRANSFER_PHONE_SCENARIO),
        ),
        patch("orchestrator.services.confirm.get_pending", new=AsyncMock(return_value=None)),
        patch("orchestrator.services.confirm.create_pending", new=AsyncMock()) as create_pending,
        patch("orchestrator.services.session.touch", new=AsyncMock(return_value={"lang": "en-US"})),
    ):
        resp = await client.post(
            "/chat", json={"session_id": "u-ph2", "text": "Transfer 1500 to +7 701 234 5678"}
        )

    assert resp.status_code == 200
    body = resp.json()
    assert body["action"] == "confirm"
    assert "8 (701) 234 56 78" in body["message"]  # formatted, grouped display
    create_pending.assert_awaited_once()


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

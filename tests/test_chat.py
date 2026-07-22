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
async def test_chat_greeting_gets_friendly_reply_not_unknown(client):
    """A bare 'hello' must not trigger the 'I didn't understand' capability dump."""
    with (
        patch(
            "orchestrator.services.llm.classify",
            new=AsyncMock(return_value=IntentResult(intent="greeting", params={}, confidence=0.98)),
        ),
        patch("orchestrator.services.confirm.get_pending", new=AsyncMock(return_value=None)),
        patch("orchestrator.services.session.touch", new=AsyncMock(return_value={"lang": "en-US"})),
        patch("orchestrator.services.scenario.get", new=AsyncMock()) as scenario_get,
    ):
        resp = await client.post("/chat", json={"session_id": "u2b", "text": "hello"})

    assert resp.status_code == 200
    body = resp.json()
    assert body["action"] == "reply"
    assert "help" in body["message"].lower()
    assert "didn't quite catch" not in body["message"]
    scenario_get.assert_not_awaited()  # greeting never reaches scenario lookup


@pytest.mark.asyncio
async def test_chat_greeting_uses_name_when_channel_provides_it(client):
    """Telegram/Mini App sessions get a personalised greeting."""
    with (
        patch(
            "orchestrator.services.llm.classify",
            new=AsyncMock(return_value=IntentResult(intent="greeting", params={}, confidence=0.98)),
        ),
        patch("orchestrator.services.confirm.get_pending", new=AsyncMock(return_value=None)),
        patch("orchestrator.services.session.touch", new=AsyncMock(return_value={"lang": "ru-RU"})),
    ):
        resp = await client.post(
            "/chat",
            json={"session_id": "u2e", "text": "Привет", "user_name": "Санжар"},
        )

    assert resp.status_code == 200
    from orchestrator.i18n import t
    assert resp.json()["message"] == t("ru-RU", "greeting_named", name="Санжар")
    assert "Санжар" in resp.json()["message"]


@pytest.mark.asyncio
async def test_chat_kazakh_greeting_with_name_is_kazakh_not_english(client):
    """Regression guard: a kk-KZ greeting must never fall back to English text
    read aloud by the Kazakh voice — it must use the real kk-KZ template."""
    with (
        patch(
            "orchestrator.services.llm.classify",
            new=AsyncMock(return_value=IntentResult(intent="greeting", params={}, confidence=0.98)),
        ),
        patch("orchestrator.services.confirm.get_pending", new=AsyncMock(return_value=None)),
        patch("orchestrator.services.session.touch", new=AsyncMock(return_value={"lang": "kk-KZ"})),
    ):
        resp = await client.post(
            "/chat",
            json={"session_id": "u2f", "text": "Сәлем", "lang": "kk-KZ", "user_name": "Санжар"},
        )

    assert resp.status_code == 200
    body = resp.json()
    assert body["lang"] == "kk-KZ"
    assert "Санжар" in body["message"]
    assert "Hello" not in body["message"]  # no English-fallback leakage


@pytest.mark.asyncio
async def test_chat_greeting_without_name_stays_generic(client):
    """No user_name provided (anonymous browser session) → the plain greeting."""
    with (
        patch(
            "orchestrator.services.llm.classify",
            new=AsyncMock(return_value=IntentResult(intent="greeting", params={}, confidence=0.98)),
        ),
        patch("orchestrator.services.confirm.get_pending", new=AsyncMock(return_value=None)),
        patch("orchestrator.services.session.touch", new=AsyncMock(return_value={"lang": "ru-RU"})),
    ):
        resp = await client.post("/chat", json={"session_id": "u2g", "text": "Привет"})

    assert resp.status_code == 200
    from orchestrator.i18n import t
    assert resp.json()["message"] == t("ru-RU", "greeting")


@pytest.mark.asyncio
async def test_chat_farewell_gets_distinct_reply_from_greeting(client):
    """'Thanks, bye' gets a closing remark, not the 'hello' opener reused."""
    with (
        patch(
            "orchestrator.services.llm.classify",
            new=AsyncMock(return_value=IntentResult(intent="farewell", params={}, confidence=0.97)),
        ),
        patch("orchestrator.services.confirm.get_pending", new=AsyncMock(return_value=None)),
        patch("orchestrator.services.session.touch", new=AsyncMock(return_value={"lang": "en-US"})),
        patch("orchestrator.services.scenario.get", new=AsyncMock()) as scenario_get,
    ):
        resp = await client.post("/chat", json={"session_id": "u2d", "text": "thanks, bye"})

    assert resp.status_code == 200
    body = resp.json()
    assert body["action"] == "reply"
    from orchestrator.i18n import t
    assert body["message"] == t("en-US", "farewell")
    assert body["message"] != t("en-US", "greeting")
    scenario_get.assert_not_awaited()


@pytest.mark.asyncio
async def test_slotfill_greeting_does_not_derail_collection(client):
    """Small talk mid-collection re-asks the same slot instead of erroring out."""
    sf = {"intent": "deposit_open", "params": {"amount": "100000"},
          "missing": ["term"], "lang": "en-US"}
    with (
        patch("orchestrator.services.confirm.get_pending", new=AsyncMock(return_value=None)),
        patch("orchestrator.services.session.touch", new=AsyncMock(return_value={"lang": "en-US"})),
        patch("orchestrator.services.slotfill.get", new=AsyncMock(return_value=sf)),
        patch("orchestrator.services.llm.extract_param", new=AsyncMock(return_value=None)),
        patch(
            "orchestrator.services.llm.classify",
            new=AsyncMock(return_value=IntentResult(intent="farewell", params={}, confidence=0.97)),
        ),
        patch("orchestrator.services.scenario.get", new=AsyncMock()) as scenario_get,
    ):
        resp = await client.post("/chat", json={"session_id": "u2c", "text": "thanks!"})

    assert resp.status_code == 200
    body = resp.json()
    assert body["action"] == "collect"  # still waiting on term, not switched away
    scenario_get.assert_not_awaited()


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


# ── Account resolution (transfer_own) ────────────────────────────────────────

_TRANSFER_OWN_SCENARIO = MagicMock(
    intent="transfer_own",
    display_name="Transfer Between Own Accounts",
    required_params=["from_account_kind", "to_account_kind", "amount"],
    confirm_template=(
        "Перевожу {amount} со счёта «{from_account_name}» "
        "на счёт «{to_account_name}». Подтверждаете?"
    ),
    confirm_templates={},
    mib_endpoint="/transfer/own",
    mib_method="POST",
)

_MOCK_ACCOUNTS = [
    {"account_id": "ACC-KZT-001", "currency": "KZT",
     "name": {"ru-RU": "Тенговый", "kk-KZ": "Теңгелік", "en-US": "Tenge"}},
    {"account_id": "ACC-USD-001", "currency": "USD",
     "name": {"ru-RU": "Долларовый", "kk-KZ": "Долларлық", "en-US": "Dollar"}},
]


@pytest.mark.asyncio
async def test_transfer_own_confirms_with_account_names(client):
    """Account kinds resolve to real accounts; the confirm shows names, not codes."""
    with (
        patch(
            "orchestrator.services.llm.classify",
            new=AsyncMock(
                return_value=IntentResult(
                    intent="transfer_own",
                    params={"from_account_kind": "KZT", "to_account_kind": "USD",
                            "amount": "10000"},
                    confidence=0.95,
                    lang="ru-RU",
                )
            ),
        ),
        patch(
            "orchestrator.services.scenario.get",
            new=AsyncMock(return_value=_TRANSFER_OWN_SCENARIO),
        ),
        patch(
            "orchestrator.services.accounts.list_accounts",
            new=AsyncMock(return_value=_MOCK_ACCOUNTS),
        ),
        patch("orchestrator.services.confirm.get_pending", new=AsyncMock(return_value=None)),
        patch("orchestrator.services.confirm.create_pending", new=AsyncMock()) as create_pending,
        patch("orchestrator.services.session.touch", new=AsyncMock(return_value={"lang": "ru-RU"})),
    ):
        resp = await client.post(
            "/chat",
            json={"session_id": "u-own", "text": "Переведи 10000 с тенгового на долларовый"},
        )

    assert resp.status_code == 200
    body = resp.json()
    assert body["action"] == "confirm"
    assert "Тенговый" in body["message"] and "Долларовый" in body["message"]
    assert "KZT" not in body["message"]  # names, not raw codes
    # The MIB call will receive the resolved account IDs.
    sent = create_pending.await_args.kwargs["params"]
    assert sent["from_account_id"] == "ACC-KZT-001"
    assert sent["to_account_id"] == "ACC-USD-001"
    # History gets the compact record, not the confirmation question.
    assert create_pending.await_args.kwargs["summary"] == \
        "Перевод 10000: Тенговый → Долларовый"


@pytest.mark.asyncio
async def test_transfer_own_unknown_kind_replies_with_accounts(client):
    """An unresolvable kind ends the turn with the available-accounts reply."""
    with (
        patch(
            "orchestrator.services.llm.classify",
            new=AsyncMock(
                return_value=IntentResult(
                    intent="transfer_own",
                    params={"from_account_kind": "GBP", "to_account_kind": "USD",
                            "amount": "10"},
                    confidence=0.95,
                    lang="ru-RU",
                )
            ),
        ),
        patch(
            "orchestrator.services.scenario.get",
            new=AsyncMock(return_value=_TRANSFER_OWN_SCENARIO),
        ),
        patch(
            "orchestrator.services.accounts.list_accounts",
            new=AsyncMock(return_value=_MOCK_ACCOUNTS),
        ),
        patch("orchestrator.services.confirm.get_pending", new=AsyncMock(return_value=None)),
        patch("orchestrator.services.confirm.create_pending", new=AsyncMock()) as create_pending,
        patch("orchestrator.services.session.touch", new=AsyncMock(return_value={"lang": "ru-RU"})),
    ):
        resp = await client.post(
            "/chat", json={"session_id": "u-own2", "text": "с фунтового на долларовый 10"}
        )

    assert resp.status_code == 200
    body = resp.json()
    assert body["action"] == "reply"  # not a confirm
    assert "Тенговый" in body["message"]  # lists what the user actually has
    create_pending.assert_not_awaited()


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
async def test_dictated_phone_is_corrected_deterministically(client):
    """A phone dictated as Kazakh number-words is captured from the raw text.

    Guards the reported bug: the LLM non-deterministically mis-transcribed a long
    spoken number (777/581 instead of 775/815). Even when classify returns a
    wrong phone, the deterministic parser overrides it from the transcript.
    """
    transcript = (
        "сегіз жеті жүз жетпіс бес сегіз жүз он бес елу бес жетпіс алты "
        "нөміріне бес мың теңге аудару керек"
    )
    with (
        patch(
            "orchestrator.services.llm.classify",
            new=AsyncMock(
                return_value=IntentResult(
                    intent="transfer_phone",
                    params={"phone": "87775815576", "amount": "5000"},  # LLM got it wrong
                    confidence=0.95,
                    lang="kk-KZ",
                )
            ),
        ),
        patch(
            "orchestrator.services.scenario.get",
            new=AsyncMock(return_value=_TRANSFER_PHONE_SCENARIO),
        ),
        patch("orchestrator.services.confirm.get_pending", new=AsyncMock(return_value=None)),
        patch("orchestrator.services.confirm.create_pending", new=AsyncMock()),
        patch("orchestrator.services.session.touch", new=AsyncMock(return_value={"lang": "kk-KZ"})),
    ):
        resp = await client.post(
            "/chat", json={"session_id": "u-dict", "text": transcript}
        )

    assert resp.status_code == 200
    body = resp.json()
    assert body["action"] == "confirm"
    assert "8 (775) 815 55 76" in body["message"]  # corrected from the transcript
    assert "777" not in body["message"]  # the LLM's wrong digits are gone


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

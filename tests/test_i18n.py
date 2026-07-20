"""Tests for orchestrator i18n helpers and multilingual chat responses."""
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from orchestrator.i18n import _SLOT_PROMPTS, slot_prompt, t
from orchestrator.models import IntentResult

_TRANSFER_SCENARIO = MagicMock(
    intent="transfer",
    display_name="Money Transfer",
    required_params=["amount", "currency", "to_account"],
    confirm_template="Перевести {amount} {currency} на счёт {to_account} — подтвердить?",
    confirm_templates={
        "ru-RU": "Перевести {amount} {currency} на счёт {to_account} — подтвердить?",
        "kk-KZ": "{to_account} шотына {amount} {currency} аудару — растайсыз ба?",
        "en-US": "Transfer {amount} {currency} to account {to_account} — confirm?",
    },
    mib_endpoint="/transfer",
    mib_method="POST",
)


class TestI18nHelper:
    def test_russian_unknown_intent(self):
        msg = t("ru-RU", "unknown_intent")
        assert "не понял" in msg

    def test_kazakh_unknown_intent(self):
        msg = t("kk-KZ", "unknown_intent")
        assert "түсінбедім" in msg

    def test_english_unknown_intent(self):
        msg = t("en-US", "unknown_intent")
        assert "couldn't understand" in msg

    def test_missing_params_interpolation(self):
        msg = t("en-US", "missing_params", params="currency, to_account")
        assert "currency" in msg
        assert "to_account" in msg

    def test_fallback_to_english_for_unknown_lang(self):
        msg = t("fr-FR", "cancelled")
        assert msg == t("ru-RU", "cancelled")  # falls back to DEFAULT_LANG (ru-RU)

    def test_cancelled_messages(self):
        assert "Отменено" in t("ru-RU", "cancelled")
        assert "Бас тартылды" in t("kk-KZ", "cancelled")
        assert "Cancelled" in t("en-US", "cancelled")


class TestSlotPrompt:
    # Required params introduced with the expanded scenarios — each needs a
    # dedicated prompt in every language, not the generic fallback.
    NEW_PARAMS = [
        "from_account_kind", "to_account_kind", "phone", "term", "card_last4",
        "limit_kind", "limit_amount", "period", "cert_kind",
    ]

    @pytest.mark.parametrize("lang", ["ru-RU", "kk-KZ", "en-US"])
    def test_new_params_have_dedicated_prompts(self, lang):
        for param in self.NEW_PARAMS:
            assert param in _SLOT_PROMPTS[lang], f"{param} missing for {lang}"
            assert slot_prompt(lang, param) == _SLOT_PROMPTS[lang][param]

    def test_unknown_param_uses_fallback(self):
        msg = slot_prompt("ru-RU", "nonexistent")
        assert "nonexistent" in msg
        assert "{param}" not in msg  # placeholder was interpolated


@pytest.mark.asyncio
async def test_chat_kazakh_returns_kazakh_confirm(client):
    with (
        patch(
            "orchestrator.services.llm.classify",
            new=AsyncMock(
                return_value=IntentResult(
                    intent="transfer",
                    params={"amount": "1000", "currency": "KZT", "to_account": "KZ456"},
                    confidence=0.96,
                )
            ),
        ),
        patch(
            "orchestrator.services.scenario.get",
            new=AsyncMock(return_value=_TRANSFER_SCENARIO),
        ),
        patch("orchestrator.services.confirm.create_pending", new=AsyncMock()),
        patch(
            "orchestrator.services.confirm.get_pending",
            new=AsyncMock(return_value=None),
        ),
        patch(
            "orchestrator.services.session.touch",
            new=AsyncMock(return_value={"lang": "kk-KZ"}),
        ),
    ):
        resp = await client.post(
            "/chat",
            json={"session_id": "u10", "text": "KZ456 шотына 1000 теңге аудар", "lang": "kk-KZ"},
        )

    assert resp.status_code == 200
    body = resp.json()
    assert body["action"] == "confirm"
    assert "растайсыз ба?" in body["message"]
    assert "KZ456" in body["message"]


@pytest.mark.asyncio
async def test_chat_russian_returns_russian_error(client):
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
        patch(
            "orchestrator.services.session.touch",
            new=AsyncMock(return_value={"lang": "ru-RU"}),
        ),
    ):
        resp = await client.post(
            "/chat",
            json={"session_id": "u11", "text": "включи музыку", "lang": "ru-RU"},
        )

    assert resp.status_code == 200
    body = resp.json()
    assert body["action"] == "reply"
    assert "не понял" in body["message"]

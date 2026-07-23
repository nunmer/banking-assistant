"""Tests for orchestrator i18n helpers and multilingual chat responses."""
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from orchestrator.i18n import _SLOT_PROMPTS, effective_lang, slot_prompt, speech, strip_for_speech, t
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
        assert "помочь" in msg and "Переводы" in msg  # friendly capability list

    def test_kazakh_unknown_intent(self):
        msg = t("kk-KZ", "unknown_intent")
        assert "Аударымдар" in msg  # capability list

    def test_english_unknown_intent(self):
        msg = t("en-US", "unknown_intent")
        assert "help with" in msg and "Transfers" in msg

    def test_russian_unknown_intent_topic_names_the_topic(self):
        msg = t("ru-RU", "unknown_intent_topic", topic="курс доллара к тенге")
        assert "курс доллара к тенге" in msg

    def test_english_unknown_intent_topic_names_the_topic(self):
        msg = t("en-US", "unknown_intent_topic", topic="today's weather")
        assert "today's weather" in msg

    def test_kazakh_unknown_intent_topic_names_the_topic(self):
        assert effective_lang("kk-KZ", "unknown_intent_topic") == "kk-KZ"
        msg = t("kk-KZ", "unknown_intent_topic", topic="доллар бағамы")
        assert "доллар бағамы" in msg

    @pytest.mark.parametrize("lang", ["ru-RU", "en-US"])
    def test_greeting_and_farewell_are_distinct(self, lang):
        # "hello" and "thanks, bye" must not get the same canned reply — a
        # closing remark read back in response to an opener sounds wrong.
        assert t(lang, "greeting") != t(lang, "farewell")

    def test_russian_bot_info_names_the_assistant(self):
        msg = t("ru-RU", "bot_info")
        assert "AI-nur" in msg and "Переводы" in msg

    def test_english_bot_info_names_the_assistant(self):
        msg = t("en-US", "bot_info")
        assert "AI-nur" in msg and "Transfers" in msg

    def test_kazakh_bot_info_names_the_assistant(self):
        assert effective_lang("kk-KZ", "bot_info") == "kk-KZ"
        msg = t("kk-KZ", "bot_info")
        assert "AI-nur" in msg and "Аударымдар" in msg

    def test_bot_info_distinct_from_unknown_intent(self):
        assert t("en-US", "bot_info") != t("en-US", "unknown_intent")

    def test_missing_params_interpolation(self):
        msg = t("en-US", "missing_params", params="currency, to_account")
        assert "currency" in msg
        assert "to_account" in msg

    def test_fallback_to_english_for_unknown_lang(self):
        msg = t("fr-FR", "cancelled")
        assert msg == t("ru-RU", "cancelled")  # falls back to DEFAULT_LANG (ru-RU)

    def test_missing_key_in_supported_lang_falls_back_to_default_not_english(self):
        # Regression guard: a kk-KZ session whose reply text falls back to
        # English (because a key wasn't translated yet) gets read aloud by a
        # Kazakh TTS voice — garbled noise, not a language mismatch a user can
        # even parse visually. Falling back to ru-RU instead is understandable
        # to this user base and is what "Russian is the default" (this
        # module's own docstring) should actually mean in practice.
        import orchestrator.i18n as i18n_module

        original = dict(i18n_module._MESSAGES["kk-KZ"])
        try:
            i18n_module._MESSAGES["kk-KZ"].pop("cancelled", None)
            assert t("kk-KZ", "cancelled") == t("ru-RU", "cancelled")
            assert t("kk-KZ", "cancelled") != t("en-US", "cancelled")
        finally:
            i18n_module._MESSAGES["kk-KZ"] = original

    def test_cancelled_messages(self):
        assert "отменил" in t("ru-RU", "cancelled")
        assert "тарт" in t("kk-KZ", "cancelled")
        assert "cancelled" in t("en-US", "cancelled").lower()


class TestEffectiveLang:
    def test_present_key_reports_its_own_language(self):
        assert effective_lang("kk-KZ", "cancelled") == "kk-KZ"

    def test_missing_key_reports_default_lang_not_the_requested_one(self):
        # Regression guard for the exact bug reported live: kk-KZ's plain
        # "greeting" was missing (only "greeting_named" existed), so a
        # nameless Kazakh session got Russian fallback text while `lang`
        # still claimed "kk-KZ" — driving a Kazakh TTS voice to read Russian
        # words. effective_lang must report where the text actually came
        # from, not the language that was merely asked for.
        import orchestrator.i18n as i18n_module

        original = dict(i18n_module._MESSAGES["kk-KZ"])
        try:
            i18n_module._MESSAGES["kk-KZ"].pop("greeting", None)
            assert effective_lang("kk-KZ", "greeting") == "ru-RU"
        finally:
            i18n_module._MESSAGES["kk-KZ"] = original

    def test_unsupported_lang_reports_default(self):
        assert effective_lang("fr-FR", "cancelled") == "ru-RU"


class TestStripForSpeech:
    def test_removes_emoji(self):
        assert strip_for_speech("Готово! Операция выполнена. ✅") == "Готово! Операция выполнена."

    def test_collapses_whitespace_left_by_removed_emoji(self):
        out = strip_for_speech("Привет 🙂 мир")
        assert "  " not in out
        assert out == "Привет мир"

    def test_plain_text_untouched(self):
        assert strip_for_speech("Ничего не меняется.") == "Ничего не меняется."


class TestSpeech:
    @pytest.mark.parametrize("lang", ["ru-RU", "kk-KZ", "en-US"])
    def test_unknown_intent_has_dedicated_override(self, lang):
        # The bulleted capability list is fine on screen but unreadable aloud —
        # every language must have its own natural-sentence override, never a
        # borrowed one from another language.
        override = speech(lang, "unknown_intent")
        assert override != t(lang, "unknown_intent")
        assert "\n" not in override
        assert not any("\U0001F300" <= ch <= "\U0001FAFF" for ch in override)

    def test_falls_back_to_stripped_message_without_override(self):
        # "cancelled" has no dedicated override — speech() should still be
        # emoji-free, derived from this language's own message.
        assert speech("ru-RU", "cancelled") == strip_for_speech(t("ru-RU", "cancelled"))
        assert "👌" not in speech("ru-RU", "cancelled")

    def test_never_borrows_another_languages_override(self):
        # kk-KZ speech must never fall back to the ru-RU override text —
        # an untranslated language should read its own (stripped) message,
        # not another language's audio.
        kk = speech("kk-KZ", "unknown_intent")
        ru = speech("ru-RU", "unknown_intent")
        assert kk != ru

    @pytest.mark.parametrize("lang", ["ru-RU", "kk-KZ", "en-US"])
    def test_bot_info_has_dedicated_override(self, lang):
        # Same bulleted-list-unreadable-aloud problem as unknown_intent.
        override = speech(lang, "bot_info")
        assert override != t(lang, "bot_info")
        assert "\n" not in override
        assert not any("\U0001F300" <= ch <= "\U0001FAFF" for ch in override)

    def test_kazakh_bot_info_never_borrows_another_languages_override(self):
        kk = speech("kk-KZ", "bot_info")
        ru = speech("ru-RU", "bot_info")
        assert kk != ru


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
    assert "помочь" in body["message"]  # friendly capability list
    # The bulleted list is fine to read on screen but not aloud — the response
    # must carry a distinct, natural-sentence `speech` variant for TTS.
    assert body["speech"] is not None
    assert body["speech"] != body["message"]
    assert "\n" not in body["speech"]

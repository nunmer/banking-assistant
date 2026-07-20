"""Unit tests for orchestrator/services/llm.py — pure parsing logic, no API calls."""
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from orchestrator.services import llm
from orchestrator.services.llm import _parse
from orchestrator.models import IntentResult


def _fake_completion(content: str) -> MagicMock:
    """Build a stand-in for an OpenAI chat completion with the given content."""
    message = MagicMock(content=content)
    return MagicMock(choices=[MagicMock(message=message)])


class TestParse:
    def test_valid_json(self):
        raw = '{"intent": "balance", "params": {}, "confidence": 0.99}'
        assert _parse(raw) == {"intent": "balance", "params": {}, "confidence": 0.99}

    def test_json_wrapped_in_markdown(self):
        raw = 'Here is the result:\n```json\n{"intent": "transfer", "params": {"amount": "500"}}\n```'
        result = _parse(raw)
        assert result["intent"] == "transfer"

    def test_json_with_surrounding_text(self):
        raw = 'Sure! {"intent": "unknown", "params": {}, "confidence": 0.5} that is all.'
        assert _parse(raw)["intent"] == "unknown"

    def test_invalid_raises(self):
        with pytest.raises((json.JSONDecodeError, ValueError)):
            _parse("not json at all")


class TestIntentResult:
    def test_default_confidence(self):
        r = IntentResult(intent="balance", params={})
        assert r.confidence == 1.0

    def test_params_is_dict(self):
        r = IntentResult(intent="transfer", params={"amount": "500", "currency": "USD", "to_account": "KZ1"})
        assert r.params["amount"] == "500"


class TestSystemPrompt:
    NEW_INTENTS = [
        "transfer_own", "transfer_phone", "deposit_open", "card_block",
        "card_unblock", "card_limit", "statement_pdf", "certificate",
        "navigation", "manager",
    ]

    def test_all_new_intents_documented(self):
        for intent in self.NEW_INTENTS:
            assert intent in llm.SYSTEM_PROMPT, f"{intent} missing from SYSTEM_PROMPT"


class TestClassifyLang:
    @pytest.mark.asyncio
    async def test_parses_detected_lang(self):
        raw = '{"intent":"balance","params":{},"confidence":0.9,"lang":"kk-KZ"}'
        with patch.object(
            llm.client.chat.completions, "create",
            new=AsyncMock(return_value=_fake_completion(raw)),
        ):
            r = await llm.classify("балансым қанша", "s1")
        assert r.intent == "balance"
        assert r.lang == "kk-KZ"

    @pytest.mark.asyncio
    async def test_unsupported_lang_becomes_none(self):
        raw = '{"intent":"balance","params":{},"lang":"fr-FR"}'
        with patch.object(
            llm.client.chat.completions, "create",
            new=AsyncMock(return_value=_fake_completion(raw)),
        ):
            r = await llm.classify("solde", "s1")
        assert r.lang is None

    @pytest.mark.asyncio
    async def test_missing_lang_is_none(self):
        raw = '{"intent":"balance","params":{}}'
        with patch.object(
            llm.client.chat.completions, "create",
            new=AsyncMock(return_value=_fake_completion(raw)),
        ):
            r = await llm.classify("balance", "s1")
        assert r.lang is None


class TestExtractParam:
    @pytest.mark.asyncio
    async def test_extracts_value(self):
        with patch.object(
            llm.client.chat.completions, "create",
            new=AsyncMock(return_value=_fake_completion('{"value": "12"}')),
        ):
            assert await llm.extract_param("12 months", "deposit_open", "term", "en-US") == "12"

    @pytest.mark.asyncio
    async def test_null_value_returns_none(self):
        with patch.object(
            llm.client.chat.completions, "create",
            new=AsyncMock(return_value=_fake_completion('{"value": null}')),
        ):
            assert await llm.extract_param("hello there", "transfer", "amount", "en-US") is None

    @pytest.mark.asyncio
    async def test_blank_value_returns_none(self):
        with patch.object(
            llm.client.chat.completions, "create",
            new=AsyncMock(return_value=_fake_completion('{"value": "   "}')),
        ):
            assert await llm.extract_param("uh", "transfer", "amount", "en-US") is None

    @pytest.mark.asyncio
    async def test_unparseable_returns_none(self):
        with patch.object(
            llm.client.chat.completions, "create",
            new=AsyncMock(return_value=_fake_completion("not json")),
        ):
            assert await llm.extract_param("x", "transfer", "amount", "en-US") is None

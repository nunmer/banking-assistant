"""Unit tests for orchestrator/services/llm.py — pure parsing logic, no API calls."""
import json

import pytest

from orchestrator.services.llm import _parse
from orchestrator.models import IntentResult


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

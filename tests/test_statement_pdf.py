"""Unit tests for orchestrator/services/statement_pdf.py."""
import base64
from unittest.mock import AsyncMock, patch

import pytest

from orchestrator.services import statement_pdf

_ACCOUNT = {
    "account_id": "ACC-KZT-001",
    "currency": "KZT",
    "name": {"ru-RU": "Тенговый", "kk-KZ": "Теңгелік", "en-US": "Tenge"},
}


class TestMockRows:
    def test_deterministic_per_tx_id(self):
        rows_a = statement_pdf._mock_rows("MOCK-SAME1234", "month")
        rows_b = statement_pdf._mock_rows("MOCK-SAME1234", "month")
        assert rows_a == rows_b

    def test_different_tx_id_differs(self):
        rows_a = statement_pdf._mock_rows("MOCK-AAAA1111", "month")
        rows_b = statement_pdf._mock_rows("MOCK-BBBB2222", "month")
        assert rows_a != rows_b

    def test_rows_within_period_window(self):
        from datetime import datetime, timezone
        rows = statement_pdf._mock_rows("MOCK-WEEK0001", "week")
        now = datetime.now(timezone.utc)
        for row in rows:
            assert (now - row["date"]).days <= 7


class TestPeriodToDays:
    """Regression coverage: the real requested duration must drive the

    actual date range, not get silently collapsed to a fixed bucket (the
    "two months" bug — the client asked for 2 months and would have gotten a
    statement covering the wrong window)."""

    def test_arbitrary_counts_scale_correctly(self):
        assert statement_pdf._period_to_days("1 month") == 30
        assert statement_pdf._period_to_days("2 month") == 60
        assert statement_pdf._period_to_days("4 month") == 120
        assert statement_pdf._period_to_days("10 day") == 10
        assert statement_pdf._period_to_days("3 year") == 1095

    def test_quarter_is_ninety_days(self):
        assert statement_pdf._period_to_days("quarter") == 90

    def test_old_bare_bucket_words_still_supported(self):
        assert statement_pdf._period_to_days("week") == 7
        assert statement_pdf._period_to_days("month") == 30
        assert statement_pdf._period_to_days("year") == 365

    def test_unrecognized_value_falls_back_to_thirty_days(self):
        assert statement_pdf._period_to_days("nonsense") == 30
        assert statement_pdf._period_to_days("") == 30


class TestBuildPdf:
    @pytest.mark.parametrize("lang", ["ru-RU", "kk-KZ", "en-US"])
    def test_produces_valid_pdf_bytes(self, lang):
        pdf_bytes = statement_pdf._build("MOCK-ABCD1234", "month", _ACCOUNT, lang)
        assert pdf_bytes.startswith(b"%PDF")
        assert pdf_bytes.rstrip().endswith(b"%%EOF")
        assert len(pdf_bytes) > 500

    def test_no_account_falls_back_gracefully(self):
        # statement_pdf's account_id param is optional — must not crash when
        # the account lookup came back empty.
        pdf_bytes = statement_pdf._build("MOCK-NOACCT01", "month", None, "en-US")
        assert pdf_bytes.startswith(b"%PDF")

    def test_deterministic_content_per_tx_id(self):
        a = statement_pdf._build("MOCK-SAME5678", "month", _ACCOUNT, "ru-RU")
        b = statement_pdf._build("MOCK-SAME5678", "month", _ACCOUNT, "ru-RU")
        assert a == b

    def test_different_languages_produce_different_content(self):
        ru = statement_pdf._build("MOCK-LANGDIFF", "month", _ACCOUNT, "ru-RU")
        en = statement_pdf._build("MOCK-LANGDIFF", "month", _ACCOUNT, "en-US")
        assert ru != en


class TestGenerateAndStore:
    @pytest.mark.asyncio
    async def test_round_trip_through_redis(self):
        """generate_and_store then fetch returns the same bytes back."""
        store: dict[str, str] = {}

        async def fake_setex(key, ttl, value):
            store[key] = value

        async def fake_get(key):
            return store.get(key)

        with (
            patch.object(statement_pdf.redis, "setex", side_effect=fake_setex),
            patch.object(statement_pdf.redis, "get", side_effect=fake_get),
            patch(
                "orchestrator.services.accounts.list_accounts",
                new=AsyncMock(return_value=[_ACCOUNT]),
            ),
        ):
            ok = await statement_pdf.generate_and_store(
                tx_id="MOCK-ROUNDTRIP", session_id="s1",
                params={"period": "month"}, lang="ru-RU",
            )
            assert ok is True
            fetched = await statement_pdf.fetch("MOCK-ROUNDTRIP")

        assert fetched is not None
        assert fetched.startswith(b"%PDF")
        # Stored as base64 text, like the rest of this service layer's redis use.
        assert base64.b64decode(store[statement_pdf._key("MOCK-ROUNDTRIP")]) == fetched

    @pytest.mark.asyncio
    async def test_fetch_missing_returns_none(self):
        with patch.object(statement_pdf.redis, "get", new=AsyncMock(return_value=None)):
            assert await statement_pdf.fetch("MOCK-NOPE0000") is None

    @pytest.mark.asyncio
    async def test_generate_failure_is_best_effort(self):
        """A redis/account-lookup failure must return False, never raise —
        the caller (chat.py's _record_operation) must not have its reply
        broken by a PDF-generation problem."""
        with (
            patch.object(statement_pdf.redis, "setex", side_effect=RuntimeError("boom")),
            patch(
                "orchestrator.services.accounts.list_accounts",
                new=AsyncMock(return_value=[_ACCOUNT]),
            ),
        ):
            ok = await statement_pdf.generate_and_store(
                tx_id="MOCK-FAIL0001", session_id="s1",
                params={"period": "month"}, lang="ru-RU",
            )
        assert ok is False

    @pytest.mark.asyncio
    async def test_account_id_param_selects_matching_account(self):
        other = {"account_id": "ACC-USD-001", "currency": "USD", "name": {"en-US": "Dollar"}}
        captured = {}

        def fake_build(tx_id, period, account, lang):
            captured["account"] = account
            return b"%PDF-1.4\n%%EOF"

        with (
            patch.object(statement_pdf, "_build", side_effect=fake_build),
            patch.object(statement_pdf.redis, "setex", new=AsyncMock()),
            patch(
                "orchestrator.services.accounts.list_accounts",
                new=AsyncMock(return_value=[_ACCOUNT, other]),
            ),
        ):
            await statement_pdf.generate_and_store(
                tx_id="MOCK-PICKACCT", session_id="s1",
                params={"period": "month", "account_id": "ACC-USD-001"}, lang="en-US",
            )

        assert captured["account"]["account_id"] == "ACC-USD-001"

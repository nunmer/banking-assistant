"""Unit tests for account resolution and per-intent enrichment."""
from unittest.mock import AsyncMock, patch

import pytest

from orchestrator.services import accounts, enrich

_ACCOUNTS = [
    {"account_id": "ACC-KZT-001", "currency": "KZT",
     "name": {"ru-RU": "Тенговый", "kk-KZ": "Теңгелік", "en-US": "Tenge"}},
    {"account_id": "ACC-USD-001", "currency": "USD",
     "name": {"ru-RU": "Долларовый", "kk-KZ": "Долларлық", "en-US": "Dollar"}},
]


class TestAccounts:
    def test_find_by_kind_matches_currency(self):
        assert accounts.find_by_kind(_ACCOUNTS, "usd")["account_id"] == "ACC-USD-001"

    def test_find_by_kind_missing(self):
        assert accounts.find_by_kind(_ACCOUNTS, "EUR") is None

    def test_display_name_localised(self):
        assert accounts.display_name(_ACCOUNTS[0], "kk-KZ") == "Теңгелік"

    def test_display_name_falls_back_to_ru(self):
        assert accounts.display_name(_ACCOUNTS[0], "de-DE") == "Тенговый"


@pytest.mark.asyncio
class TestTransferOwnEnrich:
    async def test_resolves_ids_and_names(self):
        with patch.object(accounts, "list_accounts", new=AsyncMock(return_value=_ACCOUNTS)):
            params, err = await enrich.apply(
                "transfer_own", "u1",
                {"from_account_kind": "KZT", "to_account_kind": "USD", "amount": "10000"},
                "ru-RU",
            )
        assert err is None
        assert params["from_account_id"] == "ACC-KZT-001"
        assert params["to_account_id"] == "ACC-USD-001"
        assert params["from_account_name"] == "Тенговый"
        assert params["to_account_name"] == "Долларовый"
        assert params["amount"] == "10000"  # original params preserved

    async def test_unknown_kind_lists_available(self):
        with patch.object(accounts, "list_accounts", new=AsyncMock(return_value=_ACCOUNTS)):
            _, err = await enrich.apply(
                "transfer_own", "u1",
                {"from_account_kind": "GBP", "to_account_kind": "USD", "amount": "10"},
                "ru-RU",
            )
        assert err is not None
        assert "GBP" in err
        assert "Тенговый" in err and "Долларовый" in err  # available accounts shown

    async def test_same_account_rejected(self):
        with patch.object(accounts, "list_accounts", new=AsyncMock(return_value=_ACCOUNTS)):
            _, err = await enrich.apply(
                "transfer_own", "u1",
                {"from_account_kind": "KZT", "to_account_kind": "KZT", "amount": "10"},
                "ru-RU",
            )
        assert err is not None
        assert "один и тот же" in err

    async def test_lookup_failure_friendly_error(self):
        with patch.object(accounts, "list_accounts", new=AsyncMock(return_value=[])):
            _, err = await enrich.apply(
                "transfer_own", "u1",
                {"from_account_kind": "KZT", "to_account_kind": "USD", "amount": "10"},
                "en-US",
            )
        assert err is not None
        assert "couldn't load" in err

    async def test_unregistered_intent_passes_through(self):
        params = {"amount": "5"}
        out, err = await enrich.apply("balance", "u1", params, "ru-RU")
        assert err is None
        assert out == params

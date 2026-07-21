"""Unit tests for compact operation summaries."""
from orchestrator.services import opsummary


class TestShort:
    def test_transfer_phone_ru(self):
        out = opsummary.short(
            "transfer_phone",
            {"phone": "87758155576", "amount": "5000", "currency": "KZT"},
            "ru-RU",
        )
        assert out == "Перевод 5000 тенге → 8 (775) 815 55 76"

    def test_transfer_phone_without_currency(self):
        out = opsummary.short(
            "transfer_phone", {"phone": "87758155576", "amount": "5000"}, "ru-RU"
        )
        assert out == "Перевод 5000 → 8 (775) 815 55 76"

    def test_transfer_own_uses_account_names(self):
        out = opsummary.short(
            "transfer_own",
            {"amount": "10000", "from_account_name": "Тенговый",
             "to_account_name": "Долларовый", "from_account_kind": "KZT",
             "to_account_kind": "USD"},
            "ru-RU",
        )
        assert out == "Перевод 10000: Тенговый → Долларовый"

    def test_transfer_kk(self):
        out = opsummary.short(
            "transfer", {"amount": "500", "currency": "USD", "to_account": "KZ123"}, "kk-KZ"
        )
        assert out == "Аударым 500 доллар → KZ123"

    def test_card_block(self):
        assert opsummary.short("card_block", {"card_last4": "4321"}, "ru-RU") == \
            "Блокировка карты •• 4321"

    def test_deposit_en(self):
        out = opsummary.short("deposit_open", {"amount": "100000", "term": "12"}, "en-US")
        assert out == "Deposit 100000, 12 mo"

    def test_no_question_mark_ever(self):
        # The whole point: history entries are records, not questions.
        for intent in ("transfer", "transfer_own", "transfer_phone", "payment",
                       "deposit_open", "card_block", "card_limit", "certificate"):
            assert "?" not in opsummary.short(intent, {"amount": "1"}, "ru-RU")

    def test_unknown_intent_falls_back_to_intent(self):
        assert opsummary.short("mystery_op", {}, "ru-RU") == "mystery_op"

    def test_balance_label_only(self):
        assert opsummary.short("balance", {}, "kk-KZ") == "Баланс"

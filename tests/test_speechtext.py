"""Unit tests for speechtext rendering — currency/enum words + identifier spell-out."""
from orchestrator.services import speechtext


class TestForDisplay:
    def test_currency_localized(self):
        out = speechtext.for_display({"amount": "100", "currency": "KZT"}, "ru-RU")
        assert out["currency"] == "тенге"
        assert out["amount"] == "100"  # non-enum untouched

    def test_currency_localized_en(self):
        assert speechtext.for_display({"currency": "USD"}, "en-US")["currency"] == "dollar"

    def test_account_kinds_localized(self):
        out = speechtext.for_display(
            {"from_account_kind": "KZT", "to_account_kind": "USD"}, "ru-RU"
        )
        assert out["from_account_kind"] == "тенге"
        assert out["to_account_kind"] == "доллар"

    def test_limit_period_cert_localized(self):
        assert speechtext.for_display({"limit_kind": "daily"}, "ru-RU")["limit_kind"] == "суточный"
        assert speechtext.for_display({"period": "month"}, "ru-RU")["period"] == "месяц"
        assert (
            speechtext.for_display({"cert_kind": "no_debt"}, "ru-RU")["cert_kind"]
            == "об отсутствии задолженности"
        )

    def test_unknown_value_passthrough(self):
        assert speechtext.for_display({"currency": "GBP"}, "ru-RU")["currency"] == "GBP"

    def test_identifier_not_spelled_in_display(self):
        assert speechtext.for_display({"to_account": "KZ123"}, "ru-RU")["to_account"] == "KZ123"


class TestForSpeech:
    def test_currency_word_and_identifier_spelled(self):
        out = speechtext.for_speech({"currency": "KZT", "to_account": "KZ12"}, "ru-RU")
        assert out["currency"] == "тенге"
        assert out["to_account"] == "K Z 1 2"

    def test_card_last4_spelled(self):
        assert speechtext.for_speech({"card_last4": "4321"}, "ru-RU")["card_last4"] == "4 3 2 1"

    def test_amount_untouched(self):
        assert speechtext.for_speech({"amount": "500"}, "en-US")["amount"] == "500"

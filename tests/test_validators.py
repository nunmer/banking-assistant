"""Unit tests for parameter validation at the confirmation boundary."""
from orchestrator.services import validators


class TestPhone:
    def test_local_10_digits(self):
        assert validators.is_valid("phone", "7012345678")

    def test_with_8_prefix(self):
        assert validators.is_valid("phone", "87012345678")

    def test_with_plus7_and_spaces(self):
        assert validators.is_valid("phone", "+7 701 234 5678")

    def test_name_rejected(self):
        # The bug this guards: a person's name where a number belongs.
        assert not validators.is_valid("phone", "Aidar")

    def test_too_short_rejected(self):
        assert not validators.is_valid("phone", "12345")

    def test_10_digits_not_starting_with_7_rejected(self):
        # KZ national numbers always start with 7; guards the numwords
        # reassembly from accepting a bogus 10-digit reading.
        assert not validators.is_valid("phone", "8700433202")

    def test_11_digits_without_7_after_trunk_rejected(self):
        assert not validators.is_valid("phone", "88012345678")

    def test_empty_rejected(self):
        assert not validators.is_valid("phone", "")


class TestAmount:
    def test_positive(self):
        assert validators.is_valid("amount", "1500")

    def test_zero_rejected(self):
        assert not validators.is_valid("amount", "0")

    def test_word_rejected(self):
        assert not validators.is_valid("amount", "много")


class TestCardLast4:
    def test_four_digits(self):
        assert validators.is_valid("card_last4", "4321")

    def test_wrong_length_rejected(self):
        assert not validators.is_valid("card_last4", "432")

    def test_letters_rejected(self):
        assert not validators.is_valid("card_last4", "abcd")


class TestUnvalidatedPassthrough:
    def test_unknown_param_present_ok(self):
        # Params without a validator (to_account, etc.) pass through if present.
        assert validators.is_valid("to_account", "KZ123")

    def test_none_rejected(self):
        assert not validators.is_valid("to_account", None)

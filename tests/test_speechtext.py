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


class TestPeriodDuration:
    """Regression coverage for the "two months" bug: period must keep the

    real requested count (any number, not just the reported "2"), localized
    per language — Russian via a declension-dodging abbreviation, Kazakh
    unchanged (no noun inflection by count), English with plain pluralization.
    """

    def test_arbitrary_counts_all_work_not_just_two(self):
        for n in ("1", "2", "3", "4", "17"):
            out = speechtext.for_display({"period": f"{n} month"}, "ru-RU")["period"]
            assert out == f"{n} мес."

    def test_russian_uses_declension_free_abbreviation(self):
        assert speechtext.for_display({"period": "2 month"}, "ru-RU")["period"] == "2 мес."
        assert speechtext.for_display({"period": "10 day"}, "ru-RU")["period"] == "10 дн."
        assert speechtext.for_display({"period": "1 week"}, "ru-RU")["period"] == "1 нед."
        assert speechtext.for_display({"period": "3 year"}, "ru-RU")["period"] == "3 г."

    def test_kazakh_noun_unchanged_regardless_of_count(self):
        assert speechtext.for_display({"period": "2 month"}, "kk-KZ")["period"] == "2 ай"
        assert speechtext.for_display({"period": "5 month"}, "kk-KZ")["period"] == "5 ай"

    def test_english_pluralizes_unless_exactly_one(self):
        assert speechtext.for_display({"period": "1 month"}, "en-US")["period"] == "1 month"
        assert speechtext.for_display({"period": "2 month"}, "en-US")["period"] == "2 months"

    def test_quarter_still_a_literal_word_not_three_months(self):
        assert speechtext.for_display({"period": "quarter"}, "ru-RU")["period"] == "квартал"
        assert speechtext.for_display({"period": "quarter"}, "kk-KZ")["period"] == "тоқсан"

    def test_old_bare_bucket_words_still_supported(self):
        # Backward-compat: a pending confirmation created before this format
        # change might still carry the old single-word value.
        assert speechtext.for_display({"period": "week"}, "ru-RU")["period"] == "неделю"
        assert speechtext.for_display({"period": "year"}, "kk-KZ")["period"] == "жыл"


class TestPeriodSpeechVsDisplay:
    """Regression coverage: Yandex TTS reads the Russian display abbreviation

    ("3 мес.") close to literally ("mies"), not expanded to the real word —
    so the speech variant must use the full, correctly-declined word instead.
    Kazakh/English need no divergence (already full words either way).
    """

    def test_russian_speech_uses_full_declined_word_not_the_abbreviation(self):
        out = speechtext.for_speech({"period": "3 month"}, "ru-RU")["period"]
        assert out == "3 месяца"
        assert "мес." not in out

    def test_russian_numeral_agreement_one_few_many(self):
        # one (ends in 1, not 11): accusative singular
        assert speechtext.for_speech({"period": "1 month"}, "ru-RU")["period"] == "1 месяц"
        assert speechtext.for_speech({"period": "21 month"}, "ru-RU")["period"] == "21 месяц"
        # few (ends in 2-4, not 12-14): genitive singular
        assert speechtext.for_speech({"period": "2 month"}, "ru-RU")["period"] == "2 месяца"
        assert speechtext.for_speech({"period": "4 month"}, "ru-RU")["period"] == "4 месяца"
        assert speechtext.for_speech({"period": "22 month"}, "ru-RU")["period"] == "22 месяца"
        # many (0, 5-20, ...): genitive plural
        assert speechtext.for_speech({"period": "5 month"}, "ru-RU")["period"] == "5 месяцев"
        assert speechtext.for_speech({"period": "11 month"}, "ru-RU")["period"] == "11 месяцев"
        assert speechtext.for_speech({"period": "14 month"}, "ru-RU")["period"] == "14 месяцев"

    def test_russian_all_units_have_full_speech_forms(self):
        assert speechtext.for_speech({"period": "1 day"}, "ru-RU")["period"] == "1 день"
        assert speechtext.for_speech({"period": "2 day"}, "ru-RU")["period"] == "2 дня"
        assert speechtext.for_speech({"period": "5 day"}, "ru-RU")["period"] == "5 дней"
        assert speechtext.for_speech({"period": "1 week"}, "ru-RU")["period"] == "1 неделю"
        assert speechtext.for_speech({"period": "2 week"}, "ru-RU")["period"] == "2 недели"
        assert speechtext.for_speech({"period": "5 week"}, "ru-RU")["period"] == "5 недель"
        assert speechtext.for_speech({"period": "1 year"}, "ru-RU")["period"] == "1 год"
        assert speechtext.for_speech({"period": "2 year"}, "ru-RU")["period"] == "2 года"
        assert speechtext.for_speech({"period": "5 year"}, "ru-RU")["period"] == "5 лет"  # irregular

    def test_kazakh_and_english_speech_match_display(self):
        assert (
            speechtext.for_speech({"period": "2 month"}, "kk-KZ")["period"]
            == speechtext.for_display({"period": "2 month"}, "kk-KZ")["period"]
        )
        assert (
            speechtext.for_speech({"period": "2 month"}, "en-US")["period"]
            == speechtext.for_display({"period": "2 month"}, "en-US")["period"]
        )


class TestTermUnit:
    """Regression coverage for the "7 мес." mispronunciation bug: the

    deposit_open confirm template hardcodes the unit word as static text
    next to {term} in kk-KZ/en-US (already correct for any count), but
    ru-RU needs a rendered, numeral-agreeing {term_unit} instead — same
    "mies" mispronunciation class as the period bug, on a different param.
    """

    def test_display_uses_the_abbreviation(self):
        assert speechtext.for_display({"term": "7", "amount": "100"}, "ru-RU")["term_unit"] == "мес."
        assert speechtext.for_display({"term": "1", "amount": "100"}, "ru-RU")["term_unit"] == "мес."

    def test_speech_uses_full_declined_word_not_the_abbreviation(self):
        out = speechtext.for_speech({"term": "7", "amount": "100"}, "ru-RU")["term_unit"]
        assert out == "месяцев"
        assert "мес." not in out

    def test_speech_numeral_agreement_one_few_many(self):
        assert speechtext.for_speech({"term": "1"}, "ru-RU")["term_unit"] == "месяц"
        assert speechtext.for_speech({"term": "2"}, "ru-RU")["term_unit"] == "месяца"
        assert speechtext.for_speech({"term": "5"}, "ru-RU")["term_unit"] == "месяцев"
        assert speechtext.for_speech({"term": "11"}, "ru-RU")["term_unit"] == "месяцев"
        assert speechtext.for_speech({"term": "21"}, "ru-RU")["term_unit"] == "месяц"

    def test_kazakh_and_english_get_no_term_unit_since_their_templates_dont_use_it(self):
        assert speechtext.for_display({"term": "7"}, "kk-KZ")["term_unit"] == ""
        assert speechtext.for_speech({"term": "7"}, "en-US")["term_unit"] == ""

    def test_absent_when_term_not_in_params(self):
        assert "term_unit" not in speechtext.for_display({"amount": "100"}, "ru-RU")
        assert "term_unit" not in speechtext.for_speech({"amount": "100"}, "ru-RU")


class TestForSpeech:
    def test_currency_word_and_identifier_spelled(self):
        out = speechtext.for_speech({"currency": "KZT", "to_account": "KZ12"}, "ru-RU")
        assert out["currency"] == "тенге"
        assert out["to_account"] == "K Z 1 2"

    def test_card_last4_spelled(self):
        assert speechtext.for_speech({"card_last4": "4321"}, "ru-RU")["card_last4"] == "4 3 2 1"

    def test_amount_untouched(self):
        assert speechtext.for_speech({"amount": "500"}, "en-US")["amount"] == "500"


class TestPhone:
    def test_display_grouped_from_plus7(self):
        assert speechtext.format_phone("+77755437575") == "8 (775) 543 75 75"

    def test_display_grouped_from_10_digits(self):
        assert speechtext.format_phone("7755437575") == "8 (775) 543 75 75"

    def test_speech_groups_as_numbers(self):
        # Comma-separated groups so TTS reads whole numbers, not digit-by-digit.
        assert speechtext.format_phone("87755437575", for_speech=True) == "8, 775, 543, 75, 75"

    def test_speech_kazakh_trunk_is_a_word(self):
        # Kazakh reads a bare leading "8" as an ordinal ("8 times"); use the word.
        assert (
            speechtext.format_phone("87755437575", for_speech=True, lang="kk-KZ")
            == "сегіз, 775, 543, 75, 75"
        )

    def test_speech_russian_keeps_digit_trunk(self):
        assert (
            speechtext.format_phone("87755437575", for_speech=True, lang="ru-RU")
            == "8, 775, 543, 75, 75"
        )

    def test_for_display_formats_phone(self):
        out = speechtext.for_display({"phone": "+77012345678", "amount": "5000"}, "ru-RU")
        assert out["phone"] == "8 (701) 234 56 78"
        assert out["amount"] == "5000"

    def test_for_speech_groups_phone(self):
        assert speechtext.for_speech({"phone": "+77012345678"}, "ru-RU")["phone"] == "8, 701, 234, 56, 78"

    def test_for_speech_groups_phone_kazakh(self):
        assert (
            speechtext.for_speech({"phone": "+77012345678"}, "kk-KZ")["phone"]
            == "сегіз, 701, 234, 56, 78"
        )

    def test_unexpected_shape_falls_back(self):
        assert speechtext.format_phone("12345") == "12345"  # display: raw
        assert speechtext.format_phone("12345", for_speech=True) == "1 2 3 4 5"  # speech: spelled

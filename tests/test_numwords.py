"""Unit tests for deterministic spoken-number → digits conversion."""
from orchestrator.services import numwords

# The exact number from the reported bug, dictated in Kazakh.
_KK_PHONE_WORDS = (
    "сегіз жеті жүз жетпіс бес сегіз жүз он бес елу бес жетпіс алты"
)
_RU_PHONE_WORDS = (
    "восемь семьсот семьдесят пять восемьсот пятнадцать пятьдесят пять семьдесят шесть"
)


class TestSpokenToDigitsKazakh:
    def test_phone_groups(self):
        assert numwords.spoken_to_digits(_KK_PHONE_WORDS, "kk-KZ") == "8 775 815 55 76"

    def test_amount_with_thousand(self):
        assert numwords.spoken_to_digits("бес мың теңге", "kk-KZ") == "5000 теңге"

    def test_teen_composed(self):
        assert numwords.spoken_to_digits("он бес", "kk-KZ") == "15"

    def test_hundred_multiplier(self):
        assert numwords.spoken_to_digits("екі жүз", "kk-KZ") == "200"
        assert numwords.spoken_to_digits("жүз", "kk-KZ") == "100"

    def test_two_bare_units_split(self):
        assert numwords.spoken_to_digits("сегіз жеті", "kk-KZ") == "8 7"

    def test_non_number_words_untouched(self):
        assert numwords.spoken_to_digits("менің балансым қанша", "kk-KZ") == "менің балансым қанша"

    def test_full_transcript(self):
        text = f"{_KK_PHONE_WORDS} нөміріне бес мың теңге аудару керек"
        assert (
            numwords.spoken_to_digits(text, "kk-KZ")
            == "8 775 815 55 76 нөміріне 5000 теңге аудару керек"
        )


class TestSpokenToDigitsRussian:
    def test_phone_groups(self):
        assert numwords.spoken_to_digits(_RU_PHONE_WORDS, "ru-RU") == "8 775 815 55 76"

    def test_amount_with_thousand(self):
        assert numwords.spoken_to_digits("пять тысяч тенге", "ru-RU") == "5000 тенге"

    def test_teen_single_word(self):
        assert numwords.spoken_to_digits("пятнадцать", "ru-RU") == "15"

    def test_kazakh_on_not_parsed_as_russian(self):
        # "он" is Kazakh 10 but the Russian pronoun "he" — must stay a word in ru.
        assert numwords.spoken_to_digits("он хочет перевести", "ru-RU") == "он хочет перевести"


class TestPhoneFromText:
    def test_kazakh_dictated(self):
        text = f"{_KK_PHONE_WORDS} нөміріне бес мың теңге аудару керек"
        assert numwords.phone_from_text(text, "kk-KZ") == "87758155576"

    def test_russian_dictated(self):
        assert numwords.phone_from_text(_RU_PHONE_WORDS, "ru-RU") == "87758155576"

    def test_typed_plus7_groups(self):
        assert numwords.phone_from_text("+7 701 234 5678", "ru-RU") == "7012345678"

    def test_typed_grouped_digits(self):
        assert numwords.phone_from_text("8 775 815 55 76", "kk-KZ") == "87758155576"

    def test_amount_only_is_not_a_phone(self):
        assert numwords.phone_from_text("бес мың теңге аудар", "kk-KZ") is None

    def test_no_number_returns_none(self):
        assert numwords.phone_from_text("баланс", "kk-KZ") is None

    def test_english_digits_still_found(self):
        # Even without a lexicon, a typed digit run is recovered.
        assert numwords.phone_from_text("call 87758155576 please", "en-US") == "87758155576"


class TestMergedGroupAmbiguity:
    """"400, 33" and "433" are the same spoken words — the phone shape decides.

    Guards the reported bug: 8 700 400 33 22 was recognized as 8 700 433 22
    (the 400/33 boundary merged, silently dropping two digits).
    """

    def test_kazakh_dictated_merged_hundreds(self):
        kk = "сегіз жеті жүз төрт жүз отыз үш жиырма екі"
        assert numwords.phone_from_text(kk, "kk-KZ") == "87004003322"

    def test_russian_dictated_merged_hundreds(self):
        ru = "восемь семьсот четыреста тридцать три двадцать два"
        assert numwords.phone_from_text(ru, "ru-RU") == "87004003322"

    def test_pre_merged_digits_recovered(self):
        # STT/LLM may hand us the already-merged digits; still recoverable.
        assert numwords.phone_from_text("8 700 433 22", "kk-KZ") == "87004003322"

    def test_kazakh_adjacent_hundreds_split(self):
        # "жеті жүз төрт жүз" is 700 then 400 — the 4 multiplies the new
        # hundred, it does not extend the previous number to 704.
        assert numwords.spoken_to_digits("жеті жүз төрт жүз", "kk-KZ") == "700 400"

    def test_valid_number_never_altered(self):
        # A concatenation that is already a valid phone wins over any expansion.
        assert numwords.phone_from_text("8 775 815 55 76", "kk-KZ") == "87758155576"

    def test_incomplete_number_not_invented(self):
        # Too few digits stays unrecognized — no expansion fabricates a phone.
        assert numwords.phone_from_text("8 700 433", "kk-KZ") is None

"""Render parameter values for human-facing text and for speech.

Two concerns:
- Localise "enum" params (currency codes, limit kinds, periods, certificate
  kinds) to natural words, so "KZT" reads and is spoken as "тенге" rather than
  the letters "K-Z-T" — for both the on-screen message and the TTS variant.
- Spell out identifiers (account/card/phone/bill numbers) digit-by-digit in the
  TTS variant only, so they are read one character at a time.
"""

import re

DEFAULT_LANG = "ru-RU"

# Params whose values are identifiers, not quantities — spelled out for TTS.
# `phone` is handled separately (grouped, not digit-by-digit).
IDENTIFIER_PARAMS = frozenset({"to_account", "account_id", "bill_id", "card_last4"})

# Trunk-prefix word for the spoken phone number. The leading "8" must be a WORD
# for Kazakh TTS: as a bare digit before the first group ("8, 775") the Kazakh
# normaliser reads it as an ordinal + counter ("сегізінші рет" ≈ "8 times 775").
# Russian/English read the digit correctly, so they keep "8".
_TRUNK_WORD = {"kk": "сегіз"}

# Currency-code params, localised to a spoken/written word.
_CURRENCY_WORDS = {
    "ru-RU": {"KZT": "тенге", "USD": "доллар", "EUR": "евро", "RUB": "рубль"},
    "kk-KZ": {"KZT": "теңге", "USD": "доллар", "EUR": "еуро", "RUB": "рубль"},
    "en-US": {"KZT": "tenge", "USD": "dollar", "EUR": "euro", "RUB": "ruble"},
}

_LIMIT_KIND_WORDS = {
    "ru-RU": {"daily": "суточный", "monthly": "месячный"},
    "kk-KZ": {"daily": "тәуліктік", "monthly": "айлық"},
    "en-US": {"daily": "daily", "monthly": "monthly"},
}

_PERIOD_WORDS = {
    "ru-RU": {"week": "неделю", "month": "месяц", "quarter": "квартал", "year": "год"},
    "kk-KZ": {"week": "апта", "month": "ай", "quarter": "тоқсан", "year": "жыл"},
    "en-US": {"week": "the week", "month": "the month", "quarter": "the quarter", "year": "the year"},
}

# "period" values from the LLM are either the literal "quarter" or "<count>
# <unit>" (see llm.py's prompt) — a real duration, not one of 4 fixed
# buckets. For DISPLAY, Russian uses an abbreviation that doesn't need to
# agree with the number in gender/case (same trick this codebase already
# uses for deposit term months — see opsummary.py's _MONTHS) — reading "3
# мес." on screen is natural. TTS is a different story: Yandex's synthesiser
# reads an abbreviation like "мес." close to literally ("mies"), not
# expanded to the real word — so the SPEECH variant needs the actual,
# correctly-declined Russian word (see _RU_DURATION_FORMS below). Kazakh
# nouns don't inflect for count at all, so no special-casing needed there
# either way; English just needs a trailing "s" for anything but 1.
_DURATION_UNIT_WORDS = {
    "ru-RU": {"day": "дн.", "week": "нед.", "month": "мес.", "year": "г."},
    "kk-KZ": {"day": "күн", "week": "апта", "month": "ай", "year": "жыл"},
    "en-US": {"day": "day", "week": "week", "month": "month", "year": "year"},
}
_DURATION_RE = re.compile(r"^(\d+)\s+(day|week|month|year)$")

# Full Russian words for TTS, one triple per unit: (one, few, many) —
# accusative singular (after "за", matches a bare count of 1: "за месяц"),
# genitive singular (counts ending 2-4, e.g. "за 2 месяца" — Russian numerals
# 2/3/4 always take genitive singular regardless of the governing case), and
# genitive plural (everything else: 0, 5-20, ...25, ... — e.g. "за 5 месяцев").
# "year" is irregular: the idiomatic plural-genitive is "лет", not "годов".
_RU_DURATION_FORMS = {
    "day": ("день", "дня", "дней"),
    "week": ("неделю", "недели", "недель"),
    "month": ("месяц", "месяца", "месяцев"),
    "year": ("год", "года", "лет"),
}


def _ru_plural_index(n: int) -> int:
    """0/1/2 → (one, few, many) per standard Russian numeral-noun agreement."""
    if n % 100 in (11, 12, 13, 14):
        return 2
    last = n % 10
    if last == 1:
        return 0
    if last in (2, 3, 4):
        return 1
    return 2


def _term_unit_word(value: str, lang: str, for_speech: bool) -> str:
    """The unit word for a deposit term — always months (see llm.py's

    prompt: "term: deposit term in months"). Confirm templates originally
    hardcoded the unit word as static text next to {term} (kk-KZ: "{term}
    айға", en-US: "{term}-month") — both grammatically fine for any count
    as-is, unlike Russian, which genuinely needs numeral-noun agreement.
    Rather than duplicate the abbreviation-vs-full-word split "period"
    already has, only the ru-RU template routes its unit word through this
    (as a separate {term_unit} placeholder) — kk-KZ/en-US ignore it, since
    `str.format` silently ignores unused kwargs.
    """
    if lang != "ru-RU":
        return ""
    try:
        n = int(value)
    except (TypeError, ValueError):
        return _DURATION_UNIT_WORDS["ru-RU"]["month"]
    if for_speech:
        return _RU_DURATION_FORMS["month"][_ru_plural_index(n)]
    return _DURATION_UNIT_WORDS["ru-RU"]["month"]


_CERT_KIND_WORDS = {
    "ru-RU": {"account": "о счёте", "no_debt": "об отсутствии задолженности", "balance": "о балансе"},
    "kk-KZ": {"account": "шот туралы", "no_debt": "берешегі жоқтығы туралы", "balance": "баланс туралы"},
    "en-US": {"account": "account", "no_debt": "no-debt", "balance": "balance"},
}

# param name -> its localisation table. Currency codes are upper-cased before
# lookup; the rest are lower-cased.
_LOCALIZED = {
    "currency": _CURRENCY_WORDS,
    "from_account_kind": _CURRENCY_WORDS,
    "to_account_kind": _CURRENCY_WORDS,
    "limit_kind": _LIMIT_KIND_WORDS,
    "period": _PERIOD_WORDS,
    "cert_kind": _CERT_KIND_WORDS,
}


def spell_out(value: str) -> str:
    """Space out alphanumerics so TTS reads them one character at a time."""
    return " ".join(ch for ch in str(value) if not ch.isspace())


def format_phone(value: str, for_speech: bool = False, lang: str = DEFAULT_LANG) -> str:
    """Format a Kazakhstan phone number in the local grouped style.

    Display:  8 (775) 543 75 75
    Speech:   8, 775, 543, 75, 75  — comma-separated groups so TTS reads each as
              a whole number ("семьсот семьдесят пять"), not merged or spelled
              digit-by-digit. For Kazakh the leading trunk prefix is the word
              "сегіз" rather than the digit 8 (see `_TRUNK_WORD`).
    Falls back to the raw value (display) / spelled-out digits (speech) if the
    number isn't the expected 10-digit KZ shape.
    """
    digits = re.sub(r"\D", "", str(value))
    if len(digits) == 11 and digits[0] in "78":
        rest = digits[1:]
    elif len(digits) == 10:
        rest = digits
    else:
        rest = ""
    if len(rest) != 10:
        return spell_out(value) if for_speech else str(value)
    a, b, c, d = rest[:3], rest[3:6], rest[6:8], rest[8:10]
    if for_speech:
        trunk = _TRUNK_WORD.get((lang or "")[:2].lower(), "8")
        return f"{trunk}, {a}, {b}, {c}, {d}"
    return f"8 ({a}) {b} {c} {d}"


def _localize(param: str, value: str, lang: str, for_speech: bool = False) -> str:
    """Map an enum-like value to its natural word, or return it unchanged."""
    if param == "period":
        return _localize_period(value, lang, for_speech=for_speech)
    table = _LOCALIZED[param].get(lang) or _LOCALIZED[param].get(DEFAULT_LANG, {})
    v = str(value)
    return table.get(v) or table.get(v.upper()) or table.get(v.lower()) or v


def _localize_period(value: str, lang: str, for_speech: bool = False) -> str:
    """"quarter", or an arbitrary "<count> <unit>" duration — any count, not

    a fixed set of them (see llm.py's prompt). Falls back to the bare-word
    tables for a still-in-flight pre-existing value using the old
    week/month/year single-bucket format, or to the raw value unchanged.
    """
    v = str(value).strip()
    words = _PERIOD_WORDS.get(lang) or _PERIOD_WORDS[DEFAULT_LANG]
    if v.lower() == "quarter":
        return words.get("quarter", v)
    m = _DURATION_RE.match(v)
    if m:
        count, unit = m.group(1), m.group(2)
        if for_speech and lang == "ru-RU":
            word = _RU_DURATION_FORMS[unit][_ru_plural_index(int(count))]
            return f"{count} {word}"
        unit_words = _DURATION_UNIT_WORDS.get(lang) or _DURATION_UNIT_WORDS[DEFAULT_LANG]
        word = unit_words[unit]
        if lang == "en-US" and count != "1":
            word += "s"
        return f"{count} {word}"
    return words.get(v.lower(), v)


def for_display(params: dict, lang: str) -> dict:
    """Params for the on-screen message: enum words + grouped phone number."""
    out = {}
    for key, val in params.items():
        if key == "phone":
            out[key] = format_phone(val, for_speech=False)
        elif key in _LOCALIZED:
            out[key] = _localize(key, val, lang)
        else:
            out[key] = val
    if "term" in params:
        out["term_unit"] = _term_unit_word(params["term"], lang, for_speech=False)
    return out


def for_speech(params: dict, lang: str) -> dict:
    """Params for the TTS variant: enum words, grouped phone, identifiers spelled out."""
    out = {}
    for key, val in params.items():
        if key == "phone":
            out[key] = format_phone(val, for_speech=True, lang=lang)
        elif key in _LOCALIZED:
            out[key] = _localize(key, val, lang, for_speech=True)
        elif key in IDENTIFIER_PARAMS:
            out[key] = spell_out(val)
        else:
            out[key] = val
    if "term" in params:
        out["term_unit"] = _term_unit_word(params["term"], lang, for_speech=True)
    return out

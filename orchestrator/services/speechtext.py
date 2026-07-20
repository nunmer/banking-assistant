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


def format_phone(value: str, for_speech: bool = False) -> str:
    """Format a Kazakhstan phone number in the local grouped style.

    Display:  8 (775) 543 75 75
    Speech:   8, 775, 543, 75, 75  — comma-separated groups so TTS reads each as
              a whole number ("семьсот семьдесят пять"), not merged or spelled
              digit-by-digit.
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
        return f"8, {a}, {b}, {c}, {d}"
    return f"8 ({a}) {b} {c} {d}"


def _localize(param: str, value: str, lang: str) -> str:
    """Map an enum-like value to its natural word, or return it unchanged."""
    table = _LOCALIZED[param].get(lang) or _LOCALIZED[param].get(DEFAULT_LANG, {})
    v = str(value)
    return table.get(v) or table.get(v.upper()) or table.get(v.lower()) or v


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
    return out


def for_speech(params: dict, lang: str) -> dict:
    """Params for the TTS variant: enum words, grouped phone, identifiers spelled out."""
    out = {}
    for key, val in params.items():
        if key == "phone":
            out[key] = format_phone(val, for_speech=True)
        elif key in _LOCALIZED:
            out[key] = _localize(key, val, lang)
        elif key in IDENTIFIER_PARAMS:
            out[key] = spell_out(val)
        else:
            out[key] = val
    return out

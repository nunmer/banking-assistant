"""Render parameter values for human-facing text and for speech.

Two concerns:
- Localise "enum" params (currency codes, limit kinds, periods, certificate
  kinds) to natural words, so "KZT" reads and is spoken as "тенге" rather than
  the letters "K-Z-T" — for both the on-screen message and the TTS variant.
- Spell out identifiers (account/card/phone/bill numbers) digit-by-digit in the
  TTS variant only, so they are read one character at a time.
"""

DEFAULT_LANG = "ru-RU"

# Params whose values are identifiers, not quantities — spelled out for TTS.
IDENTIFIER_PARAMS = frozenset(
    {"to_account", "account_id", "bill_id", "phone", "card_last4"}
)

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


def _localize(param: str, value: str, lang: str) -> str:
    """Map an enum-like value to its natural word, or return it unchanged."""
    table = _LOCALIZED[param].get(lang) or _LOCALIZED[param].get(DEFAULT_LANG, {})
    v = str(value)
    return table.get(v) or table.get(v.upper()) or table.get(v.lower()) or v


def for_display(params: dict, lang: str) -> dict:
    """Params for the on-screen message: enum values as natural words."""
    return {
        key: _localize(key, val, lang) if key in _LOCALIZED else val
        for key, val in params.items()
    }


def for_speech(params: dict, lang: str) -> dict:
    """Params for the TTS variant: enum words + identifiers spelled out."""
    out = {}
    for key, val in params.items():
        if key in _LOCALIZED:
            out[key] = _localize(key, val, lang)
        elif key in IDENTIFIER_PARAMS:
            out[key] = spell_out(val)
        else:
            out[key] = val
    return out

"""Build TTS-friendly variants of user-facing messages.

Account numbers, phone numbers, and bill IDs should be read out one character
at a time ("eight seven zero …") rather than as a single huge number. Amounts
are left alone so "500" is still read as "five hundred".
"""

# Params whose values are identifiers, not quantities.
IDENTIFIER_PARAMS = frozenset(
    {"to_account", "account_id", "bill_id", "phone", "card_last4"}
)


def spell_out(value: str) -> str:
    """Space out alphanumerics so TTS reads them one character at a time."""
    return " ".join(ch for ch in str(value) if not ch.isspace())


def speech_params(params: dict) -> dict:
    """Return params with identifier values spelled out for synthesis."""
    return {
        key: spell_out(val) if key in IDENTIFIER_PARAMS else val
        for key, val in params.items()
    }

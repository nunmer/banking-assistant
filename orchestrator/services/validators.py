"""Parameter validation at the confirmation boundary.

A parameter counts as satisfied only if it is present AND well-formed. This
stops obviously-wrong values (a name where a phone number belongs, letters where
an amount belongs) from reaching the confirmation/MIB call — instead the user is
re-asked. Only params with a clear machine-checkable shape are validated; free
/enum values (currency, account kinds, period, …) are left to the LLM + render
layer.
"""
import re


def _digits(value: str) -> str:
    return re.sub(r"\D", "", str(value))


def _valid_phone(value: str) -> bool:
    # Kazakhstan: 10 local digits, or 11 with an 8/7 country prefix.
    d = _digits(value)
    return len(d) == 10 or (len(d) == 11 and d[0] in "78")


def _positive_int(value: str) -> bool:
    v = str(value).strip().replace(" ", "")
    return v.isdigit() and int(v) > 0


def _card_last4(value: str) -> bool:
    v = str(value).strip()
    return v.isdigit() and len(v) == 4


_VALIDATORS = {
    "phone": _valid_phone,
    "amount": _positive_int,
    "limit_amount": _positive_int,
    "term": _positive_int,
    "limit": lambda v: str(v).strip().isdigit(),
    "card_last4": _card_last4,
}


def is_valid(param: str, value) -> bool:
    """True if `value` is present and well-formed for `param`."""
    if value is None or str(value).strip() == "":
        return False
    validator = _VALIDATORS.get(param)
    return validator(str(value)) if validator else True

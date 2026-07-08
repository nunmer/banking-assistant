"""Detect yes/no replies to a pending confirmation, in Kazakh, Russian, English.

Used so a spoken or typed "yes"/"no" resolves a pending confirmation without
the user having to tap the inline buttons.
"""
import re

_AFFIRM = {
    # en
    "yes", "yeah", "yep", "yup", "ok", "okay", "sure", "confirm", "confirmed",
    "correct", "agree", "agreed", "go",
    # ru
    "да", "ага", "угу", "конечно", "подтверждаю", "подтвердить", "давай",
    "согласен", "согласна", "верно", "ок", "окей",
    # kk
    "иә", "ия", "ооба", "жарайды", "макул", "мақұл", "дұрыс", "растаймын", "ия",
}

_NEGATE = {
    # en
    "no", "nope", "nah", "cancel", "stop", "decline", "dont",
    # ru
    "нет", "не", "отмена", "отменить", "стоп", "отказ",
    # kk
    "жоқ", "жок", "тоқта", "болмайды",
}


def classify_reply(text: str) -> str | None:
    """Return "yes", "no", or None if the text is not a clear yes/no reply."""
    norm = re.sub(r"[^\w\s]", " ", text.strip().lower())
    words = norm.split()
    if not words:
        return None

    if words[0] in _AFFIRM:
        return "yes"
    if words[0] in _NEGATE:
        return "no"
    # Fall back to a token scan (e.g. "да, конечно" / "не надо").
    if any(w in _NEGATE for w in words):
        return "no"
    if any(w in _AFFIRM for w in words):
        return "yes"
    return None

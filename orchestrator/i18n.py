"""Internationalisation helpers for the orchestrator.

Covers every user-facing string the orchestrator generates.
Russian is the default — it's the primary language for ForteBank KZ users.
"""
from __future__ import annotations

DEFAULT_LANG = "ru-RU"

_MESSAGES: dict[str, dict[str, str]] = {
    "ru-RU": {
        "unknown_intent": (
            "Извините, я не понял вашу просьбу. "
            "Попробуйте: перевод, баланс, оплата счёта или выписка."
        ),
        "no_scenario": "Извините, я не могу помочь с этим.",
        "missing_params": "Пожалуйста, укажите: {params}",
        "no_pending": "Ожидающего действия не найдено. Возможно, истёк срок — попробуйте снова.",
        "cancelled": "Отменено.",
    },
    "kk-KZ": {
        "unknown_intent": (
            "Кешіріңіз, сізді түсінбедім. "
            "Қолжетімді: аудару, баланс, шот төлеу немесе үзінді."
        ),
        "no_scenario": "Кешіріңіз, мен мұнда көмектесе алмаймын.",
        "missing_params": "Мына деректерді көрсетіңіз: {params}",
        "no_pending": "Күтуші әрекет табылмады. Мерзімі өткен болуы мүмкін — қайталап сұраңыз.",
        "cancelled": "Бас тартылды.",
    },
    "en-US": {
        "unknown_intent": (
            "Sorry, I couldn't understand that. "
            "Try: transfer, balance, pay a bill, or a statement."
        ),
        "no_scenario": "Sorry, I can't help with that.",
        "missing_params": "Please provide: {params}",
        "no_pending": "No pending action found. It may have expired — please ask again.",
        "cancelled": "Cancelled.",
    },
}


def t(lang: str, key: str, **kwargs: str) -> str:
    """Return the localised string for the given language and key."""
    bucket = _MESSAGES.get(lang) or _MESSAGES[DEFAULT_LANG]
    template = bucket.get(key) or _MESSAGES["en-US"].get(key, key)
    return template.format(**kwargs) if kwargs else template

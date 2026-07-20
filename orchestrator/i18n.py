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


# Per-language prompt for each parameter, asked one at a time during multi-turn
# collection. New scenarios add their parameters here; anything missing falls
# back to a generic "please provide {param}" so collection still works.
_SLOT_PROMPTS: dict[str, dict[str, str]] = {
    "ru-RU": {
        "amount": "На какую сумму?",
        "currency": "В какой валюте? (KZT, USD, EUR)",
        "to_account": "На какой счёт перевести? Укажите номер счёта.",
        "bill_id": "Укажите номер счёта для оплаты.",
        "limit": "Сколько последних транзакций показать?",
        "from_account_kind": "С какого счёта списать? (тенговый, долларовый, …)",
        "to_account_kind": "На какой счёт зачислить? (тенговый, долларовый, …)",
        "phone": "Укажите номер телефона получателя.",
        "term": "На какой срок? (в месяцах)",
        "card_last4": "Укажите последние 4 цифры карты.",
        "limit_kind": "Какой лимит изменить — суточный или месячный?",
        "limit_amount": "Укажите новый лимит.",
        "period": "За какой период? (например, месяц)",
        "cert_kind": "Какую справку подготовить? (о счёте, об отсутствии задолженности, …)",
    },
    "kk-KZ": {
        "amount": "Қандай сома?",
        "currency": "Қай валютада? (KZT, USD, EUR)",
        "to_account": "Қай шотқа аудару керек? Шот нөмірін көрсетіңіз.",
        "bill_id": "Төлейтін шот нөмірін көрсетіңіз.",
        "limit": "Соңғы неше транзакцияны көрсетейін?",
        "from_account_kind": "Қай шоттан алу керек? (теңгелік, долларлық, …)",
        "to_account_kind": "Қай шотқа есептеу керек? (теңгелік, долларлық, …)",
        "phone": "Алушының телефон нөмірін көрсетіңіз.",
        "term": "Қандай мерзімге? (айлармен)",
        "card_last4": "Картаның соңғы 4 санын көрсетіңіз.",
        "limit_kind": "Қай лимитті өзгерту керек — тәуліктік пе, айлық па?",
        "limit_amount": "Жаңа лимитті көрсетіңіз.",
        "period": "Қай кезең үшін? (мысалы, ай)",
        "cert_kind": "Қандай анықтама керек? (шот туралы, берешегі жоқ туралы, …)",
    },
    "en-US": {
        "amount": "What amount?",
        "currency": "Which currency? (KZT, USD, EUR)",
        "to_account": "Which account? Please provide the account number.",
        "bill_id": "Please provide the bill number.",
        "limit": "How many recent transactions?",
        "from_account_kind": "From which account? (tenge, dollar, …)",
        "to_account_kind": "To which account? (tenge, dollar, …)",
        "phone": "Please provide the recipient's phone number.",
        "term": "For what term? (in months)",
        "card_last4": "Please provide the last 4 digits of the card.",
        "limit_kind": "Which limit — daily or monthly?",
        "limit_amount": "Please provide the new limit.",
        "period": "For what period? (e.g. month)",
        "cert_kind": "Which certificate? (account, no-debt, …)",
    },
}

_SLOT_FALLBACK = {
    "ru-RU": "Пожалуйста, укажите: {param}",
    "kk-KZ": "Мынаны көрсетіңіз: {param}",
    "en-US": "Please provide: {param}",
}


def slot_prompt(lang: str, param: str) -> str:
    """Return the localised prompt asking the user for one parameter."""
    bucket = _SLOT_PROMPTS.get(lang) or _SLOT_PROMPTS[DEFAULT_LANG]
    prompt = bucket.get(param)
    if prompt:
        return prompt
    fallback = _SLOT_FALLBACK.get(lang) or _SLOT_FALLBACK[DEFAULT_LANG]
    return fallback.format(param=param)

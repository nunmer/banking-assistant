"""Internationalisation helpers for the orchestrator.

Covers every user-facing string the orchestrator generates.
Russian is the default — it's the primary language for ForteBank KZ users.
"""
from __future__ import annotations

DEFAULT_LANG = "ru-RU"

_MESSAGES: dict[str, dict[str, str]] = {
    "ru-RU": {
        "unknown_intent": (
            "Не совсем понял 🤔 Вот с чем я могу помочь:\n\n"
            "💸 Переводы — на счёт, между своими счетами, по номеру телефона\n"
            "💳 Карты — заблокировать, разблокировать, изменить лимит\n"
            "🏦 Депозит — открыть\n"
            "📄 Счёт — баланс, выписка, справка\n"
            "🧾 Оплата счетов\n"
            "📍 Навигация и связь с менеджером\n\n"
            "Просто напишите или скажите, что нужно — например «переведи 5000 тенге на +7 701 …»."
        ),
        "no_scenario": "Извините, с этим пока не могу помочь.",
        "missing_params": "Пожалуйста, укажите: {params}",
        "no_pending": "Не нашёл активного запроса. Возможно, истёк срок — попробуйте ещё раз.",
        "cancelled": "Хорошо, отменил. 👌",
        "operation_done": "Готово! Операция выполнена. ✅",
        "operation_error": "Не удалось выполнить операцию. Попробуйте, пожалуйста, чуть позже.",
    },
    "kk-KZ": {
        "unknown_intent": (
            "Толық түсінбедім 🤔 Мен мынаған көмектесе аламын:\n\n"
            "💸 Аударымдар — шотқа, өз шоттарыңыз арасында, телефон нөмірі бойынша\n"
            "💳 Карталар — бұғаттау, бұғаттан шығару, лимитті өзгерту\n"
            "🏦 Депозит — ашу\n"
            "📄 Шот — баланс, үзінді, анықтама\n"
            "🧾 Шот төлеу\n"
            "📍 Навигация және менеджермен байланыс\n\n"
            "Не керегін жазыңыз немесе айтыңыз — мысалы «+7 701 … нөміріне 5000 теңге аудар»."
        ),
        "no_scenario": "Кешіріңіз, бұған әзірге көмектесе алмаймын.",
        "missing_params": "Мына деректерді көрсетіңіз: {params}",
        "no_pending": "Белсенді сұрау табылмады. Мерзімі өткен болуы мүмкін — қайталап көріңіз.",
        "cancelled": "Жарайды, бас тарттым. 👌",
        "operation_done": "Дайын! Операция орындалды. ✅",
        "operation_error": "Операцияны орындау мүмкін болмады. Сәл кейінірек қайталап көріңіз.",
    },
    "en-US": {
        "unknown_intent": (
            "I didn't quite catch that 🤔 Here's what I can help with:\n\n"
            "💸 Transfers — to an account, between your own accounts, by phone number\n"
            "💳 Cards — block, unblock, change limit\n"
            "🏦 Deposit — open one\n"
            "📄 Account — balance, statement, certificate\n"
            "🧾 Pay bills\n"
            "📍 Navigation and reaching a manager\n\n"
            "Just type or say what you need — e.g. \"send 5000 tenge to +7 701 …\"."
        ),
        "no_scenario": "Sorry, I can't help with that yet.",
        "missing_params": "Please provide: {params}",
        "no_pending": "No active request found. It may have expired — please try again.",
        "cancelled": "Okay, cancelled. 👌",
        "operation_done": "Done! Your request has been completed. ✅",
        "operation_error": "I couldn't complete that operation. Please try again a little later.",
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

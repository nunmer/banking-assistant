"""Internationalisation helpers for the orchestrator.

Covers every user-facing string the orchestrator generates.
Russian is the default — it's the primary language for ForteBank KZ users.
"""
from __future__ import annotations

import re

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
        "greeting": "Здравствуйте! Чем могу помочь?",
        "farewell": "Рад был помочь! Обращайтесь, если что-то понадобится.",
        "no_scenario": "Извините, с этим пока не могу помочь.",
        "accounts_unavailable": "Не получилось загрузить ваши счета. Попробуйте, пожалуйста, чуть позже.",
        "no_account_kind": "Не нашёл у вас счёта в валюте {kind}. Ваши счета: {available}.",
        "same_account": "Это один и тот же счёт — перевод не нужен. 🙂 Уточните, с какого и на какой счёт перевести.",
        "missing_params": "Пожалуйста, укажите: {params}",
        "no_pending": "Не нашёл активного запроса. Возможно, истёк срок — попробуйте ещё раз.",
        "cancelled": "Хорошо, отменил. 👌",
        "invalid_value": "Хм, это не похоже на корректное значение.",
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
        "farewell": "Көмектескеніме қуаныштымын! Қажет болса, айта беріңіз.",
        "no_scenario": "Кешіріңіз, бұған әзірге көмектесе алмаймын.",
        "accounts_unavailable": "Шоттарыңызды жүктеу мүмкін болмады. Сәл кейінірек қайталап көріңіз.",
        "no_account_kind": "{kind} валютасында шотыңыз табылмады. Сіздің шоттарыңыз: {available}.",
        "same_account": "Бұл бір шот — аударым қажет емес. 🙂 Қай шоттан қай шотқа аудару керегін нақтылаңыз.",
        "missing_params": "Мына деректерді көрсетіңіз: {params}",
        "no_pending": "Белсенді сұрау табылмады. Мерзімі өткен болуы мүмкін — қайталап көріңіз.",
        "cancelled": "Жарайды, бас тарттым. 👌",
        "invalid_value": "Хм, бұл дұрыс мән емес сияқты.",
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
        "greeting": "Hello! How can I help you today?",
        "farewell": "Glad I could help! Feel free to reach out again if you need anything.",
        "no_scenario": "Sorry, I can't help with that yet.",
        "accounts_unavailable": "I couldn't load your accounts. Please try again a little later.",
        "no_account_kind": "You don't have a {kind} account. Your accounts: {available}.",
        "same_account": "That's the same account on both sides — no transfer needed. 🙂 Please tell me which account to move from and to.",
        "missing_params": "Please provide: {params}",
        "no_pending": "No active request found. It may have expired — please try again.",
        "cancelled": "Okay, cancelled. 👌",
        "invalid_value": "Hmm, that doesn't look quite right.",
        "operation_done": "Done! Your request has been completed. ✅",
        "operation_error": "I couldn't complete that operation. Please try again a little later.",
    },
}


def t(lang: str, key: str, **kwargs: str) -> str:
    """Return the localised string for the given language and key.

    A key missing from a supported language's own bucket falls back to
    DEFAULT_LANG (ru-RU), not English — this text may be spoken by a TTS
    voice chosen to match `lang`, and Russian is the language this user base
    is actually likely to understand, unlike a silent assumption of English.
    """
    bucket = _MESSAGES.get(lang) or _MESSAGES[DEFAULT_LANG]
    template = bucket.get(key) or _MESSAGES[DEFAULT_LANG].get(key, key)
    return template.format(**kwargs) if kwargs else template


# Emoji/pictographs read fine on screen but make a TTS engine stumble (it either
# vocalises the symbol's description or drops audio for it) — strip them from
# anything read aloud that has no dedicated `speech` override below.
_EMOJI_RE = re.compile(
    "["
    "\U0001F1E6-\U0001F1FF"  # regional indicators
    "\U0001F300-\U0001FAFF"  # symbols, pictographs, emoticons, supplemental
    "\U00002600-\U000027BF"  # misc symbols & dingbats
    "️"                  # variation selector-16
    "]+"
)


def strip_for_speech(text: str) -> str:
    """Remove emoji and tidy whitespace so text reads as plain spoken sentences."""
    cleaned = _EMOJI_RE.sub("", text)
    cleaned = re.sub(r"[ \t]+", " ", cleaned)
    return cleaned.strip(" \n")


# Some display strings (the capability list, in particular) are bulleted menus
# meant to be read on screen, not heard — spoken aloud they run together into
# noise, and the bot's terse system phrasing overall reads more like a menu than
# a person. These are natural-sentence rewrites used only for TTS; the on-screen
# `message` text is unchanged.
_SPEECH_OVERRIDES: dict[str, dict[str, str]] = {
    "ru-RU": {
        "unknown_intent": (
            "Я пока не понял, что вы имеете в виду. Я умею переводить деньги, "
            "работать с картами, открывать вклады, показывать баланс и выписки, "
            "оплачивать счета, а ещё могу подсказать, куда обратиться. "
            "Просто скажите своими словами, что вам нужно."
        ),
    },
    "kk-KZ": {
        "unknown_intent": (
            "Кешіріңіз, не айтқыңыз келгенін әзірге түсінбедім. Мен ақша "
            "аудара аламын, карталар бойынша көмектесе аламын, депозит аша "
            "аламын, баланс пен үзінді көшірмені көрсете аламын, шоттарды "
            "төлей аламын, сондай-ақ сізге қайда жүгіну керегін айтып бере "
            "аламын. Қажетіңізді өз сөзіңізбен айта салыңыз."
        ),
    },
    "en-US": {
        "unknown_intent": (
            "I didn't quite catch that. I can transfer money, manage your "
            "cards, open a deposit, show your balance and statement, pay "
            "bills, or point you to a manager. Just tell me what you need, "
            "in your own words."
        ),
    },
}


def speech(lang: str, key: str, **kwargs: str) -> str:
    """Return the TTS-friendly variant of message `key`.

    Falls back to a symbol-stripped `t(lang, key)` when there's no dedicated
    override for this exact language — most messages already read fine aloud
    once emoji are gone. Never borrows another language's override: a
    not-yet-translated language must never end up spoken in the wrong one.
    """
    override = _SPEECH_OVERRIDES.get(lang, {}).get(key)
    if override:
        return override.format(**kwargs) if kwargs else override
    return strip_for_speech(t(lang, key, **kwargs))


# Per-language prompt for each parameter, asked one at a time during multi-turn
# collection. New scenarios add their parameters here; anything missing falls
# back to a generic "please provide {param}" so collection still works.
_SLOT_PROMPTS: dict[str, dict[str, str]] = {
    "ru-RU": {
        "amount": "Назовите сумму, пожалуйста.",
        "currency": "В какой валюте — тенге, доллары или евро?",
        "to_account": "На какой счёт перевести? Назовите номер счёта.",
        "bill_id": "Какой счёт оплатить? Назовите номер.",
        "limit": "Сколько последних транзакций показать?",
        "from_account_kind": "С какого счёта списать — тенгового, долларового или другого?",
        "to_account_kind": "На какой счёт зачислить — тенговый, долларовый или другой?",
        "phone": "Назовите номер телефона получателя, пожалуйста.",
        "term": "На какой срок открыть депозит — в месяцах?",
        "card_last4": "Назовите последние 4 цифры карты.",
        "limit_kind": "Какой лимит изменить — суточный или месячный?",
        "limit_amount": "Какой лимит установить?",
        "period": "За какой период — например, за месяц?",
        "cert_kind": "Какую справку подготовить — о счёте или об отсутствии задолженности?",
    },
    "kk-KZ": {
        "amount": "Қажетті соманы атаңыз.",
        "currency": "Қай валютада — теңгемен, доллармен әлде еуромен?",
        "to_account": "Қай шотқа аудару керек? Шот нөмірін айтыңыз.",
        "bill_id": "Қай шотты төлеу керек? Нөмірін айтыңыз.",
        "limit": "Соңғы неше транзакцияны көрсетейін?",
        "from_account_kind": "Қай шоттан ақша шығару керек — теңгелік, долларлық немесе басқадан?",
        "to_account_kind": "Қай шотқа аудару керек — теңгелік, долларлық әлде басқа шотқа?",
        "phone": "Алушының телефон нөмірін айтыңыз.",
        "term": "Депозитті қандай мерзімге ашу керек — аймен айтыңыз.",
        "card_last4": "Картаның соңғы 4 цифрын айтыңыз.",
        "limit_kind": "Қай лимитті өзгерту керек — тәуліктік пе, әлде айлық па?",
        "limit_amount": "Қандай лимит орнату керек?",
        "period": "Қандай мерзімге — мысалы, бір айға?",
        "cert_kind": "Қандай анықтама дайындау керек — шот туралы ма, әлде берешектің жоқтығы туралы ма?",
    },
    "en-US": {
        "amount": "What amount, please?",
        "currency": "Which currency — tenge, dollars, or euros?",
        "to_account": "Which account should I send it to? Please give me the account number.",
        "bill_id": "Which bill would you like to pay? Please give me the number.",
        "limit": "How many recent transactions?",
        "from_account_kind": "Which account should I take it from — tenge, dollar, or other?",
        "to_account_kind": "Which account should I credit it to — tenge, dollar, or other?",
        "phone": "What's the recipient's phone number?",
        "term": "For how many months should I open the deposit?",
        "card_last4": "What are the last 4 digits of the card?",
        "limit_kind": "Which limit should I change — daily or monthly?",
        "limit_amount": "What limit would you like to set?",
        "period": "For which period — for example, the last month?",
        "cert_kind": "Which certificate would you like — account statement or a no-debt certificate?",
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

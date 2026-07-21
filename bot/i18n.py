"""Internationalisation helpers for the Telegram bot.

Supported languages: Kazakh (kk-KZ), Russian (ru-RU), English (en-US).
Russian is the default — it's the primary banking language for ForteBank KZ.
"""
from __future__ import annotations

SUPPORTED: set[str] = {"kk-KZ", "ru-RU", "en-US"}
DEFAULT_LANG: str = "ru-RU"

_LANG_MAP: dict[str, str] = {
    "kk": "kk-KZ", "kk-kz": "kk-KZ", "kk-KZ": "kk-KZ",
    "ru": "ru-RU", "ru-ru": "ru-RU", "ru-RU": "ru-RU",
    "en": "en-US", "en-us": "en-US", "en-US": "en-US",
    "en-gb": "en-US", "en-GB": "en-US",
}


def resolve_lang(code: str | None, strict: bool = False) -> str | None:
    """Map a Telegram language_code or user input to a supported BCP-47 tag.

    With strict=True returns None for unsupported codes instead of the default.
    """
    if not code:
        return None if strict else DEFAULT_LANG
    resolved = _LANG_MAP.get(code) or _LANG_MAP.get(code[:2].lower())
    if resolved:
        return resolved
    return None if strict else DEFAULT_LANG


_MESSAGES: dict[str, dict[str, str]] = {
    "ru-RU": {
        "start": (
            "Привет! Я банковский ассистент Forte 👋\n\n"
            "Пишите или отправляйте голосовые — на русском или казахском, как удобно. "
            "Язык распознаю сам.\n\n"
            "Я умею:\n"
            "💸 Переводы — на счёт, между своими счетами, по номеру телефона\n"
            "💳 Карты — заблокировать, разблокировать, изменить лимит\n"
            "🏦 Открыть депозит\n"
            "📄 Баланс, выписка, справка\n"
            "🧾 Оплата счетов\n"
            "📍 Навигация и связь с менеджером\n\n"
            "Например: «Переведи 5000 тенге на +7 701 234 5678»"
        ),
        "lang_set": "Язык изменён на русский. 🇷🇺",
        "lang_unknown": "Неизвестный язык. Доступные: kk (қазақша), ru (русский), en (English).",
        "lang_current": "Текущий язык: {}. Сменить: /lang kk | ru | en",
        "error_audio": "Не удалось распознать аудио. Попробуйте ещё раз.",
        "empty_audio": "Ничего не разобрал — повторите, пожалуйста.",
        "error_generic": "Что-то пошло не так. Попробуйте ещё раз.",
        "transcript_prefix": "🗣 _{}_ ",
        "web_version": "🌐 Попробовать веб-версию",
        "app_prompt": "Голосовой ассистент AI-nur — нажмите, чтобы открыть:",
    },
    "kk-KZ": {
        "start": (
            "Сәлем! Мен Forte банк ассистентімін 👋\n\n"
            "Мәтін де, дауыстық та жаза аласыз — орысша не қазақша, өзіңізге ыңғайлы тілде. "
            "Тілді өзім тани аламын.\n\n"
            "Мен мынаны істей аламын:\n"
            "💸 Аударымдар — шотқа, өз шоттарыңыз арасында, телефон нөмірі бойынша\n"
            "💳 Карталар — бұғаттау, бұғаттан шығару, лимитті өзгерту\n"
            "🏦 Депозит ашу\n"
            "📄 Баланс, үзінді, анықтама\n"
            "🧾 Шот төлеу\n"
            "📍 Навигация және менеджермен байланыс\n\n"
            "Мысалы: «+7 701 234 5678 нөміріне 5000 теңге аудар»"
        ),
        "lang_set": "Тіл қазақ тіліне өзгертілді. 🇰🇿",
        "lang_unknown": "Белгісіз тіл. Қолжетімді: kk (қазақша), ru (русский), en (English).",
        "lang_current": "Ағымдағы тіл: {}. Өзгерту: /lang kk | ru | en",
        "error_audio": "Дыбысты тану мүмкін болмады. Қайталап көріңіз.",
        "empty_audio": "Ештеңе естілмеді — қайталаңыз.",
        "error_generic": "Бірдеңе дұрыс болмады. Қайталап көріңіз.",
        "transcript_prefix": "🗣 _{}_ ",
        "web_version": "🌐 Веб-нұсқасын байқап көріңіз",
        "app_prompt": "AI-nur дауыстық ассистенті — ашу үшін басыңыз:",
    },
    "en-US": {
        "start": (
            "Hi! I'm the Forte banking assistant 👋\n\n"
            "Type or send a voice message — in Russian or Kazakh, whichever you like. "
            "I'll detect the language myself.\n\n"
            "I can help with:\n"
            "💸 Transfers — to an account, between your own accounts, by phone number\n"
            "💳 Cards — block, unblock, change limit\n"
            "🏦 Open a deposit\n"
            "📄 Balance, statement, certificate\n"
            "🧾 Pay bills\n"
            "📍 Navigation and reaching a manager\n\n"
            "For example: \"Send 5000 tenge to +7 701 234 5678\""
        ),
        "lang_set": "Language set to English. 🇬🇧",
        "lang_unknown": "Unknown language. Available: kk (қазақша), ru (русский), en (English).",
        "lang_current": "Current language: {}. Change: /lang kk | ru | en",
        "error_audio": "Sorry, I couldn't understand the audio. Please try again.",
        "empty_audio": "I didn't catch that — could you say it again?",
        "error_generic": "Something went wrong. Please try again.",
        "transcript_prefix": "🗣 _{}_ ",
        "web_version": "🌐 Try the web version",
        "app_prompt": "AI-nur voice assistant — tap to open:",
    },
}


def t(lang: str, key: str) -> str:
    """Return the localised string for the given language and key."""
    bucket = _MESSAGES.get(lang) or _MESSAGES[DEFAULT_LANG]
    return bucket.get(key) or _MESSAGES["en-US"].get(key, key)

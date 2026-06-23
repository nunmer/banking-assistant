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
            "Привет! Я банковский ассистент Forte.\n\n"
            "Отправьте текст или голосовое сообщение. Например:\n"
            "• Переведи 500 долларов на счёт KZ123\n"
            "• Какой мой баланс?\n"
            "• Оплати счёт 8842 на сумму 12000\n"
            "• Покажи последние 5 транзакций\n\n"
            "Сменить язык: /lang kk | ru | en"
        ),
        "lang_set": "Язык изменён на русский. 🇷🇺",
        "lang_unknown": "Неизвестный язык. Доступные: kk (қазақша), ru (русский), en (English).",
        "lang_current": "Текущий язык: {}. Сменить: /lang kk | ru | en",
        "error_audio": "Не удалось распознать аудио. Попробуйте ещё раз.",
        "empty_audio": "Ничего не разобрал — повторите, пожалуйста.",
        "error_generic": "Что-то пошло не так. Попробуйте ещё раз.",
        "transcript_prefix": "🗣 _{}_ ",
    },
    "kk-KZ": {
        "start": (
            "Сәлем! Мен Forte банк ассистентімін.\n\n"
            "Мәтін немесе дауыстық хабарлама жібере аласыз. Мысалы:\n"
            "• KZ123 шотына 500 доллар аудар\n"
            "• Менің балансым қанша?\n"
            "• 8842 шотты 12000 сомасына төле\n"
            "• Соңғы 5 транзакцияны көрсет\n\n"
            "Тілді өзгерту: /lang kk | ru | en"
        ),
        "lang_set": "Тіл қазақ тіліне өзгертілді. 🇰🇿",
        "lang_unknown": "Белгісіз тіл. Қолжетімді: kk (қазақша), ru (русский), en (English).",
        "lang_current": "Ағымдағы тіл: {}. Өзгерту: /lang kk | ru | en",
        "error_audio": "Дыбысты тану мүмкін болмады. Қайталап көріңіз.",
        "empty_audio": "Ештеңе естілмеді — қайталаңыз.",
        "error_generic": "Бірдеңе дұрыс болмады. Қайталап көріңіз.",
        "transcript_prefix": "🗣 _{}_ ",
    },
    "en-US": {
        "start": (
            "Hi! I'm the Forte banking assistant.\n\n"
            "Send me a text or voice message. For example:\n"
            "• Transfer 500 USD to account KZ123\n"
            "• What's my balance?\n"
            "• Pay bill 8842 for 12000\n"
            "• Show my last 5 transactions\n\n"
            "Change language: /lang kk | ru | en"
        ),
        "lang_set": "Language set to English. 🇬🇧",
        "lang_unknown": "Unknown language. Available: kk (қазақша), ru (русский), en (English).",
        "lang_current": "Current language: {}. Change: /lang kk | ru | en",
        "error_audio": "Sorry, I couldn't understand the audio. Please try again.",
        "empty_audio": "I didn't catch that — could you say it again?",
        "error_generic": "Something went wrong. Please try again.",
        "transcript_prefix": "🗣 _{}_ ",
    },
}


def t(lang: str, key: str) -> str:
    """Return the localised string for the given language and key."""
    bucket = _MESSAGES.get(lang) or _MESSAGES[DEFAULT_LANG]
    return bucket.get(key) or _MESSAGES["en-US"].get(key, key)

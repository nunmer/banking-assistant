"""Inline keyboards used by the bot."""
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, WebAppInfo

# Language picker shown under a message. Tapping a flag fires `setlang:<tag>`.
_LANG_BUTTONS: list[tuple[str, str]] = [
    ("🇰🇿 Қазақша", "kk-KZ"),
    ("🇷🇺 Русский", "ru-RU"),
    ("🇬🇧 English", "en-US"),
]


def lang_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text=label, callback_data=f"setlang:{tag}")
                for label, tag in _LANG_BUTTONS
            ]
        ]
    )


def web_link_keyboard(label: str, url: str) -> InlineKeyboardMarkup:
    """Single URL button linking to the web voice client (opens in browser)."""
    return InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text=label, url=url)]]
    )


def web_app_keyboard(label: str, url: str) -> InlineKeyboardMarkup:
    """Single Mini App button — opens the voice client inside Telegram."""
    return InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text=label, web_app=WebAppInfo(url=url))]]
    )


def confirm_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="✅ Yes", callback_data="confirm:yes"),
                InlineKeyboardButton(text="❌ No", callback_data="confirm:no"),
            ]
        ]
    )

"""Inline keyboards used by the bot."""
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

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


def confirm_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="✅ Yes", callback_data="confirm:yes"),
                InlineKeyboardButton(text="❌ No", callback_data="confirm:no"),
            ]
        ]
    )

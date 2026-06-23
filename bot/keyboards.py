"""Inline keyboards used by the bot."""
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup


def confirm_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="✅ Yes", callback_data="confirm:yes"),
                InlineKeyboardButton(text="❌ No", callback_data="confirm:no"),
            ]
        ]
    )

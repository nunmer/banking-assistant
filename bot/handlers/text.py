"""Text message and confirmation-callback handlers."""
import logging

import httpx
from aiogram import F, Router
from aiogram.filters import Command, CommandStart
from aiogram.types import CallbackQuery, Message

from bot.config import settings
from bot.handlers.common import send_to_orchestrator
from bot.i18n import DEFAULT_LANG, SUPPORTED, resolve_lang, t
from bot.keyboards import confirm_keyboard

logger = logging.getLogger("bot.text")

router = Router()

_LANG_ALIASES: dict[str, str] = {
    "kk": "kk-KZ", "ru": "ru-RU", "en": "en-US",
}


def _user_lang(message: Message) -> str:
    """Resolve a user's language from their Telegram locale, defaulting to Russian."""
    return resolve_lang(message.from_user.language_code) or DEFAULT_LANG


@router.message(CommandStart())
async def handle_start(message: Message) -> None:
    lang = _user_lang(message)
    await message.answer(t(lang, "start"))


@router.message(Command("lang"))
async def handle_lang(message: Message) -> None:
    """Set preferred language: /lang kk | ru | en"""
    current_lang = _user_lang(message)
    args = (message.text or "").split(maxsplit=1)
    if len(args) < 2:
        lang_name = current_lang
        await message.answer(t(current_lang, "lang_current").format(lang_name))
        return

    code = args[1].strip().lower()
    new_lang = _LANG_ALIASES.get(code)
    if not new_lang:
        await message.answer(t(current_lang, "lang_unknown"))
        return

    # Persist lang in the session via the orchestrator /chat with a neutral text.
    # The simplest approach: send a dummy chat request that sets the lang.
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(
                f"{settings.ORCHESTRATOR_URL}/session/lang",
                json={"session_id": str(message.from_user.id), "lang": new_lang},
            )
            resp.raise_for_status()
    except httpx.HTTPError:
        pass  # Non-fatal — the lang will be picked up on the next real message.

    await message.answer(t(new_lang, "lang_set"))


@router.message(F.text)
async def handle_text(message: Message) -> None:
    session_id = str(message.from_user.id)
    lang = _user_lang(message)

    try:
        data = await send_to_orchestrator(session_id, message.text, lang=lang)
    except httpx.HTTPError as e:
        logger.error("orchestrator call failed: %s", e)
        await message.answer(t(lang, "error_generic"))
        return

    reply_markup = confirm_keyboard() if data["action"] == "confirm" else None
    await message.answer(data["message"], reply_markup=reply_markup)


@router.callback_query(F.data.startswith("confirm:"))
async def handle_confirm_callback(callback: CallbackQuery) -> None:
    approved = callback.data.split(":")[1] == "yes"
    session_id = str(callback.from_user.id)
    lang = resolve_lang(callback.from_user.language_code) or DEFAULT_LANG

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(
                f"{settings.ORCHESTRATOR_URL}/confirm/reply",
                json={"session_id": session_id, "approved": approved},
            )
            resp.raise_for_status()
            data = resp.json()
    except httpx.HTTPError as e:
        logger.error("confirm/reply call failed: %s", e)
        await callback.answer(t(lang, "error_generic"), show_alert=True)
        return

    await callback.message.edit_text(data["message"])
    await callback.answer()

"""Text message and confirmation-callback handlers."""
import logging

import httpx
from aiogram import F, Router
from aiogram.filters import Command, CommandStart
from aiogram.types import CallbackQuery, Message

from bot.config import settings
from bot.handlers.common import get_user_lang, send_to_orchestrator
from bot.i18n import DEFAULT_LANG, SUPPORTED, resolve_lang, t
from bot.keyboards import confirm_keyboard, lang_keyboard, web_app_keyboard

# Bilingual prompt shown above the language picker (user may not have a lang yet).
LANG_PROMPT = "Тілді таңдаңыз / Выберите язык / Choose your language:"

logger = logging.getLogger("bot.text")

router = Router()

_LANG_ALIASES: dict[str, str] = {
    "kk": "kk-KZ", "ru": "ru-RU", "en": "en-US",
}


def _user_lang(message: Message) -> str:
    """Resolve a user's language from their Telegram locale, defaulting to Russian."""
    return resolve_lang(message.from_user.language_code) or DEFAULT_LANG


async def _persist_lang(session_id: str, lang: str) -> None:
    """Best-effort persist of the user's language to the orchestrator session."""
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(
                f"{settings.ORCHESTRATOR_URL}/session/lang",
                json={"session_id": session_id, "lang": lang},
            )
            resp.raise_for_status()
    except httpx.HTTPError as e:
        logger.warning("failed to persist lang: %s", e)


@router.message(CommandStart())
async def handle_start(message: Message) -> None:
    lang = _user_lang(message)
    # Seed the session with the Telegram locale so voice works on first use.
    await _persist_lang(str(message.from_user.id), lang)
    # Mini App button — opens the voice client inside Telegram (same session).
    reply_markup = (
        web_app_keyboard(t(lang, "web_version"), settings.WEB_APP_URL)
        if settings.WEB_APP_URL
        else None
    )
    await message.answer(t(lang, "start"), reply_markup=reply_markup)


@router.message(Command("app"))
async def handle_app(message: Message) -> None:
    """Open the Mini App — the always-available entry point from the menu."""
    lang = _user_lang(message)
    if not settings.WEB_APP_URL:
        await message.answer(t(lang, "error_generic"))
        return
    await message.answer(
        t(lang, "app_prompt"),
        reply_markup=web_app_keyboard(t(lang, "web_version"), settings.WEB_APP_URL),
    )


@router.message(Command("lang"))
async def handle_lang(message: Message) -> None:
    """Show the language picker, or set directly via /lang kk | ru | en."""
    current_lang = _user_lang(message)
    args = (message.text or "").split(maxsplit=1)

    # No argument → show the inline flag buttons.
    if len(args) < 2:
        await message.answer(LANG_PROMPT, reply_markup=lang_keyboard())
        return

    code = args[1].strip().lower()
    new_lang = _LANG_ALIASES.get(code)
    if not new_lang:
        await message.answer(t(current_lang, "lang_unknown"))
        return

    await _persist_lang(str(message.from_user.id), new_lang)
    await message.answer(t(new_lang, "lang_set"))


@router.callback_query(F.data.startswith("setlang:"))
async def handle_setlang_callback(callback: CallbackQuery) -> None:
    new_lang = callback.data.split(":", 1)[1]
    if new_lang not in SUPPORTED:
        await callback.answer()
        return

    await _persist_lang(str(callback.from_user.id), new_lang)
    await callback.message.edit_text(t(new_lang, "lang_set"))
    await callback.answer()


@router.message(F.text)
async def handle_text(message: Message) -> None:
    session_id = str(message.from_user.id)
    # Persisted session language is the source of truth; omit lang on /chat so
    # it is not overwritten by the Telegram locale.
    lang = await get_user_lang(session_id, fallback=_user_lang(message))

    try:
        data = await send_to_orchestrator(session_id, message.text)
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
                json={"session_id": session_id, "approved": approved, "channel": "telegram"},
            )
            resp.raise_for_status()
            data = resp.json()
    except httpx.HTTPError as e:
        logger.error("confirm/reply call failed: %s", e)
        await callback.answer(t(lang, "error_generic"), show_alert=True)
        return

    await callback.message.edit_text(data["message"])
    await callback.answer()

"""Text and confirmation-callback handlers."""
import logging

import httpx
from aiogram import F, Router
from aiogram.filters import CommandStart
from aiogram.types import CallbackQuery, Message

from bot.config import settings
from bot.handlers.common import send_to_orchestrator
from bot.keyboards import confirm_keyboard

logger = logging.getLogger("bot.text")

router = Router()


@router.message(CommandStart())
async def handle_start(message: Message) -> None:
    await message.answer(
        "Hi! I'm the Forte banking assistant.\n\n"
        "Send me a message or a voice note. For example:\n"
        "• Transfer 500 USD to account KZ123\n"
        "• What's my balance?\n"
        "• Pay bill 8842 for 12000\n"
        "• Show my last 5 transactions"
    )


@router.message(F.text)
async def handle_text(message: Message) -> None:
    session_id = str(message.from_user.id)
    try:
        data = await send_to_orchestrator(session_id, message.text)
    except httpx.HTTPError as e:
        logger.error("orchestrator call failed: %s", e)
        await message.answer("Something went wrong. Please try again.")
        return

    reply_markup = confirm_keyboard() if data["action"] == "confirm" else None
    await message.answer(data["message"], reply_markup=reply_markup)


@router.callback_query(F.data.startswith("confirm:"))
async def handle_confirm_callback(callback: CallbackQuery) -> None:
    approved = callback.data.split(":")[1] == "yes"
    session_id = str(callback.from_user.id)

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
        await callback.answer("Something went wrong.", show_alert=True)
        return

    await callback.message.edit_text(data["message"])
    await callback.answer()

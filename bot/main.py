"""Forte Assistant Telegram bot entrypoint (long polling)."""
import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.types import BotCommand, MenuButtonCommands

from bot.config import settings
from bot.handlers import text, voice

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("bot")

# Shown in Telegram's "Menu" / command list next to the input field.
BOT_COMMANDS = [
    BotCommand(command="start", description="Start the bot"),
    BotCommand(command="app", description="Voice assistant app / Дауыстық ассистент / Голосовой ассистент"),
    BotCommand(command="lang", description="Change language / Тілді өзгерту / Сменить язык"),
]


async def main() -> None:
    if not settings.TELEGRAM_TOKEN:
        raise RuntimeError("TELEGRAM_TOKEN is not set")

    bot = Bot(token=settings.TELEGRAM_TOKEN)
    dp = Dispatcher()

    # Voice first so voice notes are not swallowed by the text router.
    dp.include_router(voice.router)
    dp.include_router(text.router)

    logger.info("Starting Forte Assistant bot (long polling)")
    await bot.delete_webhook(drop_pending_updates=True)
    await bot.set_my_commands(BOT_COMMANDS)
    # Telegram allows a single menu button: commands OR a Mini App. Keep the
    # commands menu (/start, /app, /lang) — the Mini App opens via the /app
    # command and the /start button instead. This also actively undoes a
    # previously set web_app menu button (Telegram persists it server-side).
    await bot.set_chat_menu_button(menu_button=MenuButtonCommands())
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())

"""Forte Assistant Telegram bot entrypoint (long polling)."""
import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.types import BotCommand, MenuButtonWebApp, WebAppInfo

from bot.config import settings
from bot.handlers import text, voice

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("bot")

# Shown in Telegram's "Menu" / command list next to the input field.
BOT_COMMANDS = [
    BotCommand(command="start", description="Start the bot"),
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
    # Persistent menu button next to the input field opens the Mini App.
    if settings.WEB_APP_URL:
        await bot.set_chat_menu_button(
            menu_button=MenuButtonWebApp(
                text="AI-nur", web_app=WebAppInfo(url=settings.WEB_APP_URL)
            )
        )
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())

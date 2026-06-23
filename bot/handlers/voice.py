"""Voice-note handler: download → transcribe → orchestrate → optional TTS reply."""
import logging

import httpx
from aiogram import Bot, F, Router
from aiogram.types import BufferedInputFile, Message

from bot.config import settings
from bot.handlers.common import send_to_orchestrator, synthesize
from bot.keyboards import confirm_keyboard

logger = logging.getLogger("bot.voice")

router = Router()


async def _transcribe(audio: bytes, lang: str) -> str:
    async with httpx.AsyncClient(timeout=60.0) as client:
        resp = await client.post(
            f"{settings.SPEECH_API_URL}/stt",
            content=audio,
            headers={"Content-Type": "audio/ogg", "X-Lang": lang},
        )
        resp.raise_for_status()
        return resp.json()["text"]


async def _reply(message: Message, text: str, **kwargs) -> None:
    """Send a reply as a voice note if TTS is enabled, otherwise plain text."""
    if settings.TTS_VOICE_REPLIES:
        audio = await synthesize(text, lang=settings.SPEECH_DEFAULT_LANG)
        if audio:
            await message.answer_voice(
                BufferedInputFile(audio, filename="reply.ogg"),
                caption=text,
                **kwargs,
            )
            return
    await message.answer(text, **kwargs)


@router.message(F.voice)
async def handle_voice(message: Message, bot: Bot) -> None:
    session_id = str(message.from_user.id)

    # Download the OGG/Opus voice note from Telegram.
    file = await bot.get_file(message.voice.file_id)
    buf = await bot.download_file(file.file_path)
    audio = buf.read()

    try:
        transcript = await _transcribe(audio, settings.SPEECH_DEFAULT_LANG)
    except (httpx.HTTPError, KeyError) as e:
        logger.error("transcription failed: %s", e)
        await message.answer("Sorry, I couldn't understand the audio. Please try again.")
        return

    if not transcript.strip():
        await message.answer("I didn't catch that — could you say it again?")
        return

    await message.answer(f"🗣 _{transcript}_", parse_mode="Markdown")

    try:
        data = await send_to_orchestrator(session_id, transcript)
    except httpx.HTTPError as e:
        logger.error("orchestrator call failed: %s", e)
        await message.answer("Something went wrong. Please try again.")
        return

    reply_markup = confirm_keyboard() if data["action"] == "confirm" else None
    await _reply(message, data["message"], reply_markup=reply_markup)

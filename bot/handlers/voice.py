"""Voice-note handler: download → STT → orchestrate → optional TTS reply."""
import logging

import httpx
from aiogram import Bot, F, Router
from aiogram.types import BufferedInputFile, Message

from bot.config import settings
from bot.handlers.common import send_to_orchestrator, synthesize
from bot.handlers.text import _user_lang
from bot.i18n import t
from bot.keyboards import confirm_keyboard

logger = logging.getLogger("bot.voice")

router = Router()


async def _transcribe(audio: bytes, lang: str) -> str:
    async with httpx.AsyncClient(timeout=120.0) as client:
        resp = await client.post(
            f"{settings.SPEECH_API_URL}/stt",
            content=audio,
            headers={"Content-Type": "audio/ogg", "X-Lang": lang},
        )
        resp.raise_for_status()
        return resp.json()["text"]


async def _reply(message: Message, text: str, lang: str, **kwargs) -> None:
    """Send a reply as a voice note if TTS is enabled, otherwise plain text."""
    if settings.TTS_VOICE_REPLIES:
        audio = await synthesize(text, lang=lang)
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
    lang = _user_lang(message)

    # Download the OGG/Opus voice note from Telegram.
    file = await bot.get_file(message.voice.file_id)
    buf = await bot.download_file(file.file_path)
    audio = buf.read()

    try:
        transcript = await _transcribe(audio, lang)
    except (httpx.HTTPError, KeyError) as e:
        logger.error("transcription failed: %s", e)
        await message.answer(t(lang, "error_audio"))
        return

    if not transcript.strip():
        await message.answer(t(lang, "empty_audio"))
        return

    await message.answer(t(lang, "transcript_prefix").format(transcript), parse_mode="Markdown")

    try:
        data = await send_to_orchestrator(session_id, transcript, lang=lang)
    except httpx.HTTPError as e:
        logger.error("orchestrator call failed: %s", e)
        await message.answer(t(lang, "error_generic"))
        return

    reply_markup = confirm_keyboard() if data["action"] == "confirm" else None
    await _reply(message, data["message"], lang=lang, reply_markup=reply_markup)

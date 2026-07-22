"""Voice-note handler: download → STT → orchestrate → optional TTS reply."""
import logging

import httpx
from aiogram import Bot, F, Router
from aiogram.types import BufferedInputFile, Message

from bot.config import settings
from bot.handlers.common import (
    get_user_lang,
    send_to_orchestrator,
    speech_headers,
    synthesize,
)
from bot.handlers.text import _user_lang
from bot.i18n import t
from bot.keyboards import confirm_keyboard

logger = logging.getLogger("bot.voice")

router = Router()


async def _transcribe(audio: bytes) -> str:
    # Send the multi-language set so the speech service auto-detects which
    # language was spoken; the orchestrator then replies in that language.
    async with httpx.AsyncClient(timeout=120.0) as client:
        resp = await client.post(
            f"{settings.SPEECH_SERVICE_URL}/stt/recognize",
            files={"file": ("audio.ogg", audio, "application/octet-stream")},
            data={"lang": settings.STT_LANGS},
            headers=speech_headers(),
        )
        resp.raise_for_status()
        return resp.json()["text"]


async def _reply(
    message: Message, text: str, lang: str, speech: str | None = None, **kwargs
) -> None:
    """Reply to a voice message.

    When TTS_VOICE_REPLIES is enabled and synthesis succeeds, send a voice note
    followed by the text (the text message carries any inline keyboard). The
    voice reads `speech` when provided (e.g. account numbers spelled out),
    otherwise `text`. If TTS is disabled or synthesis fails, fall back to text.
    """
    if settings.TTS_VOICE_REPLIES:
        audio = await synthesize(speech or text, lang=lang)
        if audio:
            await message.answer_voice(BufferedInputFile(audio, filename="reply.ogg"))
            await message.answer(text, **kwargs)
            return
    await message.answer(text, **kwargs)


@router.message(F.voice)
async def handle_voice(message: Message, bot: Bot) -> None:
    session_id = str(message.from_user.id)
    # Use the persisted session language (set via /lang) so STT is told the
    # right language; fall back to the Telegram locale for brand-new users.
    lang = await get_user_lang(session_id, fallback=_user_lang(message))

    # Download the OGG/Opus voice note from Telegram.
    file = await bot.get_file(message.voice.file_id)
    buf = await bot.download_file(file.file_path)
    audio = buf.read()

    try:
        transcript = await _transcribe(audio)
    except (httpx.HTTPError, KeyError) as e:
        logger.error("transcription failed: %s", e)
        await message.answer(t(lang, "error_audio"))
        return

    if not transcript.strip():
        await message.answer(t(lang, "empty_audio"))
        return

    await message.answer(t(lang, "transcript_prefix").format(transcript), parse_mode="Markdown")

    try:
        data = await send_to_orchestrator(
            session_id, transcript, user_name=message.from_user.first_name
        )
    except httpx.HTTPError as e:
        logger.error("orchestrator call failed: %s", e)
        await message.answer(t(lang, "error_generic"))
        return

    reply_markup = confirm_keyboard() if data["action"] == "confirm" else None
    # Speak in the language the orchestrator actually replied in (it auto-detects
    # and may differ from the session language when the user switched), so the
    # TTS voice matches the text. Fall back to the session language.
    reply_lang = data.get("lang") or lang
    await _reply(
        message,
        data["message"],
        lang=reply_lang,
        speech=data.get("speech"),
        reply_markup=reply_markup,
    )

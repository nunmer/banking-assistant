"""Whisper provider — local STT via faster-whisper.

faster-whisper is synchronous and CPU-bound, so transcription runs in a
threadpool to avoid blocking the event loop. TTS is not supported locally.
"""
import asyncio
import io

from faster_whisper import WhisperModel

import config

_model: WhisperModel | None = None


def _get_model() -> WhisperModel:
    global _model
    if _model is None:
        _model = WhisperModel(
            config.WHISPER_MODEL,
            device=config.WHISPER_DEVICE,
            compute_type=config.WHISPER_COMPUTE_TYPE,
        )
    return _model


def _transcribe_sync(audio: bytes, lang: str) -> str:
    segments, _ = _get_model().transcribe(io.BytesIO(audio), language=lang[:2])
    return " ".join(s.text for s in segments).strip()


async def transcribe(audio: bytes, lang: str) -> str:
    return await asyncio.to_thread(_transcribe_sync, audio, lang)


async def synthesize(text: str, lang: str, voice: str | None = None) -> bytes:
    raise NotImplementedError("Local Whisper provider does not support TTS")

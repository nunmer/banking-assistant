"""Yandex SpeechKit v3 streaming STT — real-time bidirectional gRPC recognition.

Unlike `stt.py`'s `recognize()`/`transcribe()` (submit-whole-file, then poll),
this opens a live gRPC stream to Yandex: PCM audio chunks go up as they're
captured, partial/final transcripts come back as Yandex produces them — no
waiting for the user to stop talking before recognition starts.

Confirmed live (see the pilot's planning notes) that `.kz` region streaming
works with the same `Api-Key`/`x-folder-id` credentials as the REST batch API;
the generated protobuf/gRPC stubs come from the `yandexcloud` PyPI package
(already a dependency), not hand-generated or vendored.
"""
import asyncio
from typing import AsyncIterator

import grpc
from yandex.cloud.ai.stt.v3 import stt_pb2, stt_service_pb2_grpc

from app.core.config import settings

# Streaming is only documented/available via gRPC — there is no REST
# equivalent — and only on this regional host (the global host rejects a
# `.kz`-issued API key outright).
STREAM_HOST = "stt.api.yandexcloud.kz:443"

# PCM format the client is expected to send — see web/static/app.js's capture
# pipeline, which downsamples the mic to this exact shape before sending.
SAMPLE_RATE_HERTZ = 16000

# How long a pause must be before Yandex's built-in end-of-utterance detector
# decides the user is done talking and emits a `final` — this is the
# "algorithm that finds when the user gave enough context" that lets the web
# client keep the mic open across a whole hands-free conversation instead of
# requiring a manual stop-tap after every turn. Not so short that a normal
# mid-sentence breath cuts the utterance early, not so long that replies feel
# sluggish to start.
EOU_PAUSE_MS = 700


def _session_options(lang: str) -> stt_pb2.StreamingOptions:
    """Build the first StreamingRequest message: audio format + language.

    `lang` may be a single BCP-47 tag or a comma-separated set, same
    convention as the batch engine's WHITELIST handling in `stt.py`.
    """
    languages = [c.strip() for c in lang.split(",") if c.strip()] or [lang]
    return stt_pb2.StreamingOptions(
        recognition_model=stt_pb2.RecognitionModelOptions(
            audio_format=stt_pb2.AudioFormatOptions(
                raw_audio=stt_pb2.RawAudio(
                    audio_encoding=stt_pb2.RawAudio.LINEAR16_PCM,
                    sample_rate_hertz=SAMPLE_RATE_HERTZ,
                    audio_channel_count=1,
                )
            ),
            text_normalization=stt_pb2.TextNormalizationOptions(
                text_normalization=stt_pb2.TextNormalizationOptions.TEXT_NORMALIZATION_ENABLED,
            ),
            language_restriction=stt_pb2.LanguageRestrictionOptions(
                restriction_type=stt_pb2.LanguageRestrictionOptions.WHITELIST,
                language_code=languages,
            ),
            audio_processing_type=stt_pb2.RecognitionModelOptions.REAL_TIME,
        ),
        eou_classifier=stt_pb2.EouClassifierOptions(
            default_classifier=stt_pb2.DefaultEouClassifier(
                type=stt_pb2.DefaultEouClassifier.DEFAULT,
                max_pause_between_words_hint_ms=EOU_PAUSE_MS,
            )
        ),
    )


def _metadata() -> tuple:
    return (
        ("authorization", f"Api-Key {settings.YANDEX_API_KEY}"),
        ("x-folder-id", settings.YANDEX_FOLDER_ID),
    )


class StreamingSession:
    """One live recognition session over a single gRPC bidi stream.

    Feed PCM chunks in via `send_chunk()`/`end()` from one task while
    consuming `responses()` from another — the two run concurrently against
    the same underlying stream, mirroring how the caller's WebSocket relay
    (browser <-> this session) needs to pump both directions at once.
    """

    def __init__(self, lang: str):
        self._chunks: asyncio.Queue[bytes | None] = asyncio.Queue()
        self._channel = grpc.aio.secure_channel(STREAM_HOST, grpc.ssl_channel_credentials())
        stub = stt_service_pb2_grpc.RecognizerStub(self._channel)
        self._call = stub.RecognizeStreaming(self._requests(lang), metadata=_metadata())

    async def _requests(self, lang: str) -> AsyncIterator[stt_pb2.StreamingRequest]:
        yield stt_pb2.StreamingRequest(session_options=_session_options(lang))
        while True:
            chunk = await self._chunks.get()
            if chunk is None:
                return
            yield stt_pb2.StreamingRequest(chunk=stt_pb2.AudioChunk(data=chunk))

    async def send_chunk(self, pcm: bytes) -> None:
        """Queue one PCM fragment (16-bit LE mono @ 16kHz) for recognition."""
        await self._chunks.put(pcm)

    async def end(self) -> None:
        """Signal no more audio is coming — the request stream will close."""
        await self._chunks.put(None)

    async def responses(self) -> AsyncIterator[dict]:
        """Yield `{"type": "partial"|"final", "text": ...}` as they arrive.

        Other event kinds (status_code keep-alives, eou_update, ...) are
        intentionally not surfaced — the caller only needs transcript text.
        """
        async for resp in self._call:
            kind = resp.WhichOneof("Event")
            if kind not in ("partial", "final"):
                continue
            update = getattr(resp, kind)
            text = " ".join(alt.text for alt in update.alternatives if alt.text).strip()
            if text:
                yield {"type": kind, "text": text}

    async def close(self) -> None:
        await self._channel.close()

"""GigaAM STT engine (self-hosted, OpenAI-compatible transcriptions API).

The model is multilingual on its own — unlike Yandex, there's no language
whitelist to pass, so `lang` is accepted for interface compatibility but not
forwarded.
"""
from typing import Any

from app.engines.base import STTEngine, STTEngineType, EngineError
from app.engines.gigaam.client import GigaamAPIError, transcribe_file
from app.core.config import settings


class GigaamSTTEngine(STTEngine):
    @property
    def engine_type(self) -> STTEngineType:
        return STTEngineType.GIGAAM

    def recognize(self, audio: bytes, lang: str = "ru-RU") -> str:
        try:
            data = transcribe_file(audio, settings.GIGAAM_MODEL)
        except GigaamAPIError as e:
            raise EngineError(str(e)) from e
        return (data.get("text") or "").strip()

    def transcribe(self, audio: bytes, lang: str = "ru-RU") -> list[dict[str, Any]]:
        # verbose_json is the de-facto standard for per-segment timing on
        # OpenAI-compatible transcription servers; fall back to a single
        # untimed utterance if the server ignores response_format and just
        # returns {"text": ...} — no speaker diarization either way.
        try:
            data = transcribe_file(
                audio, settings.GIGAAM_MODEL, response_format="verbose_json"
            )
        except GigaamAPIError as e:
            raise EngineError(str(e)) from e

        segments = data.get("segments") or []
        if not segments:
            text = (data.get("text") or "").strip()
            if not text:
                return []
            return [{"speaker": "0", "text": text,
                      "utterances": [{"text": text, "start_ms": 0, "end_ms": 0}]}]

        utterances = [
            {
                "text": (seg.get("text") or "").strip(),
                "start_ms": int(seg.get("start", 0) * 1000),
                "end_ms": int(seg.get("end", 0) * 1000),
            }
            for seg in segments
        ]
        return [{
            "speaker": "0",
            "text": " ".join(u["text"] for u in utterances).strip(),
            "utterances": utterances,
        }]

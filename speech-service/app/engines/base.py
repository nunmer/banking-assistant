from abc import ABC, abstractmethod
from enum import Enum
from typing import Any


class STTEngineType(str, Enum):
    YANDEX = "yandex"
    GIGAAM = "gigaam"


class TTSEngineType(str, Enum):
    YANDEX = "yandex"
    QWEN = "qwen"


class EngineError(Exception):
    pass


class STTEngine(ABC):
    @property
    @abstractmethod
    def engine_type(self) -> STTEngineType:
        pass

    @abstractmethod
    def recognize(self, audio: bytes, lang: str = "ru-RU") -> str:
        """Recognize speech from WAV bytes; return normalized transcript."""
        pass

    @abstractmethod
    def transcribe(self, audio: bytes, lang: str = "ru-RU") -> list[dict[str, Any]]:
        """Transcribe with per-utterance timestamps and speaker grouping.

        Returns list of channel dicts:
            {"speaker": str, "text": str,
             "utterances": [{"text": str, "start_ms": int, "end_ms": int}]}
        """
        pass


class TTSEngine(ABC):
    @property
    @abstractmethod
    def engine_type(self) -> TTSEngineType:
        pass

    @abstractmethod
    def synthesize(self, text: str, voice: str = "marina", lang: str = "ru-RU",
                   fmt: str = "WAV", speed: float = 1.15) -> bytes:
        """Synthesize text to audio bytes.

        `speed` defaults above Yandex's own neutral 1.0 — full-rate TTS reads
        noticeably slower than natural conversational speech.
        """
        pass

    @abstractmethod
    def list_voices(self) -> list[str]:
        """Return available voice identifiers."""
        pass

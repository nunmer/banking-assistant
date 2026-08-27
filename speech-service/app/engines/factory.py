from app.engines.base import STTEngine, TTSEngine, STTEngineType, TTSEngineType
from app.core.config import settings


def create_stt_engine(engine_type: STTEngineType | str | None = None) -> STTEngine:
    if engine_type is None:
        engine_type = settings.DEFAULT_STT_ENGINE
    if isinstance(engine_type, str):
        try:
            engine_type = STTEngineType(engine_type.lower())
        except ValueError:
            raise ValueError(f"Unknown STT engine: '{engine_type}'. Valid: {[e.value for e in STTEngineType]}")

    if engine_type == STTEngineType.YANDEX:
        from app.engines.yandex.stt import YandexSTTEngine
        return YandexSTTEngine()

    if engine_type == STTEngineType.GIGAAM:
        from app.engines.gigaam.stt import GigaamSTTEngine
        return GigaamSTTEngine()

    raise ValueError(f"Unknown STT engine: {engine_type}")


def create_tts_engine(engine_type: TTSEngineType | str | None = None) -> TTSEngine:
    if engine_type is None:
        engine_type = settings.DEFAULT_TTS_ENGINE
    if isinstance(engine_type, str):
        try:
            engine_type = TTSEngineType(engine_type.lower())
        except ValueError:
            raise ValueError(f"Unknown TTS engine: '{engine_type}'. Valid: {[e.value for e in TTSEngineType]}")

    if engine_type == TTSEngineType.YANDEX:
        from app.engines.yandex.tts import YandexTTSEngine
        return YandexTTSEngine()

    if engine_type == TTSEngineType.QWEN:
        from app.engines.qwen.tts import QwenTTSEngine
        return QwenTTSEngine()

    raise ValueError(f"Unknown TTS engine: {engine_type}")

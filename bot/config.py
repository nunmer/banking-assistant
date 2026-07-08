"""Environment-driven configuration for the Telegram bot."""
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    TELEGRAM_TOKEN: str = ""
    ORCHESTRATOR_URL: str = "http://orchestrator:8000"
    SPEECH_SERVICE_URL: str = "http://host.docker.internal:8000"
    # API key for the speech-service (X-API-Key header). Empty = no auth header.
    SPEECH_API_KEY: str = ""
    SPEECH_DEFAULT_LANG: str = "ru-RU"
    # When True, voice-message replies are sent as voice notes via TTS.
    TTS_VOICE_REPLIES: bool = False
    # Per-language TTS voice (speech-service / Yandex voice names). The voice
    # determines the spoken language, so Kazakh needs a Kazakh voice.
    TTS_VOICE_RU: str = "jane"   # Russian
    TTS_VOICE_KK: str = "madi"   # Kazakh
    TTS_VOICE_EN: str = "jane"   # no English voice available — Russian fallback


settings = Settings()


def voice_for_lang(lang: str | None) -> str:
    """Map a BCP-47 language tag to a configured TTS voice."""
    code = (lang or settings.SPEECH_DEFAULT_LANG)[:2].lower()
    return {
        "kk": settings.TTS_VOICE_KK,
        "ru": settings.TTS_VOICE_RU,
        "en": settings.TTS_VOICE_EN,
    }.get(code, settings.TTS_VOICE_RU)

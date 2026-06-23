"""Environment-driven configuration for the Telegram bot."""
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    TELEGRAM_TOKEN: str = ""
    ORCHESTRATOR_URL: str = "http://orchestrator:8000"
    SPEECH_API_URL: str = "http://speech-api:8002"
    SPEECH_DEFAULT_LANG: str = "ru-RU"
    # When True, voice-message replies are sent as voice notes via TTS.
    # Requires a speech provider that supports /tts (speechkit); whisper does not.
    TTS_VOICE_REPLIES: bool = False


settings = Settings()

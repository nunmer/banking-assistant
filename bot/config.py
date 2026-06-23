"""Environment-driven configuration for the Telegram bot."""
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    TELEGRAM_TOKEN: str = ""
    ORCHESTRATOR_URL: str = "http://orchestrator:8000"
    SPEECH_SERVICE_URL: str = "http://host.docker.internal:8000"
    SPEECH_DEFAULT_LANG: str = "ru-RU"
    # When True, voice-message replies are sent as voice notes via TTS.
    TTS_VOICE_REPLIES: bool = False


settings = Settings()

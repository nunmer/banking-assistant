from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", case_sensitive=True, extra="ignore"
    )

    # App
    APP_ENV: str = "production"
    LOG_LEVEL: str = "INFO"
    LOG_JSON: bool = True
    WORKERS: int = 4

    # CORS: comma-separated origins, or "*" for any
    CORS_ORIGINS: str = "*"

    # Engine selection
    DEFAULT_STT_ENGINE: str = "yandex"
    DEFAULT_TTS_ENGINE: str = "yandex"

    # Database — no default: must be set explicitly (Vault/.env), never a
    # guessable credential baked into source.
    DATABASE_URL: str

    # Celery / Redis
    CELERY_BROKER_URL: str = "redis://localhost:6379/0"
    CELERY_RESULT_BACKEND: str = "redis://localhost:6379/1"
    REDIS_URL: str = "redis://localhost:6379/2"
    CELERY_QUEUE: str = "speech_queue"

    # File storage (shared volume between API and worker)
    UPLOAD_DIR: str = "/app/uploads"

    # Authentication
    API_KEY_ENABLED: bool = False
    API_KEY_HEADER: str = "X-API-Key"

    # Rate limiting (per API key, fixed window)
    RATE_LIMIT_ENABLED: bool = False
    RATE_LIMIT_MAX_REQUESTS: int = 60
    RATE_LIMIT_WINDOW_SECONDS: int = 60

    # Deduplication
    DEDUP_ENABLED: bool = True
    TTS_CACHE_TTL_SECONDS: int = 86400

    # Yandex SpeechKit
    YANDEX_API_KEY: str = ""
    YANDEX_FOLDER_ID: str = ""
    YANDEX_STT_URL: str = "https://stt.api.yandexcloud.kz/stt/v3/recognizeFileAsync"
    YANDEX_TTS_URL: str = "https://tts.api.yandexcloud.kz/tts/v3/utteranceSynthesis"
    YANDEX_TIMEOUT: int = 120
    YANDEX_SSL_VERIFY: bool = True
    YANDEX_HTTPS_PROXY: str = ""
    YANDEX_HTTP_PROXY: str = ""

    # GigaAM (self-hosted, OpenAI-compatible /v1/audio/transcriptions)
    GIGAAM_STT_URL: str = "http://10.0.94.187:8003/v1/audio/transcriptions"
    GIGAAM_MODEL: str = "gigaam-multilingual-large-ctc"
    GIGAAM_TIMEOUT: int = 120

    # Qwen3-TTS (self-hosted, OpenAI-compatible /v1/audio/speech)
    QWEN_TTS_URL: str = "http://10.0.94.187:8002/v1/audio/speech"
    QWEN_TTS_MODEL: str = "Qwen/Qwen3-TTS-12Hz-1.7B-CustomVoice"
    QWEN_TIMEOUT: int = 120

    @property
    def cors_origin_list(self) -> list[str]:
        value = self.CORS_ORIGINS.strip()
        if value == "*":
            return ["*"]
        return [o.strip() for o in value.split(",") if o.strip()]


settings = Settings()

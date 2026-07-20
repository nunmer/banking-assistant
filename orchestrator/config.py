"""Environment-driven configuration for the orchestrator service."""
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # LLM
    OPENAI_API_BASE: str = "https://api.openai.com/v1"
    OPENAI_API_KEY: str = ""
    OPENAI_MODEL: str = "gpt-4o"

    # Persistence
    DATABASE_URL: str = "postgresql+asyncpg://forte:forte@postgres:5432/forte"
    REDIS_URL: str = "redis://redis:6379/0"

    # MIB
    MIB_API_BASE: str = "http://mock-mib:8001"
    MIB_API_TOKEN: str = ""

    # Confirmation TTL (seconds) — user has this long to approve.
    CONFIRM_TTL: int = 120
    # Slot-filling TTL (seconds) — a half-finished parameter collection expires
    # after this so it doesn't linger for the whole session.
    SLOTFILL_TTL: int = 300
    # Session TTL (seconds) — 24h.
    SESSION_TTL: int = 60 * 60 * 24

    # Minimum LLM confidence to act on an intent.
    MIN_CONFIDENCE: float = 0.4


settings = Settings()

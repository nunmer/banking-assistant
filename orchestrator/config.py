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
    # Conversation-window idle timeout (seconds) — same "state simply expires
    # and looks fresh next time" idea as CONFIRM_TTL/SLOTFILL_TTL above,
    # applied to the whole visit: a new turn arriving after this long a gap
    # starts a new window for grouping the durable transcript (see
    # services/session_window.py). Does not affect account lookups, operation
    # history, language preference, or pending confirm/slot-fill — those stay
    # keyed by the permanent identity regardless of how long it's been.
    SESSION_WINDOW_TIMEOUT: int = 30 * 60

    # Minimum LLM confidence to act on an intent.
    MIN_CONFIDENCE: float = 0.4

    # Admin panel (routers/admin.py) — Basic Auth. Intentionally weak default
    # per explicit pilot-stage instruction; the primary protection boundary is
    # meant to be the web gateway's own Basic Auth in front of this (defense
    # in depth, since this port's network exposure wasn't verified).
    ADMIN_USER: str = "admin"
    ADMIN_PASSWORD: str = "admin"


settings = Settings()

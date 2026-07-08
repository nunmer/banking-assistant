"""Pydantic data contracts shared across orchestrator routers and services."""
from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    session_id: str
    text: str
    lang: str | None = None  # BCP-47 tag from the bot (kk-KZ | ru-RU | en-US)


class ChatResponse(BaseModel):
    action: str  # "confirm" | "reply"
    message: str
    # Optional TTS-optimized variant of `message` (e.g. account numbers spelled
    # out digit-by-digit). The bot displays `message` but synthesizes `speech`.
    speech: str | None = None


class IntentResult(BaseModel):
    intent: str
    params: dict[str, str] = Field(default_factory=dict)
    confidence: float = 1.0


class ConfirmReplyRequest(BaseModel):
    session_id: str
    approved: bool


class MIBResult(BaseModel):
    status: str
    tx_id: str
    message: str

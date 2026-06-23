"""Pydantic data contracts shared across orchestrator routers and services."""
from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    session_id: str
    text: str


class ChatResponse(BaseModel):
    action: str  # "confirm" | "reply"
    message: str


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

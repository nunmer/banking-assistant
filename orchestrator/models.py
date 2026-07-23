"""Pydantic data contracts shared across orchestrator routers and services."""
from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    session_id: str
    text: str
    lang: str | None = None  # BCP-47 tag from the bot (kk-KZ | ru-RU | en-US)
    # Which surface sent this ("telegram" | "web"); used to attribute executed
    # operations in history and to cross-notify the other channel.
    channel: str | None = None
    # The user's first name, when the channel knows it (Telegram bot/Mini App;
    # never available for an anonymous browser session). Used to personalise
    # the greeting reply — omitted entirely when unknown, not guessed.
    user_name: str | None = None


class ChatResponse(BaseModel):
    # "confirm" — awaiting yes/no; "collect" — asking for a missing parameter;
    # "reply" — terminal message. The bot only special-cases "confirm" (adds the
    # inline keyboard); "collect" and "reply" are shown/spoken as plain messages.
    action: str
    message: str
    # Optional TTS-optimized variant of `message` (e.g. account numbers spelled
    # out digit-by-digit). The bot displays `message` but synthesizes `speech`.
    speech: str | None = None
    # Language this response is written in (kk-KZ | ru-RU | en-US). The bot uses
    # it to pick the matching TTS voice, since the reply language may differ from
    # the session language when the user switches mid-conversation.
    lang: str | None = None
    # Set when this reply completed an operation: {summary, status, tx_id,
    # created_at}. Lets clients append a persistent history card immediately.
    operation: dict | None = None
    # False only for the "I didn't understand"/unknown-intent reply. Lets a
    # hands-free voice client stay silent on ambient chatter it happened to
    # pick up, instead of interrupting with a spoken "I don't understand" for
    # every stray fragment that wasn't actually addressed to it.
    understood: bool = True


class IntentResult(BaseModel):
    intent: str
    params: dict[str, str] = Field(default_factory=dict)
    confidence: float = 1.0
    # Language the user wrote in (kk-KZ | ru-RU | en-US), detected by the LLM so
    # the assistant can reply in kind even when the user switches mid-conversation.
    lang: str | None = None
    # Set only when intent="unknown": a short topic paraphrase ("курс доллара
    # к тенге") of what the user asked about, in `lang`, so the decline reply
    # can name it instead of dumping the generic capability list. Never an
    # actual answer/figure — see the SYSTEM_PROMPT rule in llm.py forbidding
    # the model from guessing a real value here.
    topic: str | None = None


class ConfirmReplyRequest(BaseModel):
    session_id: str
    approved: bool
    channel: str | None = None  # "telegram" | "web"


class MIBResult(BaseModel):
    status: str
    tx_id: str
    message: str

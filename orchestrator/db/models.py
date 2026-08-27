"""SQLAlchemy ORM models for the scenario catalogue."""
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class Operation(Base):
    """A completed (executed or failed) banking operation.

    The durable operation history: recorded once at execution time, listed
    in the web UI after any restart. Keyed by session_id.
    """

    __tablename__ = "operations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    session_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    intent: Mapped[str] = mapped_column(String(64), nullable=False)
    # The confirmation text the user approved, in the language they approved it.
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    lang: Mapped[str] = mapped_column(String(8), nullable=False, default="ru-RU")
    status: Mapped[str] = mapped_column(String(16), nullable=False)  # success | error
    tx_id: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    channel: Mapped[str] = mapped_column(String(16), nullable=False, default="unknown")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class Message(Base):
    """One turn of a conversation (user utterance or bot reply).

    Durable transcript log, keyed by session_id like Operation — captures
    every chat turn (small talk, slot-filling, confirmations, declines), not
    just completed operations. Written once per side of a turn from the
    single /chat choke point both channels go through (routers/chat.py).
    """

    __tablename__ = "messages"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    session_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    channel: Mapped[str] = mapped_column(String(16), nullable=False, default="unknown")
    role: Mapped[str] = mapped_column(String(16), nullable=False)  # user | bot
    text: Mapped[str] = mapped_column(Text, nullable=False)
    lang: Mapped[str | None] = mapped_column(String(8), nullable=True)
    # Correlates this row to its DebugEvent rows (classify/mib/stt/tts steps
    # for the same turn). Nullable: rows logged before this feature has none.
    turn_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), index=True
    )


class DebugEvent(Base):
    """One pipeline step for a turn — STT, LLM classify/extract, enrich, MIB, TTS.

    Written by web/bot (stt/tts, via POST /debug/events — they hold no DB
    connection) and directly in-process by orchestrator's own pipeline steps
    (classify/extract_param/enrich/mib_execute), all tagged with the same
    turn_id so the admin panel can pull one turn's full trace in one query.
    """

    __tablename__ = "debug_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    session_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    turn_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    step: Mapped[str] = mapped_column(String(32), nullable=False)
    detail: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), index=True
    )


class SessionIdentity(Base):
    """Optional identity for a session — lets the admin panel search by

    username or first name instead of a bare session id. One row per
    session, upserted on any /chat call that carries a username/first_name.
    """

    __tablename__ = "session_identities"

    session_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    username: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    first_name: Mapped[str | None] = mapped_column(String(128), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class Scenario(Base):
    __tablename__ = "scenarios"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    intent: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    display_name: Mapped[str] = mapped_column(String(128), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    required_params: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    optional_params: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    confirm_template: Mapped[str] = mapped_column(Text, nullable=False)
    # Per-language confirm templates: {"ru-RU": "...", "kk-KZ": "...", "en-US": "..."}
    confirm_templates: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    mib_endpoint: Mapped[str] = mapped_column(String(256), nullable=False)
    mib_method: Mapped[str] = mapped_column(String(8), nullable=False, default="POST")
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

"""SQLAlchemy ORM models for the scenario catalogue."""
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class Operation(Base):
    """A completed (executed or failed) banking operation.

    The durable operation history behind both channels: recorded once at
    execution time, listed in the Mini App / web UI after any restart. Keyed by
    session_id — which for Telegram-authenticated users is the Telegram user
    id, so Telegram-chat and Mini App history are one and the same.
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

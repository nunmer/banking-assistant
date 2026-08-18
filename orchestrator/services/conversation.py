"""Durable conversation transcript in PostgreSQL.

`log` is called once per side of every chat turn from the single /chat entry
point (routers/chat.py), covering both channels. Read-side helpers back the
admin panel's Conversations tab. Mirrors services/history.py's
try/except-log-and-continue pattern: a logging failure must never break a
chat reply, and admin reads degrade to an empty list rather than a 500.
"""
import logging

from sqlalchemy import func, or_, select

from orchestrator.db.database import SessionLocal
from orchestrator.db.models import Message, SessionIdentity

logger = logging.getLogger("orchestrator.conversation")


async def log(
    session_id: str,
    channel: str,
    role: str,
    text: str,
    lang: str | None = None,
    turn_id: str | None = None,
) -> None:
    """Persist one turn's message; log-and-continue on storage errors."""
    if not text:
        return
    try:
        async with SessionLocal() as db:
            db.add(
                Message(
                    session_id=session_id, channel=channel, role=role, text=text,
                    lang=lang, turn_id=turn_id,
                )
            )
            await db.commit()
    except Exception as e:  # noqa: BLE001 — conversation logging must never break the flow
        logger.error("failed to log message for %s: %s", session_id, e)


async def list_sessions(limit: int = 50, offset: int = 0, q: str | None = None) -> list[dict]:
    """Most-recently-active sessions, newest first, with a message count.

    `q`, when given, filters by session_id / Telegram @username / first_name
    (case-insensitive substring match) — the admin panel's session search.
    """
    try:
        async with SessionLocal() as db:
            rn = (
                func.row_number()
                .over(partition_by=Message.session_id, order_by=Message.created_at.desc())
                .label("rn")
            )
            last_per_session = select(
                Message.session_id, Message.channel, Message.text, Message.created_at, rn
            ).subquery()

            stmt = (
                select(
                    last_per_session.c.session_id,
                    last_per_session.c.channel,
                    last_per_session.c.text,
                    last_per_session.c.created_at,
                    SessionIdentity.username,
                    SessionIdentity.first_name,
                )
                .where(last_per_session.c.rn == 1)
                .outerjoin(
                    SessionIdentity,
                    SessionIdentity.session_id == last_per_session.c.session_id,
                )
            )
            if q:
                like = f"%{q}%"
                stmt = stmt.where(
                    or_(
                        last_per_session.c.session_id.ilike(like),
                        SessionIdentity.username.ilike(like),
                        SessionIdentity.first_name.ilike(like),
                    )
                )
            stmt = stmt.order_by(last_per_session.c.created_at.desc()).limit(limit).offset(offset)
            rows = (await db.execute(stmt)).all()

            session_ids = [r.session_id for r in rows]
            counts: dict[str, int] = {}
            if session_ids:
                counts_stmt = (
                    select(Message.session_id, func.count().label("cnt"))
                    .where(Message.session_id.in_(session_ids))
                    .group_by(Message.session_id)
                )
                counts = {r.session_id: r.cnt for r in (await db.execute(counts_stmt)).all()}
    except Exception as e:  # noqa: BLE001
        logger.error("failed to list conversation sessions: %s", e)
        return []

    return [
        {
            "session_id": r.session_id,
            "channel": r.channel,
            "last_message": r.text,
            "last_at": r.created_at.isoformat() if r.created_at else None,
            "message_count": counts.get(r.session_id, 0),
            "username": r.username,
            "first_name": r.first_name,
        }
        for r in rows
    ]


async def list_messages(session_id: str, limit: int = 200) -> list[dict]:
    """Full chronological transcript for one session, oldest first."""
    try:
        async with SessionLocal() as db:
            result = await db.execute(
                select(Message)
                .where(Message.session_id == session_id)
                .order_by(Message.created_at.asc(), Message.id.asc())
                .limit(limit)
            )
            rows = result.scalars().all()
    except Exception as e:  # noqa: BLE001
        logger.error("failed to list messages for %s: %s", session_id, e)
        return []

    return [
        {
            "role": m.role,
            "text": m.text,
            "channel": m.channel,
            "lang": m.lang,
            "turn_id": m.turn_id,
            "created_at": m.created_at.isoformat() if m.created_at else None,
        }
        for m in rows
    ]

"""Durable operation history in PostgreSQL.

`record` is called once per executed operation (success or error) from both
confirmation paths; `list_recent` feeds the Mini App / web history view.
Failures to record never break the user-facing flow — history is best-effort.
"""
import logging

from sqlalchemy import select

from orchestrator.db.database import SessionLocal
from orchestrator.db.models import Operation

logger = logging.getLogger("orchestrator.history")


async def record(
    session_id: str,
    intent: str,
    summary: str,
    lang: str,
    status: str,
    tx_id: str = "",
    channel: str = "unknown",
) -> None:
    """Persist one executed operation; log-and-continue on storage errors."""
    try:
        async with SessionLocal() as db:
            db.add(
                Operation(
                    session_id=session_id,
                    intent=intent,
                    summary=summary,
                    lang=lang,
                    status=status,
                    tx_id=tx_id,
                    channel=channel,
                )
            )
            await db.commit()
    except Exception as e:  # noqa: BLE001 — history must never break the flow
        logger.error("failed to record operation for %s: %s", session_id, e)


async def list_recent(session_id: str, limit: int = 20) -> list[dict]:
    """Most recent operations for a session, newest first."""
    try:
        async with SessionLocal() as db:
            result = await db.execute(
                select(Operation)
                .where(Operation.session_id == session_id)
                .order_by(Operation.created_at.desc(), Operation.id.desc())
                .limit(limit)
            )
            rows = result.scalars().all()
    except Exception as e:  # noqa: BLE001
        logger.error("failed to list operations for %s: %s", session_id, e)
        return []

    return [
        {
            "intent": op.intent,
            "summary": op.summary,
            "lang": op.lang,
            "status": op.status,
            "tx_id": op.tx_id,
            "channel": op.channel,
            "created_at": op.created_at.isoformat() if op.created_at else None,
        }
        for op in rows
    ]

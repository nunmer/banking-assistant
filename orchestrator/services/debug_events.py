"""Per-turn debug trace in PostgreSQL — one row per pipeline step.

`log_event` is called from two places: in-process by orchestrator's own
pipeline (classify/extract_param/enrich/mib_execute, via routers/chat.py)
and via POST /debug/events by web/bot (stt/tts — they hold no DB connection
of their own). Mirrors services/history.py's try/except-log-and-continue
pattern: a logging failure must never break a chat reply or the /debug/events
endpoint itself.
"""
import logging

from sqlalchemy import select

from orchestrator.db.database import SessionLocal
from orchestrator.db.models import DebugEvent

logger = logging.getLogger("orchestrator.debug_events")


async def log_event(session_id: str, turn_id: str, step: str, detail: dict) -> None:
    try:
        async with SessionLocal() as db:
            db.add(
                DebugEvent(session_id=session_id, turn_id=turn_id, step=step, detail=detail)
            )
            await db.commit()
    except Exception as e:  # noqa: BLE001 — debug tracing must never break the flow
        logger.error("failed to log debug event (turn=%s, step=%s): %s", turn_id, step, e)


async def list_events(turn_id: str) -> list[dict]:
    """Full chronological trace for one turn, oldest first."""
    try:
        async with SessionLocal() as db:
            result = await db.execute(
                select(DebugEvent)
                .where(DebugEvent.turn_id == turn_id)
                .order_by(DebugEvent.created_at.asc(), DebugEvent.id.asc())
            )
            rows = result.scalars().all()
    except Exception as e:  # noqa: BLE001
        logger.error("failed to list debug events for turn %s: %s", turn_id, e)
        return []

    return [
        {
            "step": e.step,
            "detail": e.detail,
            "created_at": e.created_at.isoformat() if e.created_at else None,
        }
        for e in rows
    ]

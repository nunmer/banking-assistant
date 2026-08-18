"""Telegram identity per session — lets the admin panel search sessions by

`@username` ("tg nick") or first name instead of a bare numeric session id.
Upserted from routers/chat.py whenever a /chat call carries either field
(bot messages and Mini App sessions both do); best-effort, same
try/except-log-and-continue pattern as services/history.py.
"""
import logging

from sqlalchemy import func
from sqlalchemy.dialects.postgresql import insert as pg_insert

from orchestrator.db.database import SessionLocal
from orchestrator.db.models import SessionIdentity

logger = logging.getLogger("orchestrator.session_identity")


async def upsert(session_id: str, username: str | None = None, first_name: str | None = None) -> None:
    if not username and not first_name:
        return
    values = {"session_id": session_id, "updated_at": func.now()}
    if username:
        values["username"] = username
    if first_name:
        values["first_name"] = first_name
    try:
        async with SessionLocal() as db:
            stmt = pg_insert(SessionIdentity).values(**values)
            stmt = stmt.on_conflict_do_update(
                index_elements=[SessionIdentity.session_id],
                set_={k: v for k, v in values.items() if k != "session_id"},
            )
            await db.execute(stmt)
            await db.commit()
    except Exception as e:  # noqa: BLE001 — identity capture must never break the flow
        logger.error("failed to upsert session identity for %s: %s", session_id, e)

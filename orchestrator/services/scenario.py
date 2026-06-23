"""Scenario catalogue queries backed by PostgreSQL."""
from sqlalchemy import select

from orchestrator.db.database import SessionLocal
from orchestrator.db.models import Scenario


async def get(intent: str) -> Scenario | None:
    """Return the active scenario for an intent, or None if not found."""
    async with SessionLocal() as session:
        result = await session.execute(
            select(Scenario).where(
                Scenario.intent == intent,
                Scenario.active.is_(True),
            )
        )
        return result.scalar_one_or_none()

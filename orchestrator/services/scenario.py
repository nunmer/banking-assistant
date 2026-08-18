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


# ── Admin catalogue management ───────────────────────────────────────────
# Below here is used only by the admin panel (routers/admin.py) — the chat
# classification path above (`get`) is untouched so it keeps its narrow,
# active-only contract.


async def list_all() -> list[Scenario]:
    """Every scenario, active or not — for the admin catalogue view."""
    async with SessionLocal() as session:
        result = await session.execute(select(Scenario).order_by(Scenario.intent))
        return list(result.scalars().all())


async def get_any(intent: str) -> Scenario | None:
    """Return a scenario by intent regardless of its active state."""
    async with SessionLocal() as session:
        result = await session.execute(select(Scenario).where(Scenario.intent == intent))
        return result.scalar_one_or_none()


async def create(fields: dict) -> Scenario:
    """Insert a new scenario row from admin-supplied fields."""
    async with SessionLocal() as session:
        sc = Scenario(**fields)
        session.add(sc)
        await session.commit()
        await session.refresh(sc)
        return sc


async def update(intent: str, patch: dict) -> Scenario | None:
    """Apply a partial update to an existing scenario; None if not found."""
    async with SessionLocal() as session:
        result = await session.execute(select(Scenario).where(Scenario.intent == intent))
        sc = result.scalar_one_or_none()
        if sc is None:
            return None
        for key, value in patch.items():
            setattr(sc, key, value)
        await session.commit()
        await session.refresh(sc)
        return sc

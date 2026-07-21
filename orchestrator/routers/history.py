"""GET /history/{session_id} — recent executed operations for a session."""
from fastapi import APIRouter, Query

from orchestrator.services import history

router = APIRouter()


@router.get("/history/{session_id}")
async def get_history(
    session_id: str, limit: int = Query(default=20, ge=1, le=50)
) -> dict:
    return {"operations": await history.list_recent(session_id, limit)}

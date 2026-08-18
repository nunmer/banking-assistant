"""POST /debug/events — lets web/bot record a pipeline step they own (STT,
TTS) that orchestrator itself never sees directly.

No auth: same trust boundary as /chat (internal network only, reached from
web/bot, never exposed to the public internet — see docker-compose.yml,
where only `web`'s port is published).
"""
from fastapi import APIRouter
from pydantic import BaseModel

from orchestrator.services import debug_events, session_window

router = APIRouter()


class DebugEventIn(BaseModel):
    session_id: str
    turn_id: str
    step: str
    detail: dict = {}


@router.post("/debug/events")
async def post_debug_event(body: DebugEventIn) -> dict:
    # web/bot send the permanent identity — resolve it to the same windowed
    # conversation id /chat uses (see services/session_window.py), so an
    # stt/tts event lands grouped with the classify/enrich/mib_execute events
    # for the same visit, not a stale one from a much earlier session.
    history_session_id = await session_window.resolve(body.session_id)
    await debug_events.log_event(history_session_id, body.turn_id, body.step, body.detail)
    return {"ok": True}

"""Forte Assistant orchestrator — FastAPI application."""
import logging

from fastapi import APIRouter, FastAPI
from pydantic import BaseModel

from orchestrator.routers import admin, chat, confirm, debug, document, history
from orchestrator.services import confirm as confirm_svc
from orchestrator.services import session as session_svc
from orchestrator.services import slotfill as slotfill_svc

logging.basicConfig(level=logging.INFO)

app = FastAPI(title="Forte Assistant Orchestrator")

app.include_router(chat.router)
app.include_router(confirm.router)
app.include_router(history.router)
app.include_router(document.router)
app.include_router(admin.router)
app.include_router(debug.router)


class LangRequest(BaseModel):
    session_id: str
    lang: str  # BCP-47: kk-KZ | ru-RU | en-US


class SessionResetRequest(BaseModel):
    session_id: str


_VALID_LANGS = {"kk-KZ", "ru-RU", "en-US"}

_session_router = APIRouter(prefix="/session")


@_session_router.post("/lang")
async def set_lang(req: LangRequest) -> dict:
    if req.lang not in _VALID_LANGS:
        from fastapi import HTTPException
        raise HTTPException(status_code=400, detail=f"Unsupported lang: {req.lang}")
    await session_svc.touch(req.session_id, updates={"lang": req.lang})
    return {"ok": True, "lang": req.lang}


@_session_router.get("/lang/{session_id}")
async def get_lang(session_id: str) -> dict:
    data = await session_svc.get(session_id)
    return {"lang": data.get("lang", session_svc.DEFAULT_LANG)}


@_session_router.post("/reset")
async def reset_session(req: SessionResetRequest) -> dict:
    """Clear any stuck in-progress state (a pending confirmation or a

    half-answered slot-filling collection) without touching the durable
    conversation history/operations record. One Telegram account is always
    one continuous conversation by design (bot chat and the Mini App share
    it) — this is the "start fresh" action for when that's not what the
    user wants right now, wired to Telegram's own /start command.
    """
    await confirm_svc.clear_pending(req.session_id)
    await slotfill_svc.clear(req.session_id)
    return {"ok": True}


app.include_router(_session_router)


@app.get("/health")
async def health() -> dict:
    return {"status": "ok"}

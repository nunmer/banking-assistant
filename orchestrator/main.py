"""Forte Assistant orchestrator — FastAPI application."""
import logging

from fastapi import APIRouter, FastAPI
from pydantic import BaseModel

from orchestrator.routers import chat, confirm, document, history
from orchestrator.services import session as session_svc

logging.basicConfig(level=logging.INFO)

app = FastAPI(title="Forte Assistant Orchestrator")

app.include_router(chat.router)
app.include_router(confirm.router)
app.include_router(history.router)
app.include_router(document.router)


class LangRequest(BaseModel):
    session_id: str
    lang: str  # BCP-47: kk-KZ | ru-RU | en-US


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


app.include_router(_session_router)


@app.get("/health")
async def health() -> dict:
    return {"status": "ok"}

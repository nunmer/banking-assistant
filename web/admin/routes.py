"""Admin panel routes: page shell, live flags, container logs, and proxies
to orchestrator's scenario/conversation admin API.

Every route here sits behind `require_admin` (router-level dependency) —
the browser's Basic Auth challenge covers the page and every /admin/api/*
call alike. Calls to orchestrator build their own Basic Auth from this
service's own env vars rather than forwarding whatever the browser sent.
"""
import os
from urllib.parse import quote

import httpx
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import HTMLResponse, PlainTextResponse
from pydantic import BaseModel

from web.admin import docker_logs, runtime_config
from web.admin.auth import ADMIN_PASSWORD, ADMIN_USER, require_admin

ORCHESTRATOR_URL = os.getenv("ORCHESTRATOR_URL", "http://orchestrator:8000")
_ADMIN_AUTH = (ADMIN_USER, ADMIN_PASSWORD)
_STATIC_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "static")

router = APIRouter(prefix="/admin", tags=["admin"], dependencies=[Depends(require_admin)])


@router.get("")
async def admin_page() -> HTMLResponse:
    with open(os.path.join(_STATIC_DIR, "admin.html"), "r", encoding="utf-8") as f:
        return HTMLResponse(f.read())


# ── Live feature flags ───────────────────────────────────────────────────


class FlagsPatch(BaseModel):
    streaming_voice_enabled: bool | None = None
    tts_voice_ru: str | None = None
    tts_voice_kk: str | None = None
    tts_voice_default: str | None = None
    stt_langs: str | None = None
    rate_limit_per_min: int | None = None
    tts_max_chars: int | None = None


@router.get("/api/flags")
async def get_flags() -> dict:
    return await runtime_config.get_config()


@router.post("/api/flags")
async def set_flags(body: FlagsPatch) -> dict:
    patch = {k: v for k, v in body.model_dump().items() if v is not None}
    try:
        return await runtime_config.update_config(patch)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


# ── Container logs (Docker socket) ───────────────────────────────────────


@router.get("/api/containers")
async def list_containers() -> list[dict]:
    try:
        return docker_logs.list_containers()
    except docker_logs.DockerUnavailable as e:
        raise HTTPException(status_code=503, detail=f"Docker unavailable: {e}")


@router.get("/api/logs/{name}")
async def get_logs(name: str, lines: int = 200) -> PlainTextResponse:
    try:
        text = docker_logs.tail_logs(name, lines=lines)
    except docker_logs.ContainerNotFound:
        raise HTTPException(status_code=404, detail=f"No container named '{name}'")
    except docker_logs.DockerUnavailable as e:
        raise HTTPException(status_code=503, detail=f"Docker unavailable: {e}")
    return PlainTextResponse(text)


# ── Conversations + scenarios (proxied to orchestrator) ──────────────────


async def _proxy(method: str, path: str, **kwargs):
    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.request(
            method, f"{ORCHESTRATOR_URL}/admin{path}", auth=_ADMIN_AUTH, **kwargs
        )
    if resp.status_code >= 400:
        raise HTTPException(status_code=resp.status_code, detail=resp.text[:500])
    return resp.json()


@router.get("/api/conversations/sessions")
async def list_sessions(limit: int = 50, offset: int = 0, q: str | None = None) -> list[dict]:
    params = {"limit": limit, "offset": offset}
    if q:
        params["q"] = q
    return await _proxy("GET", "/conversations/sessions", params=params)


@router.get("/api/conversations/{session_id}")
async def get_conversation(session_id: str, limit: int = 200) -> list[dict]:
    # Windowed session ids contain "#" (see services/session_window.py) — an
    # unescaped "#" in a URL is a fragment separator, silently dropped along
    # with everything after it by any URL-parsing HTTP client (including
    # httpx here), so it must be percent-encoded before going into the
    # outbound proxy URL — otherwise this ends up fetching the WRONG (bare
    # identity's pre-windowing) session and returns 200 with stale data,
    # not a visible error.
    return await _proxy(
        "GET", f"/conversations/{quote(session_id, safe='')}", params={"limit": limit}
    )


@router.get("/api/turns/{turn_id}/events")
async def get_turn_events(turn_id: str) -> list[dict]:
    return await _proxy("GET", f"/turns/{quote(turn_id, safe='')}/events")


@router.get("/api/scenarios")
async def list_scenarios() -> list[dict]:
    return await _proxy("GET", "/scenarios")


@router.get("/api/scenarios/{intent}")
async def get_scenario(intent: str) -> dict:
    return await _proxy("GET", f"/scenarios/{quote(intent, safe='')}")


@router.post("/api/scenarios", status_code=201)
async def create_scenario(body: dict) -> dict:
    return await _proxy("POST", "/scenarios", json=body)


@router.put("/api/scenarios/{intent}")
async def update_scenario(intent: str, body: dict) -> dict:
    return await _proxy("PUT", f"/scenarios/{quote(intent, safe='')}", json=body)

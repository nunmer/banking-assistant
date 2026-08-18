"""Admin API — conversation transcripts and scenario catalogue management.

Reached only via the web gateway's own /admin proxy (its Basic Auth is the
primary gate), but this router carries its own independent Basic Auth check
too — defense in depth, since this service's network exposure beyond the
gateway wasn't verified. Never surfaces secrets (API keys, tokens, DB/Redis
URLs) — only scenario/conversation data the admin panel legitimately needs.
"""
import secrets

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from pydantic import BaseModel

from orchestrator.config import settings
from orchestrator.db.models import Scenario
from orchestrator.services import conversation, debug_events, scenario as scenario_svc

_security = HTTPBasic()


def require_admin(credentials: HTTPBasicCredentials = Depends(_security)) -> None:
    user_ok = secrets.compare_digest(credentials.username, settings.ADMIN_USER)
    pass_ok = secrets.compare_digest(credentials.password, settings.ADMIN_PASSWORD)
    if not (user_ok and pass_ok):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid admin credentials",
            headers={"WWW-Authenticate": "Basic"},
        )


router = APIRouter(prefix="/admin", tags=["admin"], dependencies=[Depends(require_admin)])


class ScenarioIn(BaseModel):
    intent: str
    display_name: str
    description: str | None = None
    required_params: list[str] = []
    optional_params: list[str] = []
    confirm_template: str
    confirm_templates: dict[str, str] = {}
    mib_endpoint: str
    mib_method: str = "POST"
    active: bool = True


class ScenarioPatch(BaseModel):
    display_name: str | None = None
    description: str | None = None
    required_params: list[str] | None = None
    optional_params: list[str] | None = None
    confirm_template: str | None = None
    confirm_templates: dict[str, str] | None = None
    mib_endpoint: str | None = None
    mib_method: str | None = None
    active: bool | None = None


def _scenario_out(sc: Scenario) -> dict:
    return {
        "intent": sc.intent,
        "display_name": sc.display_name,
        "description": sc.description,
        "required_params": sc.required_params,
        "optional_params": sc.optional_params,
        "confirm_template": sc.confirm_template,
        "confirm_templates": sc.confirm_templates,
        "mib_endpoint": sc.mib_endpoint,
        "mib_method": sc.mib_method,
        "active": sc.active,
        "created_at": sc.created_at.isoformat() if sc.created_at else None,
    }


@router.get("/scenarios")
async def list_scenarios() -> list[dict]:
    rows = await scenario_svc.list_all()
    return [_scenario_out(sc) for sc in rows]


@router.get("/scenarios/{intent}")
async def get_scenario(intent: str) -> dict:
    sc = await scenario_svc.get_any(intent)
    if sc is None:
        raise HTTPException(status_code=404, detail="Scenario not found")
    return _scenario_out(sc)


@router.post("/scenarios", status_code=201)
async def create_scenario(body: ScenarioIn) -> dict:
    existing = await scenario_svc.get_any(body.intent)
    if existing is not None:
        raise HTTPException(status_code=409, detail=f"Scenario '{body.intent}' already exists")
    sc = await scenario_svc.create(body.model_dump())
    return _scenario_out(sc)


@router.put("/scenarios/{intent}")
async def update_scenario(intent: str, body: ScenarioPatch) -> dict:
    patch = {k: v for k, v in body.model_dump().items() if v is not None}
    sc = await scenario_svc.update(intent, patch)
    if sc is None:
        raise HTTPException(status_code=404, detail="Scenario not found")
    return _scenario_out(sc)


@router.get("/conversations/sessions")
async def list_sessions(limit: int = 50, offset: int = 0, q: str | None = None) -> list[dict]:
    return await conversation.list_sessions(limit=limit, offset=offset, q=q)


@router.get("/conversations/{session_id}")
async def get_conversation(session_id: str, limit: int = 200) -> list[dict]:
    return await conversation.list_messages(session_id, limit=limit)


@router.get("/turns/{turn_id}/events")
async def get_turn_events(turn_id: str) -> list[dict]:
    return await debug_events.list_events(turn_id)

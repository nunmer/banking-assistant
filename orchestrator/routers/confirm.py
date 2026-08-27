"""POST /confirm/reply — execute or cancel a pending confirmation."""
import logging

from fastapi import APIRouter

from orchestrator.i18n import t
from orchestrator.models import ChatResponse, ConfirmReplyRequest
from orchestrator.routers.chat import _record_operation
from orchestrator.services import confirm, mib, session

logger = logging.getLogger("orchestrator.confirm")

router = APIRouter()


@router.post("/confirm/reply", response_model=ChatResponse)
async def confirm_reply(req: ConfirmReplyRequest) -> ChatResponse:
    user_session = await session.get(req.session_id)
    lang = user_session.get("lang", "ru-RU")

    pending = await confirm.get_pending(req.session_id)
    if pending is None:
        return ChatResponse(action="reply", message=t(lang, "no_pending"))

    # Clear first so a double-tap can never execute twice.
    await confirm.clear_pending(req.session_id)

    if not req.approved:
        return ChatResponse(action="reply", message=t(lang, "cancelled"))

    result = await mib.execute(
        endpoint=pending["mib_endpoint"],
        params=pending["params"],
        method=pending.get("mib_method", "POST"),
    )

    operation = await _record_operation(req, pending, result, lang)
    return ChatResponse(action="reply", message=result.message, operation=operation)

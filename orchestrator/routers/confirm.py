"""POST /confirm/reply — execute or cancel a pending confirmation."""
import logging

from fastapi import APIRouter

from orchestrator.models import ChatResponse, ConfirmReplyRequest
from orchestrator.services import confirm, mib

logger = logging.getLogger("orchestrator.confirm")

router = APIRouter()


@router.post("/confirm/reply", response_model=ChatResponse)
async def confirm_reply(req: ConfirmReplyRequest) -> ChatResponse:
    pending = await confirm.get_pending(req.session_id)
    if pending is None:
        return ChatResponse(
            action="reply",
            message="No pending action found. It may have expired — please ask again.",
        )

    # Clear first so a double-tap can never execute twice.
    await confirm.clear_pending(req.session_id)

    if not req.approved:
        return ChatResponse(action="reply", message="Cancelled.")

    result = await mib.execute(
        endpoint=pending["mib_endpoint"],
        params=pending["params"],
        method=pending.get("mib_method", "POST"),
    )

    return ChatResponse(action="reply", message=result.message)

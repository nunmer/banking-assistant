"""POST /chat — the main entry point. Text in, action out."""
import logging

from fastapi import APIRouter

from orchestrator.config import settings
from orchestrator.models import ChatRequest, ChatResponse
from orchestrator.services import confirm, llm, scenario

logger = logging.getLogger("orchestrator.chat")

router = APIRouter()


@router.post("/chat", response_model=ChatResponse)
async def chat(req: ChatRequest) -> ChatResponse:
    # 1. Classify intent via LLM.
    intent_result = await llm.classify(req.text, req.session_id)
    logger.info(
        "session=%s intent=%s confidence=%.2f",
        req.session_id,
        intent_result.intent,
        intent_result.confidence,
    )

    if (
        intent_result.intent in ("unknown", "")
        or intent_result.confidence < settings.MIN_CONFIDENCE
    ):
        return ChatResponse(
            action="reply",
            message="Sorry, I couldn't understand that. Try: transfer, balance, pay a bill, or a statement.",
        )

    # 2. Look the intent up in the scenario catalogue.
    sc = await scenario.get(intent_result.intent)
    if sc is None:
        return ChatResponse(action="reply", message="Sorry, I can't help with that.")

    # 3. Validate required parameters are present.
    missing = [p for p in sc.required_params if p not in intent_result.params]
    if missing:
        return ChatResponse(
            action="reply",
            message=f"Please provide: {', '.join(missing)}",
        )

    # 4. Store the pending confirmation in Redis.
    await confirm.create_pending(
        session_id=req.session_id,
        scenario=sc,
        params=intent_result.params,
    )

    # 5. Ask the user to confirm.
    try:
        msg = sc.confirm_template.format(**intent_result.params)
    except (KeyError, IndexError):
        # Template referenced a param the LLM did not extract — fall back gracefully.
        msg = f"{sc.display_name} — confirm?"

    return ChatResponse(action="confirm", message=msg)

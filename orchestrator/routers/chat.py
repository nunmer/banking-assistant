"""POST /chat — the main entry point. Text in, action out."""
import logging

from fastapi import APIRouter

from orchestrator.config import settings
from orchestrator.i18n import t
from orchestrator.models import ChatRequest, ChatResponse
from orchestrator.services import affirm, confirm, llm, mib, scenario, session, speechtext

logger = logging.getLogger("orchestrator.chat")

router = APIRouter()


@router.post("/chat", response_model=ChatResponse)
async def chat(req: ChatRequest) -> ChatResponse:
    # 1. Touch the session, optionally persisting the lang from this request.
    session_updates = {"lang": req.lang} if req.lang else None
    user_session = await session.touch(req.session_id, updates=session_updates)
    lang = user_session.get("lang", "ru-RU")

    # 1a. If a confirmation is pending, a spoken/typed yes/no resolves it.
    pending = await confirm.get_pending(req.session_id)
    if pending is not None:
        decision = affirm.classify_reply(req.text)
        if decision == "yes":
            await confirm.clear_pending(req.session_id)
            result = await mib.execute(
                endpoint=pending["mib_endpoint"],
                params=pending["params"],
                method=pending.get("mib_method", "POST"),
            )
            return ChatResponse(action="reply", message=result.message)
        if decision == "no":
            await confirm.clear_pending(req.session_id)
            return ChatResponse(action="reply", message=t(lang, "cancelled"))
        # Not a yes/no — fall through and treat it as a brand-new request.

    # 2. Classify intent via LLM.
    intent_result = await llm.classify(req.text, req.session_id)
    logger.info(
        "session=%s lang=%s intent=%s confidence=%.2f",
        req.session_id,
        lang,
        intent_result.intent,
        intent_result.confidence,
    )

    if (
        intent_result.intent in ("unknown", "")
        or intent_result.confidence < settings.MIN_CONFIDENCE
    ):
        return ChatResponse(action="reply", message=t(lang, "unknown_intent"))

    # 3. Look the intent up in the scenario catalogue.
    sc = await scenario.get(intent_result.intent)
    if sc is None:
        return ChatResponse(action="reply", message=t(lang, "no_scenario"))

    # 4. Merge session context (e.g. account_id) into params as fallback.
    params = dict(intent_result.params)
    if "account_id" not in params and user_session.get("account_id"):
        params["account_id"] = user_session["account_id"]

    # 5. Validate required parameters are present.
    missing = [p for p in sc.required_params if p not in params]
    if missing:
        return ChatResponse(
            action="reply",
            message=t(lang, "missing_params", params=", ".join(missing)),
        )

    # 6. Store the pending confirmation in Redis.
    await confirm.create_pending(
        session_id=req.session_id,
        scenario=sc,
        params=params,
    )

    # 7. Ask the user to confirm in their language.
    templates: dict = sc.confirm_templates or {}
    template = templates.get(lang) or sc.confirm_template
    try:
        msg = template.format(**params)
        # Spoken variant: spell out account/bill numbers digit-by-digit.
        speech = template.format(**speechtext.speech_params(params))
    except (KeyError, IndexError):
        msg = f"{sc.display_name}?"
        speech = None

    speech = speech if speech and speech != msg else None
    return ChatResponse(action="confirm", message=msg, speech=speech)

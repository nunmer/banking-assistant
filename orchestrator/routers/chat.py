"""POST /chat — the main entry point. Text in, action out.

Flow per turn:
  1. Resolve a pending confirmation (spoken/typed yes/no).
  2. Continue an in-progress parameter collection (slot-filling).
  3. Otherwise classify a fresh request.

Both (2) and (3) converge on `_advance`, which validates required params and
either asks for the next missing one (one at a time) or asks the user to confirm.
"""
import logging

from fastapi import APIRouter

from orchestrator.config import settings
from orchestrator.i18n import slot_prompt, t
from orchestrator.models import ChatRequest, ChatResponse
from orchestrator.services import (
    affirm,
    confirm,
    llm,
    mib,
    scenario,
    session,
    slotfill,
    speechtext,
)

logger = logging.getLogger("orchestrator.chat")

router = APIRouter()


async def _advance(
    session_id: str, user_session: dict, intent: str, params: dict, lang: str
) -> ChatResponse:
    """Validate params for an intent, then collect the next slot or confirm.

    Shared by the fresh-classification path and the slot-filling continuation.
    """
    sc = await scenario.get(intent)
    if sc is None:
        await slotfill.clear(session_id)
        return ChatResponse(action="reply", message=t(lang, "no_scenario"))

    # Merge session context (e.g. account_id) as a fallback for missing params.
    params = dict(params)
    if "account_id" not in params and user_session.get("account_id"):
        params["account_id"] = user_session["account_id"]

    # Ask for the first still-missing required parameter, one at a time.
    missing = [p for p in sc.required_params if not params.get(p)]
    if missing:
        await slotfill.create(
            session_id, intent=intent, params=params, missing=missing, lang=lang
        )
        return ChatResponse(action="collect", message=slot_prompt(lang, missing[0]))

    # All required params present — set up the confirmation.
    await slotfill.clear(session_id)
    await confirm.create_pending(session_id=session_id, scenario=sc, params=params)

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


@router.post("/chat", response_model=ChatResponse)
async def chat(req: ChatRequest) -> ChatResponse:
    # Touch the session, optionally persisting the lang from this request.
    session_updates = {"lang": req.lang} if req.lang else None
    user_session = await session.touch(req.session_id, updates=session_updates)
    lang = user_session.get("lang", "ru-RU")

    # 1. If a confirmation is pending, a spoken/typed yes/no resolves it.
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

    # 2. If a parameter collection is in progress, treat this as the answer.
    sf = await slotfill.get(req.session_id)
    if sf is not None:
        # An explicit "no"/"cancel" abandons the collection.
        if affirm.classify_reply(req.text) == "no":
            await slotfill.clear(req.session_id)
            return ChatResponse(action="reply", message=t(lang, "cancelled"))

        asked = sf["missing"][0]
        value = await llm.extract_param(req.text, sf["intent"], asked, lang)
        if value:
            params = {**sf["params"], asked: value}
            return await _advance(req.session_id, user_session, sf["intent"], params, lang)

        # Couldn't read the asked slot as a bare answer. Reclassify to catch a
        # full restatement of this intent, or a switch to a different one.
        intent_result = await llm.classify(req.text, req.session_id)
        if (
            intent_result.intent not in ("unknown", "")
            and intent_result.confidence >= settings.MIN_CONFIDENCE
        ):
            if intent_result.intent == sf["intent"]:
                # Restatement: merge any newly given params and keep collecting.
                params = {**sf["params"], **intent_result.params}
                return await _advance(req.session_id, user_session, sf["intent"], params, lang)
            # Switch to a different intent.
            await slotfill.clear(req.session_id)
            return await _advance(
                req.session_id, user_session, intent_result.intent, dict(intent_result.params), lang
            )

        # Nothing usable — re-ask the same slot.
        return ChatResponse(action="collect", message=slot_prompt(lang, asked))

    # 3. Fresh request — classify intent via LLM.
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

    return await _advance(
        req.session_id, user_session, intent_result.intent, dict(intent_result.params), lang
    )

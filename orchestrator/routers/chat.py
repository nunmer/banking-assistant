"""POST /chat — the main entry point. Text in, action out.

Flow per turn:
  1. Resolve a pending confirmation (spoken/typed yes/no).
  2. Continue an in-progress parameter collection (slot-filling).
  3. Otherwise classify a fresh request.

Both (2) and (3) converge on `_advance`, which validates required params and
either asks for the next missing one (one at a time) or asks the user to confirm.

Every response carries `lang` — the language it is written in — so the bot can
pick the matching TTS voice even when the user has just switched languages.
"""
import logging

from fastapi import APIRouter

from orchestrator.config import settings
from orchestrator.i18n import slot_prompt, speech as i18n_speech, strip_for_speech, t
from orchestrator.models import ChatRequest, ChatResponse
from orchestrator.services import (
    affirm,
    confirm,
    enrich,
    history,
    llm,
    mib,
    notify,
    numwords,
    opsummary,
    scenario,
    session,
    slotfill,
    speechtext,
    validators,
)

logger = logging.getLogger("orchestrator.chat")

router = APIRouter()


def _speech_or_none(message: str, candidate: str) -> str | None:
    """Omit a TTS variant identical to the display message — nothing to add."""
    return candidate if candidate and candidate != message else None


async def _record_operation(
    req, pending: dict, result, result_message: str, lang: str
) -> dict:
    """Persist an executed operation and cross-notify Telegram for web ops.

    Returns the operation dict included in the ChatResponse so clients can
    render a persistent history card immediately.
    """
    summary = pending.get("summary") or pending.get("scenario_intent", "")
    channel = req.channel or "unknown"
    await history.record(
        session_id=req.session_id,
        intent=pending.get("scenario_intent", ""),
        summary=summary,
        lang=pending.get("lang") or lang,
        status=result.status,
        tx_id=result.tx_id,
        channel=channel,
    )
    if channel == "web":
        # Mirror the operation into the user's Telegram chat (no-op for
        # anonymous browser sessions).
        await notify.telegram_operation(req.session_id, summary, result_message)
    return {
        "summary": summary,
        "status": result.status,
        "tx_id": result.tx_id,
        "channel": channel,
    }


async def _detect_lang(session_id: str, current: str, detected: str | None) -> str:
    """Adopt the LLM-detected language for this reply and persist it if changed."""
    if detected and detected != current:
        await session.touch(session_id, updates={"lang": detected})
        return detected
    return current


async def _advance(
    session_id: str, user_session: dict, intent: str, params: dict, lang: str, text: str
) -> ChatResponse:
    """Validate params for an intent, then collect the next slot or confirm.

    Shared by the fresh-classification path and the slot-filling continuation.
    `text` is the raw user message, used to recover exact digit values (phone)
    that the LLM transcribes unreliably from dictated number-words.
    """
    sc = await scenario.get(intent)
    if sc is None:
        await slotfill.clear(session_id)
        msg = t(lang, "no_scenario")
        return ChatResponse(
            action="reply", message=msg,
            speech=_speech_or_none(msg, i18n_speech(lang, "no_scenario")), lang=lang,
        )

    # Merge session context (e.g. account_id) as a fallback for missing params.
    params = dict(params)
    if "account_id" not in params and user_session.get("account_id"):
        params["account_id"] = user_session["account_id"]

    # A dictated phone number arrives as number-words the LLM transcribes
    # unreliably; parse the exact digits deterministically from the raw text and
    # override the LLM's guess. Only when this scenario actually takes a phone,
    # and only when a valid number is found (otherwise keep any existing value).
    expects_phone = "phone" in (sc.required_params or []) or "phone" in (
        getattr(sc, "optional_params", None) or []
    )
    if text and expects_phone:
        phone = numwords.phone_from_text(text, lang)
        if phone:
            params["phone"] = phone

    # A required param counts as satisfied only if it is present AND well-formed.
    # Values that are present but malformed (a name where a phone belongs, letters
    # where an amount belongs) are dropped so they're re-collected — with a short
    # "that doesn't look right" note prepended to the prompt.
    bad = {
        p
        for p in sc.required_params
        if str(params.get(p) or "").strip() and not validators.is_valid(p, params.get(p))
    }
    for p in bad:
        params.pop(p, None)

    # Ask for the first still-missing required parameter, one at a time.
    missing = [p for p in sc.required_params if not params.get(p)]
    if missing:
        await slotfill.create(
            session_id, intent=intent, params=params, missing=missing, lang=lang
        )
        asked = missing[0]
        prompt = slot_prompt(lang, asked)
        if asked in bad:
            prompt = f"{t(lang, 'invalid_value')} {prompt}"
        return ChatResponse(action="collect", message=prompt, lang=lang)

    # Enrich with bank data (resolve accounts, products, cards, …) before
    # confirming. A failed resolution ends the turn with a friendly reply.
    params, err = await enrich.apply(intent, session_id, params, lang)
    if err is not None:
        await slotfill.clear(session_id)
        return ChatResponse(
            action="reply", message=err,
            speech=_speech_or_none(err, strip_for_speech(err)), lang=lang,
        )

    # All required params present — set up the confirmation.
    await slotfill.clear(session_id)

    templates: dict = sc.confirm_templates or {}
    template = templates.get(lang) or sc.confirm_template
    try:
        # Display: currency/enum values as natural words ("KZT" → "тенге").
        msg = template.format(**speechtext.for_display(params, lang))
        # Speech: same words, plus account/card numbers spelled out digit-by-digit.
        speech = template.format(**speechtext.for_speech(params, lang))
    except (KeyError, IndexError):
        msg = f"{sc.display_name}?"
        speech = None

    # History wants the essentials, not the confirmation question — store a
    # compact per-intent summary ("Перевод 5000 тенге → 8 (775) …").
    await confirm.create_pending(
        session_id=session_id, scenario=sc, params=params,
        summary=opsummary.short(intent, params, lang), lang=lang,
    )

    speech = speech if speech and speech != msg else None
    return ChatResponse(action="confirm", message=msg, speech=speech, lang=lang)


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
            key = "operation_error" if result.status == "error" else "operation_done"
            message = t(lang, key)
            operation = await _record_operation(req, pending, result, message, lang)
            return ChatResponse(
                action="reply", message=message,
                speech=_speech_or_none(message, i18n_speech(lang, key)),
                lang=lang, operation=operation,
            )
        if decision == "no":
            await confirm.clear_pending(req.session_id)
            msg = t(lang, "cancelled")
            return ChatResponse(
                action="reply", message=msg,
                speech=_speech_or_none(msg, i18n_speech(lang, "cancelled")), lang=lang,
            )
        # Not a yes/no — fall through and treat it as a brand-new request.

    # 2. If a parameter collection is in progress, treat this as the answer.
    sf = await slotfill.get(req.session_id)
    if sf is not None:
        # An explicit "no"/"cancel" abandons the collection.
        if affirm.classify_reply(req.text) == "no":
            await slotfill.clear(req.session_id)
            msg = t(lang, "cancelled")
            return ChatResponse(
                action="reply", message=msg,
                speech=_speech_or_none(msg, i18n_speech(lang, "cancelled")), lang=lang,
            )

        asked = sf["missing"][0]
        value = await llm.extract_param(req.text, sf["intent"], asked, lang)
        if value:
            params = {**sf["params"], asked: value}
            return await _advance(req.session_id, user_session, sf["intent"], params, lang, req.text)

        # Couldn't read the asked slot as a bare answer. Reclassify to catch a
        # full restatement of this intent, or a switch to a different one.
        intent_result = await llm.classify(req.text, req.session_id)
        if (
            intent_result.intent not in ("unknown", "")
            and intent_result.confidence >= settings.MIN_CONFIDENCE
        ):
            lang = await _detect_lang(req.session_id, lang, intent_result.lang)
            if intent_result.intent == sf["intent"]:
                # Restatement: merge any newly given params and keep collecting.
                params = {**sf["params"], **intent_result.params}
                return await _advance(req.session_id, user_session, sf["intent"], params, lang, req.text)
            # Switch to a different intent.
            await slotfill.clear(req.session_id)
            return await _advance(
                req.session_id, user_session, intent_result.intent,
                dict(intent_result.params), lang, req.text
            )

        # Nothing usable — re-ask the same slot.
        return ChatResponse(action="collect", message=slot_prompt(lang, asked), lang=lang)

    # 3. Fresh request — classify intent via LLM.
    intent_result = await llm.classify(req.text, req.session_id)
    # Reply in the language the user actually used (auto-detected), even if they
    # switched from a previous message, and remember it for next time.
    lang = await _detect_lang(req.session_id, lang, intent_result.lang)
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
        msg = t(lang, "unknown_intent")
        return ChatResponse(
            action="reply", message=msg,
            speech=_speech_or_none(msg, i18n_speech(lang, "unknown_intent")), lang=lang,
        )

    return await _advance(
        req.session_id, user_session, intent_result.intent,
        dict(intent_result.params), lang, req.text
    )

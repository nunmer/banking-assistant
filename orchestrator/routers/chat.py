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
import re
import uuid

from fastapi import APIRouter

from orchestrator.config import settings
from orchestrator.i18n import effective_lang, slot_prompt, speech as i18n_speech, strip_for_speech, t
from orchestrator.models import ChatRequest, ChatResponse
from orchestrator.services import (
    affirm,
    confirm,
    conversation,
    debug_events,
    enrich,
    history,
    llm,
    mib,
    notify,
    numwords,
    opsummary,
    scenario,
    session,
    session_identity,
    session_window,
    slotfill,
    speechtext,
    statement_pdf,
    validators,
)

logger = logging.getLogger("orchestrator.chat")

router = APIRouter()

# Small talk has no scenario/DB entry and no parameters to collect — it's
# handled as an immediate reply and never counts as a real intent switch.
# bot_info ("what can you do", "who are you") is grouped here too: asking it
# mid-slot-filling should just answer and keep collecting, not be treated as
# abandoning the operation in progress.
_SMALL_TALK = ("greeting", "farewell", "bot_info")


def _speech_or_none(message: str, candidate: str) -> str | None:
    """Omit a TTS variant identical to the display message — nothing to add."""
    return candidate if candidate and candidate != message else None


_REPEATED_PERIODS_RE = re.compile(r"\.\.+")


def _dedupe_periods(text: str) -> str:
    """Collapse "..' into '.' — a Russian period abbreviation ("3 мес.")

    landing right before a template's own closing period ("{period}.")
    otherwise renders as a visible double period.
    """
    return _REPEATED_PERIODS_RE.sub(".", text)


def _reply(lang: str, key: str, *, understood: bool = True, **kwargs: str) -> ChatResponse:
    """A terminal `t(lang, key)` reply, with its speech variant attached.

    Reports `effective_lang`, not the requested `lang` — if this language is
    missing this specific key and `t()` fell back to Russian text, the voice
    picked from `lang` must fall back right along with it, or a Kazakh voice
    ends up reading Russian words.
    """
    resolved = effective_lang(lang, key)
    msg = t(resolved, key, **kwargs)
    return ChatResponse(
        action="reply", message=msg,
        speech=_speech_or_none(msg, i18n_speech(resolved, key, **kwargs)), lang=resolved,
        understood=understood,
    )


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

    operation = {
        "summary": summary,
        "status": result.status,
        "tx_id": result.tx_id,
        "channel": channel,
    }
    if pending.get("scenario_intent") == "statement_pdf" and result.status != "error":
        # Best-effort: a client just gets no download affordance if this
        # fails, never a broken reply — see statement_pdf.generate_and_store.
        made_pdf = await statement_pdf.generate_and_store(
            tx_id=result.tx_id,
            session_id=req.session_id,
            params=pending.get("params") or {},
            lang=pending.get("lang") or lang,
        )
        if made_pdf:
            operation["document"] = "statement_pdf"
    return operation


async def _detect_lang(session_id: str, current: str, detected: str | None) -> str:
    """Adopt the LLM-detected language for this reply and persist it if changed."""
    if detected and detected != current:
        await session.touch(session_id, updates={"lang": detected})
        return detected
    return current


async def _advance(
    session_id: str, user_session: dict, intent: str, params: dict, lang: str, text: str,
    turn_id: str, history_session_id: str,
) -> ChatResponse:
    """Validate params for an intent, then collect the next slot or confirm.

    Shared by the fresh-classification path and the slot-filling continuation.
    `text` is the raw user message, used to recover exact digit values (phone)
    that the LLM transcribes unreliably from dictated number-words.
    `session_id` is the permanent identity (used for slotfill/confirm/account
    lookups); `history_session_id` is the windowed id used only for the debug
    trace (see services/session_window.py) — never the same value once a
    visit has gone idle long enough to start a new window.
    """
    sc = await scenario.get(intent)
    if sc is None:
        await slotfill.clear(session_id)
        return _reply(lang, "no_scenario")

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
    params_before = dict(params)
    params, err = await enrich.apply(intent, session_id, params, lang)
    await debug_events.log_event(
        history_session_id, turn_id, "enrich",
        {"intent": intent, "params_before": params_before, "params_after": params, "error": err},
    )
    if err is not None:
        await slotfill.clear(session_id)
        return ChatResponse(
            action="reply", message=err,
            speech=_speech_or_none(err, strip_for_speech(err)), lang=lang,
        )

    # All required params present — set up the confirmation.
    await slotfill.clear(session_id)

    templates: dict = sc.confirm_templates or {}
    template = templates.get(lang)
    # This scenario's per-language templates currently cover every language,
    # but if one is ever missing, the voice must fall back to Russian right
    # along with the text — not claim `lang` while reading Russian words.
    resolved_lang = lang if template else "ru-RU"
    template = template or sc.confirm_template
    display_params = speechtext.for_display(params, lang)
    speech_params = speechtext.for_speech(params, lang)
    try:
        # Display: currency/enum values as natural words ("KZT" → "тенге").
        msg = _dedupe_periods(template.format(**display_params))
        # Speech: same words, plus account/card numbers spelled out digit-by-digit.
        speech = _dedupe_periods(template.format(**speech_params))
    except (KeyError, IndexError):
        msg = f"{sc.display_name}?"
        speech = None

    # This is where a value that speechtext.py doesn't know how to localize
    # (no entry in its enum tables) silently passes through unchanged and
    # ends up embedded verbatim in the target-language sentence — logging the
    # template + both param views is what makes that class of bug visible in
    # the admin panel's trace, not just the params classify/enrich already show.
    await debug_events.log_event(
        history_session_id, turn_id, "confirm",
        {
            "intent": intent, "resolved_lang": resolved_lang, "template": template,
            "display_params": display_params, "speech_params": speech_params,
            "message": msg, "speech": speech,
        },
    )

    # History wants the essentials, not the confirmation question — store a
    # compact per-intent summary ("Перевод 5000 тенге → 8 (775) …").
    await confirm.create_pending(
        session_id=session_id, scenario=sc, params=params,
        summary=opsummary.short(intent, params, lang), lang=lang,
    )

    speech = speech if speech and speech != msg else None
    return ChatResponse(action="confirm", message=msg, speech=speech, lang=resolved_lang)


@router.post("/chat", response_model=ChatResponse)
async def chat(req: ChatRequest) -> ChatResponse:
    """Log both sides of the turn around `_chat`, whichever branch it takes.

    A single choke point for the admin panel's Conversations tab — every
    surface (web, Telegram) goes through this one route, so wrapping it here
    covers every reply shape (small talk, slot-filling, confirm, decline)
    without threading a log call through every return point in `_chat`.

    Also the single choke point for the debug trace (`turn_id` — falls back
    to a fresh one if the caller omitted it, so every turn always has one),
    for capturing Telegram identity (`username`/`user_name`) for the admin
    panel's session search, and for resolving the windowed conversation id
    (`history_session_id` — see services/session_window.py) used to GROUP
    the durable transcript into separate visits instead of one never-ending
    conversation tied to the permanent identity. `req.session_id` itself is
    untouched and still flows through to `_chat` for everything that must
    stay keyed by the real identity (account lookups, operation history,
    language preference, pending confirm/slot-fill).
    """
    turn_id = req.turn_id or str(uuid.uuid4())
    history_session_id = await session_window.resolve(req.session_id)
    if req.username or req.user_name:
        await session_identity.upsert(history_session_id, username=req.username, first_name=req.user_name)
    resp = await _chat(req, turn_id, history_session_id)
    channel = req.channel or "unknown"
    await conversation.log(history_session_id, channel, "user", req.text, resp.lang, turn_id=turn_id)
    await conversation.log(history_session_id, channel, "bot", resp.message, resp.lang, turn_id=turn_id)
    return resp


async def _chat(req: ChatRequest, turn_id: str, history_session_id: str) -> ChatResponse:
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
            await debug_events.log_event(
                history_session_id, turn_id, "mib_execute",
                {
                    "endpoint": pending["mib_endpoint"],
                    "params": pending["params"],
                    "method": pending.get("mib_method", "POST"),
                    "status": result.status,
                    "tx_id": result.tx_id,
                    "message": result.message,
                },
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
            return _reply(lang, "cancelled")
        # Not a yes/no — fall through and treat it as a brand-new request.

    # 2. If a parameter collection is in progress, treat this as the answer.
    sf = await slotfill.get(req.session_id)
    if sf is not None:
        # An explicit "no"/"cancel" abandons the collection.
        if affirm.classify_reply(req.text) == "no":
            await slotfill.clear(req.session_id)
            return _reply(lang, "cancelled")

        asked = sf["missing"][0]
        value = await llm.extract_param(req.text, sf["intent"], asked, lang)
        await debug_events.log_event(
            history_session_id, turn_id, "extract_param",
            {"intent": sf["intent"], "asked": asked, "text": req.text, "value": value},
        )
        if value:
            params = {**sf["params"], asked: value}
            return await _advance(
                req.session_id, user_session, sf["intent"], params, lang, req.text,
                turn_id, history_session_id,
            )

        # Couldn't read the asked slot as a bare answer. Reclassify to catch a
        # full restatement of this intent, or a switch to a different one.
        # Small talk ("thanks", "hi") isn't a real intent switch either — it
        # falls through to re-asking the same slot, same as "unknown".
        intent_result = await llm.classify(req.text, req.session_id)
        await debug_events.log_event(
            history_session_id, turn_id, "classify",
            {
                "text": req.text, "intent": intent_result.intent,
                "confidence": intent_result.confidence, "params": intent_result.params,
                "lang": intent_result.lang, "topic": intent_result.topic,
            },
        )
        if (
            intent_result.intent not in ("unknown", "", *_SMALL_TALK)
            and intent_result.confidence >= settings.MIN_CONFIDENCE
        ):
            lang = await _detect_lang(req.session_id, lang, intent_result.lang)
            if intent_result.intent == sf["intent"]:
                # Restatement: merge any newly given params and keep collecting.
                params = {**sf["params"], **intent_result.params}
                return await _advance(
                    req.session_id, user_session, sf["intent"], params, lang, req.text,
                    turn_id, history_session_id,
                )
            # Switch to a different intent.
            await slotfill.clear(req.session_id)
            return await _advance(
                req.session_id, user_session, intent_result.intent,
                dict(intent_result.params), lang, req.text, turn_id, history_session_id,
            )

        # Nothing usable — re-ask the same slot.
        return ChatResponse(action="collect", message=slot_prompt(lang, asked), lang=lang)

    # 3. Fresh request — classify intent via LLM.
    intent_result = await llm.classify(req.text, req.session_id)
    await debug_events.log_event(
        history_session_id, turn_id, "classify",
        {
            "text": req.text, "intent": intent_result.intent,
            "confidence": intent_result.confidence, "params": intent_result.params,
            "lang": intent_result.lang, "topic": intent_result.topic,
        },
    )
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

    if intent_result.intent in _SMALL_TALK:
        # Personalise the greeting when the channel knows the user's name
        # (Telegram bot/Mini App) — never guessed, just omitted otherwise.
        if intent_result.intent == "greeting" and req.user_name:
            return _reply(lang, "greeting_named", name=req.user_name)
        return _reply(lang, intent_result.intent)

    if (
        intent_result.intent in ("unknown", "")
        or intent_result.confidence < settings.MIN_CONFIDENCE
    ):
        # A confident "unknown" (the LLM is sure what it heard, just not a
        # banking task — "play music") was clearly addressed to the bot and
        # deserves an answer. Only a genuinely low-confidence read — the LLM
        # itself unsure what it even heard — gets treated as possible ambient
        # chatter and stays silent in hands-free mode (see ws_converse).
        understood = intent_result.confidence >= settings.MIN_CONFIDENCE
        # When the LLM could name what was actually asked about (a real
        # question it just has no data for — an exchange rate, the weather),
        # name it in the decline instead of dumping the full capability list.
        if understood and intent_result.topic:
            return _reply(lang, "unknown_intent_topic", topic=intent_result.topic)
        return _reply(lang, "unknown_intent", understood=understood)

    return await _advance(
        req.session_id, user_session, intent_result.intent,
        dict(intent_result.params), lang, req.text, turn_id, history_session_id,
    )

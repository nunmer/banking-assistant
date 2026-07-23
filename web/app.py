"""Web voice-bot gateway.

Serves the static voice UI and proxies browser calls to the orchestrator and
the speech service. The proxy keeps the speech API key server-side — the
browser never sees it — and enforces basic hygiene (payload size cap, per-IP
rate limit) since this endpoint is public.

Same functionality as the Telegram bot: STT → orchestrator /chat → TTS.
"""
import asyncio
import base64
import hashlib
import json
import logging
import os
import re
import time
from collections import defaultdict, deque

import httpx
import websockets
from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from web import telegram_auth

logger = logging.getLogger("web.gateway")

ORCHESTRATOR_URL = os.getenv("ORCHESTRATOR_URL", "http://orchestrator:8000")
SPEECH_SERVICE_URL = os.getenv("SPEECH_SERVICE_URL", "http://host.docker.internal:8000")
# Same host as SPEECH_SERVICE_URL, ws(s):// scheme — speechkit's live-STT
# WebSocket endpoint lives alongside its REST API.
SPEECH_STREAM_URL = os.getenv(
    "SPEECH_STREAM_URL",
    SPEECH_SERVICE_URL.replace("https://", "wss://").replace("http://", "ws://") + "/stt/stream",
)
SPEECH_API_KEY = os.getenv("SPEECH_API_KEY", "")
STT_LANGS = os.getenv("STT_LANGS", "ru-RU,kk-KZ")
TTS_VOICE_RU = os.getenv("TTS_VOICE_RU", "marina")
TTS_VOICE_KK = os.getenv("TTS_VOICE_KK", "amira")
TTS_VOICE_DEFAULT = os.getenv("TTS_VOICE_DEFAULT", "marina")
# Bot token — used only to verify Telegram Mini App initData signatures.
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN", "")

MAX_AUDIO_BYTES = 4 * 1024 * 1024  # ~4 MB ≈ well over a minute of voice
RATE_LIMIT_PER_MIN = int(os.getenv("WEB_RATE_LIMIT_PER_MIN", "60"))
# Yandex TTS rejects long texts; long replies (e.g. the capability list) are
# spoken only up to a sentence boundary — the user reads the rest on screen.
TTS_MAX_CHARS = 250

# Words that cut the bot off mid-reply in hands-free mode. Checked regardless
# of the session's own language — someone mid-Russian-reply may well say
# "stop" in English. Not exhaustive by design: the mic stays "live" (not
# muted) while the bot talks so these can be heard at all, but anything that
# ISN'T one of these is presumed to be the bot hearing its own voice bleed
# through the speakers (no proper echo cancellation here) and is discarded
# rather than treated as a real request — seeing "wait" work is worth a few
# false negatives on words we didn't list. Exact word match only, no
# stemming — a conjugated/declined form not listed verbatim won't match,
# same limitation the Russian words already had.
_INTERRUPT_KEYWORDS = [
    "стоп", "стой", "погоди", "подожди", "хватит", "остановись",
    "stop", "wait", "hold on",
    "тоқта", "күте тұр", "күт", "тоқтай тұр",
]
_INTERRUPT_RE = re.compile(
    r"\b(?:" + "|".join(re.escape(w) for w in _INTERRUPT_KEYWORDS) + r")\b",
    re.IGNORECASE | re.UNICODE,
)


def _is_interrupt(text: str) -> bool:
    return bool(_INTERRUPT_RE.search(text))


STATIC_DIR = os.path.join(os.path.dirname(__file__), "static")

app = FastAPI(title="Forte Voice Web")


@app.middleware("http")
async def _no_cache_static(request: Request, call_next):
    """Force revalidation on every load of index.html/app.js/app.css/etc.

    Without this, browsers apply heuristic caching to these files (no
    Cache-Control was set at all) and can keep serving a stale page after a
    deploy — this bit us once already (a null-ref crash from a cached page
    with an outdated DOM shape) and would otherwise keep happening on every
    UI change. "no-cache" still lets the browser cache the file and get a
    cheap 304 via the existing ETag/Last-Modified — it just can't skip
    asking first.
    """
    response = await call_next(request)
    if request.url.path == "/" or request.url.path.startswith("/static/"):
        response.headers["Cache-Control"] = "no-cache"
    return response


def _speech_headers() -> dict[str, str]:
    return {"X-API-Key": SPEECH_API_KEY} if SPEECH_API_KEY else {}


def _voice_for_lang(lang: str | None) -> str:
    code = (lang or "ru-RU")[:2].lower()
    return {"kk": TTS_VOICE_KK, "ru": TTS_VOICE_RU}.get(code, TTS_VOICE_DEFAULT)


# ── Per-IP sliding-window rate limit (in-memory; single-instance pilot) ──────
_hits: dict[str, deque] = defaultdict(deque)


def _rate_limit(request: Request) -> None:
    ip = request.client.host if request.client else "unknown"
    now = time.monotonic()
    window = _hits[ip]
    while window and now - window[0] > 60:
        window.popleft()
    if len(window) >= RATE_LIMIT_PER_MIN:
        raise HTTPException(status_code=429, detail="Too many requests")
    window.append(now)


async def _to_wav(audio: bytes) -> bytes:
    """Transcode a browser recording to 16 kHz mono PCM WAV via ffmpeg.

    Browsers record WebM/Opus (Chrome/Android) or MP4/AAC (Safari/iOS); the
    speech service's decoder (libsndfile) reads neither, so the gateway
    normalises everything to WAV — the shape it decodes reliably.
    """
    proc = await asyncio.create_subprocess_exec(
        "ffmpeg", "-hide_banner", "-loglevel", "error",
        "-i", "pipe:0", "-f", "wav", "-ar", "16000", "-ac", "1", "pipe:1",
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    out, err = await proc.communicate(audio)
    if proc.returncode != 0 or not out:
        logger.error("ffmpeg transcode failed: %s", err.decode(errors="replace")[:300])
        raise HTTPException(status_code=400, detail="Could not decode audio")
    return out


def _tts_text(text: str) -> str:
    """Trim overly long replies to the last sentence boundary within the cap."""
    if len(text) <= TTS_MAX_CHARS:
        return text
    cut = text[:TTS_MAX_CHARS]
    best = max(cut.rfind(sep) for sep in (". ", "! ", "? ", "\n"))
    return cut[: best + 1].strip() if best > 0 else cut.strip()


class ChatIn(BaseModel):
    session_id: str
    text: str
    user_name: str | None = None


class TTSIn(BaseModel):
    text: str
    lang: str | None = None


class TgAuthIn(BaseModel):
    init_data: str


@app.post("/api/tg-auth")
async def tg_auth(request: Request, body: TgAuthIn) -> dict:
    """Verify Telegram Mini App initData and return the authenticated session.

    The returned session_id is the Telegram user id — the same id the chat bot
    uses — so a conversation started in Telegram continues in the Mini App.
    """
    _rate_limit(request)
    fields = telegram_auth.verify_init_data(body.init_data, TELEGRAM_TOKEN)
    if fields is None:
        raise HTTPException(status_code=401, detail="Invalid Telegram init data")
    uid = telegram_auth.user_id_from(fields)
    if uid is None:
        raise HTTPException(status_code=401, detail="No user in init data")
    return {"session_id": uid, "user_name": telegram_auth.user_name_from(fields)}


@app.get("/health")
async def health() -> dict:
    return {"status": "ok"}


@app.post("/api/stt")
async def stt(request: Request, file: UploadFile = File(...)) -> dict:
    """Browser audio → speech-service /stt/recognize (multi-lang autodetect)."""
    _rate_limit(request)
    audio = await file.read()
    if not audio:
        raise HTTPException(status_code=400, detail="Empty audio")
    if len(audio) > MAX_AUDIO_BYTES:
        raise HTTPException(status_code=413, detail="Audio too large")
    wav = await _to_wav(audio)

    async with httpx.AsyncClient(timeout=120.0) as client:
        resp = await client.post(
            f"{SPEECH_SERVICE_URL}/stt/recognize",
            files={"file": ("audio.wav", wav, "audio/wav")},
            data={"lang": STT_LANGS},
            headers=_speech_headers(),
        )
    if resp.status_code != 200:
        logger.error("STT failed %s: %s", resp.status_code, resp.text[:300])
        raise HTTPException(status_code=502, detail="Speech recognition failed")
    return {"text": resp.json().get("text", "")}


@app.post("/api/chat")
async def chat(request: Request, body: ChatIn) -> dict:
    """Forward a user utterance to the orchestrator, verbatim contract."""
    _rate_limit(request)
    if not body.text.strip():
        raise HTTPException(status_code=400, detail="Empty text")
    payload = {"session_id": body.session_id, "text": body.text, "channel": "web"}
    if body.user_name:
        payload["user_name"] = body.user_name
    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.post(f"{ORCHESTRATOR_URL}/chat", json=payload)
    if resp.status_code != 200:
        logger.error("orchestrator failed %s: %s", resp.status_code, resp.text[:300])
        raise HTTPException(status_code=502, detail="Assistant is unavailable")
    return resp.json()


async def _run_turn(
    client: httpx.AsyncClient, session_id: str, user_text: str, user_name: str | None = None
) -> dict:
    """Chat → TTS for one already-transcribed utterance.

    Shared by the batch `/api/converse` endpoint and the live `/ws/converse`
    streaming route — both need the exact same reply shape once they have
    text, they just get that text via different paths (one STT call vs.
    live partial/final events).
    """
    payload = {"session_id": session_id, "text": user_text, "channel": "web"}
    if user_name:
        payload["user_name"] = user_name
    chat_resp = await client.post(f"{ORCHESTRATOR_URL}/chat", json=payload)
    if chat_resp.status_code != 200:
        logger.error("orchestrator failed %s: %s", chat_resp.status_code, chat_resp.text[:300])
        raise HTTPException(status_code=502, detail="Assistant is unavailable")
    data = chat_resp.json()

    # Synthesize the spoken reply; on failure the client falls back to text.
    audio_b64 = None
    speak_text = _tts_text(data.get("speech") or data.get("message") or "")
    if speak_text:
        tts_resp = await client.post(
            f"{SPEECH_SERVICE_URL}/tts/synthesize",
            json={
                "text": speak_text,
                "lang": data.get("lang") or "ru-RU",
                "voice": _voice_for_lang(data.get("lang")),
                "format": "MP3",
            },
            headers=_speech_headers(),
        )
        if tts_resp.status_code == 200:
            audio_b64 = base64.b64encode(tts_resp.content).decode()
        else:
            logger.error("TTS failed %s: %s", tts_resp.status_code, tts_resp.text[:300])

    return {
        "message": data.get("message"),
        "action": data.get("action"),
        "lang": data.get("lang"),
        # Completed-operation record — the client renders its history card
        # from this; dropping it would wipe the confirmation without a trace.
        "operation": data.get("operation"),
        "audio": audio_b64,
        # False only for the "I didn't understand" reply — lets a hands-free
        # caller (ws_converse) decide to stay silent on ambient chatter rather
        # than interrupting the user with it. /api/converse ignores this;
        # a deliberate single recording deserves an answer either way.
        "understood": data.get("understood", True),
    }


@app.post("/api/converse")
async def converse(
    request: Request,
    session_id: str = Form(...),
    text: str | None = Form(None),
    file: UploadFile | None = File(None),
    user_name: str | None = Form(None),
) -> dict:
    """One-round-trip voice turn: STT → chat → TTS, all server-side.

    The three-request flow (stt, chat, tts) made the browser pay internet
    latency between every stage — ~3s slower than Telegram, whose bot runs the
    same chain over localhost. This endpoint mirrors the bot: audio (or a text
    from a voice-mode button) goes up once; the reply text and its MP3 come
    back together. The MP3 is base64 in the JSON — replies are a few seconds
    of speech, so the payload stays small.

    Superseded for live mic input by `/ws/converse` (streaming partial
    captions); this endpoint remains for text-mode turns and as a fallback
    where WebSocket/AudioWorklet capture isn't available.
    """
    _rate_limit(request)

    async with httpx.AsyncClient(timeout=120.0) as client:
        transcript = None
        if file is not None:
            audio = await file.read()
            if not audio:
                raise HTTPException(status_code=400, detail="Empty audio")
            if len(audio) > MAX_AUDIO_BYTES:
                raise HTTPException(status_code=413, detail="Audio too large")
            wav = await _to_wav(audio)
            stt_resp = await client.post(
                f"{SPEECH_SERVICE_URL}/stt/recognize",
                files={"file": ("audio.wav", wav, "audio/wav")},
                data={"lang": STT_LANGS},
                headers=_speech_headers(),
            )
            if stt_resp.status_code != 200:
                logger.error("STT failed %s: %s", stt_resp.status_code, stt_resp.text[:300])
                raise HTTPException(status_code=502, detail="Speech recognition failed")
            transcript = stt_resp.json().get("text", "").strip()
            if not transcript:
                return {"transcript": "", "message": None, "action": None,
                        "lang": None, "audio": None}

        user_text = transcript if transcript else (text or "").strip()
        if not user_text:
            raise HTTPException(status_code=400, detail="No audio or text given")

        result = await _run_turn(client, session_id, user_text, user_name)

    return {"transcript": transcript, **result}


@app.websocket("/ws/converse")
async def ws_converse(websocket: WebSocket) -> None:
    """Hands-free voice conversation over one continuous connection.

    The mic keeps streaming for the whole session — Yandex's own
    end-of-utterance detector (configured in speechkit's stt_stream engine)
    decides when the user finished a turn, so the browser never needs a
    manual "stop recording" tap after the first one. Each detected utterance
    runs through chat+TTS immediately and the session stays open for the
    next turn, until the browser explicitly ends it or disconnects.

    Protocol with the browser:
      1. Connect, then send {"session_id": ..., "lang": "ru-RU,kk-KZ",
         "user_name": ...}. `user_name` is only present inside Telegram
         (Mini App) and personalises a greeting reply; omitted for an
         anonymous browser session.
      2. Send binary PCM16LE mono @ 16kHz frames continuously — including
         while the reply audio is playing. The mic is deliberately NOT muted
         during playback, so that a spoken "stop"/"wait" can interrupt (see
         below); there's no real echo cancellation here, so anything heard
         while the bot is talking that ISN'T one of those interrupt words is
         discarded rather than treated as a request.
      3. Send {"action": "bot_speaking", "value": true|false} whenever local
         playback starts/stops, so the server knows how to treat what it
         hears meanwhile.
      4. Send {"action": "end"} to leave hands-free mode.
      5. Server sends {"type": "partial", "text": ...} live per turn, one
         {"type": "reply", message, audio, action, operation} per completed
         utterance the user was actually addressing to the bot (an
         "understood: false" turn — ambient chatter, not a real request — is
         silently dropped, not sent), or {"type": "interrupt"} the moment a
         stop/wait word is heard mid-reply. Keeps going for however many
         turns happen before "end".
    """
    await websocket.accept()
    try:
        first = await websocket.receive_json()
    except WebSocketDisconnect:
        return
    session_id = first.get("session_id") or ""
    lang = first.get("lang") or STT_LANGS
    user_name = first.get("user_name") or None
    bot_speaking = False

    async def browser_to_upstream(upstream) -> None:
        nonlocal bot_speaking
        while True:
            message = await websocket.receive()
            if message["type"] == "websocket.disconnect":
                break
            data = message.get("bytes")
            if data is not None:
                await upstream.send(data)
                continue
            text = message.get("text")
            if text is not None:
                try:
                    control = json.loads(text)
                except json.JSONDecodeError:
                    continue
                action = control.get("action")
                if action == "end":
                    break
                if action == "bot_speaking":
                    bot_speaking = bool(control.get("value"))
        await upstream.send(json.dumps({"action": "end"}))

    async def upstream_to_browser(upstream, client: httpx.AsyncClient) -> None:
        async for raw in upstream:
            event = json.loads(raw)
            kind = event.get("type")
            if kind == "partial":
                try:
                    await websocket.send_json(event)
                except (WebSocketDisconnect, RuntimeError):
                    return
            elif kind == "final":
                text = (event.get("text") or "").strip()
                if not text:
                    continue
                if bot_speaking:
                    # No real echo cancellation — only react to an explicit
                    # interrupt word; anything else heard mid-reply is
                    # presumed to be the bot hearing its own voice.
                    if _is_interrupt(text):
                        try:
                            await websocket.send_json({"type": "interrupt"})
                        except (WebSocketDisconnect, RuntimeError):
                            return
                    continue
                # Runs one full chat+TTS round trip per detected utterance;
                # the upstream keeps queuing any audio that arrives meanwhile.
                result = await _run_turn(client, session_id, text, user_name)
                if not result.get("understood", True):
                    # Ambient chatter, not addressed to the bot — the honest
                    # answer to "was this meant for me" is stay silent, not
                    # interrupt with "I didn't understand".
                    continue
                try:
                    await websocket.send_json({"type": "reply", **result})
                except (WebSocketDisconnect, RuntimeError):
                    return
            elif kind in ("done", "error"):
                return

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            async with websockets.connect(
                SPEECH_STREAM_URL, additional_headers=_speech_headers()
            ) as upstream:
                await upstream.send(json.dumps({"lang": lang}))
                await asyncio.gather(
                    browser_to_upstream(upstream), upstream_to_browser(upstream, client)
                )
    except WebSocketDisconnect:
        pass
    except Exception as e:
        logger.error("ws_converse failed: %s", e)
        try:
            await websocket.send_json(
                {"type": "error", "detail": "Assistant is unavailable"}
            )
        except Exception:
            pass


@app.post("/api/tts")
async def tts(request: Request, body: TTSIn) -> Response:
    """Synthesize a reply as MP3 (plays natively in every browser, incl. iOS)."""
    _rate_limit(request)
    if not body.text.strip():
        raise HTTPException(status_code=400, detail="Empty text")
    async with httpx.AsyncClient(timeout=60.0) as client:
        resp = await client.post(
            f"{SPEECH_SERVICE_URL}/tts/synthesize",
            json={
                "text": _tts_text(body.text),
                "lang": body.lang or "ru-RU",
                "voice": _voice_for_lang(body.lang),
                "format": "MP3",
            },
            headers=_speech_headers(),
        )
    if resp.status_code != 200:
        logger.error("TTS failed %s: %s", resp.status_code, resp.text[:300])
        raise HTTPException(status_code=502, detail="Speech synthesis failed")
    return Response(content=resp.content, media_type="audio/mpeg")


@app.get("/api/history")
async def api_history(request: Request, session_id: str, limit: int = 20) -> dict:
    """Recent executed operations for this session (shared with Telegram)."""
    _rate_limit(request)
    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.get(
            f"{ORCHESTRATOR_URL}/history/{session_id}", params={"limit": limit}
        )
    if resp.status_code != 200:
        logger.error("history failed %s: %s", resp.status_code, resp.text[:300])
        raise HTTPException(status_code=502, detail="History is unavailable")
    return resp.json()


def _asset_version(filename: str) -> str:
    """Content hash for a static asset — used to cache-bust its URL.

    A Cache-Control header alone isn't enough: it only takes effect on
    requests a client actually revalidates, and some environments (Telegram's
    Mini App WebView in particular) are known to cache far more aggressively
    than that. A URL a client has genuinely never seen before can't be served
    from any prior cache, browser or otherwise — so index.html's asset links
    get a query string derived from the file's own content, changing
    automatically whenever the file does.
    """
    with open(os.path.join(STATIC_DIR, filename), "rb") as f:
        return hashlib.md5(f.read()).hexdigest()[:10]


@app.get("/")
async def index() -> HTMLResponse:
    with open(os.path.join(STATIC_DIR, "index.html"), "r", encoding="utf-8") as f:
        html = f.read()
    for asset in ("app.css", "app.js", "sphere.js"):
        html = html.replace(
            f"/static/{asset}", f"/static/{asset}?v={_asset_version(asset)}"
        )
    return HTMLResponse(html)


app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

"""Web voice-bot gateway.

Serves the static voice UI and proxies browser calls to the orchestrator and
the speech service. The proxy keeps the speech API key server-side — the
browser never sees it — and enforces basic hygiene (payload size cap, per-IP
rate limit) since this endpoint is public.

Same functionality as the Telegram bot: STT → orchestrator /chat → TTS.
"""
import asyncio
import base64
import logging
import os
import time
from collections import defaultdict, deque

import httpx
from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from web import telegram_auth

logger = logging.getLogger("web.gateway")

ORCHESTRATOR_URL = os.getenv("ORCHESTRATOR_URL", "http://orchestrator:8000")
SPEECH_SERVICE_URL = os.getenv("SPEECH_SERVICE_URL", "http://host.docker.internal:8000")
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

STATIC_DIR = os.path.join(os.path.dirname(__file__), "static")

app = FastAPI(title="Forte Voice Web")


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
    return {"session_id": uid}


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
    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.post(
            f"{ORCHESTRATOR_URL}/chat",
            json={"session_id": body.session_id, "text": body.text, "channel": "web"},
        )
    if resp.status_code != 200:
        logger.error("orchestrator failed %s: %s", resp.status_code, resp.text[:300])
        raise HTTPException(status_code=502, detail="Assistant is unavailable")
    return resp.json()


@app.post("/api/converse")
async def converse(
    request: Request,
    session_id: str = Form(...),
    text: str | None = Form(None),
    file: UploadFile | None = File(None),
) -> dict:
    """One-round-trip voice turn: STT → chat → TTS, all server-side.

    The three-request flow (stt, chat, tts) made the browser pay internet
    latency between every stage — ~3s slower than Telegram, whose bot runs the
    same chain over localhost. This endpoint mirrors the bot: audio (or a text
    from a voice-mode button) goes up once; the reply text and its MP3 come
    back together. The MP3 is base64 in the JSON — replies are a few seconds
    of speech, so the payload stays small.
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

        chat_resp = await client.post(
            f"{ORCHESTRATOR_URL}/chat",
            json={"session_id": session_id, "text": user_text, "channel": "web"},
        )
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
        "transcript": transcript,
        "message": data.get("message"),
        "action": data.get("action"),
        "lang": data.get("lang"),
        # Completed-operation record — the client renders its history card
        # from this; dropping it would wipe the confirmation without a trace.
        "operation": data.get("operation"),
        "audio": audio_b64,
    }


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


@app.get("/")
async def index() -> FileResponse:
    return FileResponse(os.path.join(STATIC_DIR, "index.html"))


app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

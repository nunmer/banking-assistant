# IMPLEMENTATION.md

Technical reference for building Forte Assistant. Covers every component, data contracts, and implementation decisions.

---

## Table of contents

1. [Architecture overview](#1-architecture-overview)
2. [Telegram bot](#2-telegram-bot)
3. [Orchestrator](#3-orchestrator)
4. [LLM service](#4-llm-service)
5. [Scenario DB](#5-scenario-db)
6. [Confirmation flow](#6-confirmation-flow)
7. [Speech API](#7-speech-api)
8. [Mock MIB API](#8-mock-mib-api)
9. [Session management](#9-session-management)
10. [Data contracts](#10-data-contracts)
11. [Docker Compose](#11-docker-compose)
12. [Open problems](#12-open-problems)

---

## 1. Architecture overview

```
Telegram
   │  HTTPS Webhook
   ▼
Bot Service (aiogram)
   │  voice → POST /stt
   │  text  → POST /chat
   ▼
Orchestrator (FastAPI)
   ├── LLM Service          → OpenAI-compatible /chat/completions
   ├── Scenario Service     → PostgreSQL
   ├── Confirmation Service → Redis (pending confirmations)
   └── MIB Client           → Mock MIB API (→ real later)
```

All services communicate over internal HTTP. Redis holds session state and pending confirmation tasks. PostgreSQL holds scenarios.

---

## 2. Telegram bot

**Library:** aiogram 3 with asyncio.

### Handlers

```
bot/handlers/text.py   — handles Message where content_type == TEXT
bot/handlers/voice.py  — handles Message where content_type == VOICE
```

### Text handler

```python
# bot/handlers/text.py
from aiogram import Router
from aiogram.types import Message
import httpx

router = Router()

@router.message()
async def handle_text(message: Message):
    session_id = str(message.from_user.id)

    async with httpx.AsyncClient() as client:
        resp = await client.post(
            "http://orchestrator:8000/chat",
            json={
                "session_id": session_id,
                "text": message.text,
            },
        )

    data = resp.json()

    if data["action"] == "confirm":
        await message.answer(
            data["message"],
            reply_markup=confirm_keyboard(),  # [Yes] [No] inline buttons
        )
    else:
        await message.answer(data["message"])
```

### Voice handler

```python
# bot/handlers/voice.py
@router.message(F.voice)
async def handle_voice(message: Message, bot: Bot):
    session_id = str(message.from_user.id)

    # Download ogg from Telegram
    file = await bot.get_file(message.voice.file_id)
    buf = await bot.download_file(file.file_path)

    async with httpx.AsyncClient() as client:
        # Transcribe
        stt_resp = await client.post(
            "http://speech-api:8002/stt",
            content=buf.read(),
            headers={"Content-Type": "audio/ogg", "X-Lang": "ru-RU"},
        )
        transcript = stt_resp.json()["text"]

        # Then same as text handler
        resp = await client.post(
            "http://orchestrator:8000/chat",
            json={"session_id": session_id, "text": transcript},
        )

    data = resp.json()
    await message.answer(data["message"], reply_markup=confirm_keyboard() if data["action"] == "confirm" else None)
```

### Confirmation keyboard

```python
# bot/keyboards.py
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

def confirm_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="✅ Yes", callback_data="confirm:yes"),
        InlineKeyboardButton(text="❌ No",  callback_data="confirm:no"),
    ]])
```

### Callback handler (Yes / No)

```python
@router.callback_query(F.data.startswith("confirm:"))
async def handle_confirm_callback(callback: CallbackQuery):
    approved = callback.data.split(":")[1] == "yes"
    session_id = str(callback.from_user.id)

    async with httpx.AsyncClient() as client:
        resp = await client.post(
            "http://orchestrator:8000/confirm/reply",
            json={"session_id": session_id, "approved": approved},
        )

    data = resp.json()
    await callback.message.edit_text(data["message"])
    await callback.answer()
```

---

## 3. Orchestrator

**Framework:** FastAPI + asyncio.

### Endpoints

| Method | Path | Description |
|---|---|---|
| POST | `/chat` | Main entry — text in, action out |
| POST | `/confirm/reply` | User confirmed or rejected |

### POST /chat

```python
# orchestrator/routers/chat.py
from fastapi import APIRouter
from orchestrator.models import ChatRequest, ChatResponse
from orchestrator.services import llm, scenario, confirm

router = APIRouter()

@router.post("/chat", response_model=ChatResponse)
async def chat(req: ChatRequest):
    # 1. Classify intent via LLM
    intent_result = await llm.classify(req.text, req.session_id)

    # 2. Check scenario DB
    sc = await scenario.get(intent_result.intent)

    if sc is None:
        return ChatResponse(action="reply", message="Sorry, I can't help with that.")

    # 3. Validate required params are present
    missing = [p for p in sc.required_params if p not in intent_result.params]
    if missing:
        return ChatResponse(
            action="reply",
            message=f"Please provide: {', '.join(missing)}",
        )

    # 4. Store pending confirmation in Redis
    await confirm.create_pending(
        session_id=req.session_id,
        scenario=sc,
        params=intent_result.params,
    )

    # 5. Return confirmation message to bot
    msg = sc.confirm_template.format(**intent_result.params)
    return ChatResponse(action="confirm", message=msg)
```

### POST /confirm/reply

```python
# orchestrator/routers/confirm.py
@router.post("/confirm/reply", response_model=ChatResponse)
async def confirm_reply(req: ConfirmReplyRequest):
    pending = await confirm.get_pending(req.session_id)

    if pending is None:
        return ChatResponse(action="reply", message="No pending action found.")

    await confirm.clear_pending(req.session_id)

    if not req.approved:
        return ChatResponse(action="reply", message="Cancelled.")

    # Call MIB API
    result = await mib.execute(
        endpoint=pending.scenario.mib_endpoint,
        params=pending.params,
    )

    return ChatResponse(action="reply", message=result.message)
```

---

## 4. LLM service

**Client:** OpenAI-compatible (`openai` Python SDK, `base_url` configurable).

### System prompt

```python
SYSTEM_PROMPT = """
You are a banking assistant. Extract the user's intent and parameters from their message.

Respond ONLY with valid JSON. No explanation. No markdown.

Schema:
{
  "intent": "<intent_name>",
  "params": {
    "<param_name>": "<value>"
  },
  "confidence": 0.0–1.0
}

Available intents: transfer, balance, payment, statement, unknown

Examples:
User: "Transfer 500 dollars to account KZ123"
Response: {"intent": "transfer", "params": {"amount": "500", "currency": "USD", "to_account": "KZ123"}, "confidence": 0.97}

User: "What is my balance"
Response: {"intent": "balance", "params": {}, "confidence": 0.99}

User: "Play music"
Response: {"intent": "unknown", "params": {}, "confidence": 0.95}
"""
```

### classify()

```python
# orchestrator/services/llm.py
import json
from openai import AsyncOpenAI
from orchestrator.models import IntentResult

client = AsyncOpenAI(
    base_url=settings.OPENAI_API_BASE,
    api_key=settings.OPENAI_API_KEY,
)

async def classify(text: str, session_id: str) -> IntentResult:
    response = await client.chat.completions.create(
        model=settings.OPENAI_MODEL,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user",   "content": text},
        ],
        temperature=0,
        response_format={"type": "json_object"},
    )

    raw = response.choices[0].message.content
    data = json.loads(raw)

    return IntentResult(
        intent=data["intent"],
        params=data.get("params", {}),
        confidence=data.get("confidence", 1.0),
    )
```

**Note:** `response_format={"type": "json_object"}` guarantees valid JSON output on gpt-4o and compatible models. For other models, add a JSON extraction fallback with regex.

---

## 5. Scenario DB

### Schema

```sql
-- db/migrations/001_scenarios.sql

CREATE TABLE scenarios (
    id              SERIAL PRIMARY KEY,
    intent          VARCHAR(64) UNIQUE NOT NULL,
    display_name    VARCHAR(128) NOT NULL,
    description     TEXT,
    required_params JSONB NOT NULL DEFAULT '[]',   -- ["amount", "currency", "to_account"]
    optional_params JSONB NOT NULL DEFAULT '[]',
    confirm_template TEXT NOT NULL,                -- "Transfer {amount} {currency} to {to_account} — confirm?"
    mib_endpoint    VARCHAR(256) NOT NULL,          -- "/transfer"
    mib_method      VARCHAR(8) NOT NULL DEFAULT 'POST',
    active          BOOLEAN NOT NULL DEFAULT TRUE,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
```

### Seed data

```sql
-- db/seed.sql

INSERT INTO scenarios (intent, display_name, required_params, confirm_template, mib_endpoint) VALUES
(
    'transfer',
    'Money Transfer',
    '["amount", "currency", "to_account"]',
    'Transfer {amount} {currency} to account {to_account} — confirm?',
    '/transfer'
),
(
    'balance',
    'Account Balance',
    '[]',
    'Retrieve your account balance — confirm?',
    '/balance'
),
(
    'payment',
    'Bill Payment',
    '["bill_id", "amount"]',
    'Pay bill {bill_id} for {amount} — confirm?',
    '/payment'
),
(
    'statement',
    'Transaction Statement',
    '[]',
    'Show your last transactions — confirm?',
    '/statement'
);
```

### Query

```python
# orchestrator/services/scenario.py
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from orchestrator.db.models import Scenario

async def get(intent: str) -> Scenario | None:
    async with AsyncSession(engine) as session:
        result = await session.execute(
            select(Scenario).where(
                Scenario.intent == intent,
                Scenario.active == True,
            )
        )
        return result.scalar_one_or_none()
```

---

## 6. Confirmation flow

Pending confirmations live in Redis with a TTL. Key: `confirm:{session_id}`.

### create_pending()

```python
# orchestrator/services/confirm.py
import json
import redis.asyncio as aioredis

redis = aioredis.from_url(settings.REDIS_URL)
TTL = 120  # seconds — user has 2 min to confirm

async def create_pending(session_id: str, scenario, params: dict):
    payload = json.dumps({
        "scenario_intent": scenario.intent,
        "mib_endpoint": scenario.mib_endpoint,
        "mib_method": scenario.mib_method,
        "params": params,
    })
    await redis.setex(f"confirm:{session_id}", TTL, payload)

async def get_pending(session_id: str) -> dict | None:
    raw = await redis.get(f"confirm:{session_id}")
    if raw is None:
        return None
    return json.loads(raw)

async def clear_pending(session_id: str):
    await redis.delete(f"confirm:{session_id}")
```

**TTL behaviour:** if user doesn't respond within 2 minutes, the pending key expires. Next `/confirm/reply` returns "No pending action found."

---

## 7. Speech API

Thin FastAPI service. Two endpoints: `POST /stt`, `POST /tts`.

### Vendor routing

```python
# speech-api/main.py
from fastapi import FastAPI, Request, Header
import os

app = FastAPI()
PROVIDER = os.getenv("SPEECH_PROVIDER", "speechkit")  # speechkit | whisper

@app.post("/stt")
async def stt(request: Request, x_lang: str = Header(default="ru-RU")):
    audio_bytes = await request.body()

    if PROVIDER == "speechkit":
        from providers.speechkit import transcribe
    else:
        from providers.whisper import transcribe

    text = await transcribe(audio_bytes, lang=x_lang)
    return {"text": text}
```

### SpeechKit provider

```python
# speech-api/providers/speechkit.py
import aiohttp, os

API_KEY = os.getenv("SPEECHKIT_API_KEY")

async def transcribe(audio: bytes, lang: str) -> str:
    url = "https://stt.api.cloud.yandex.net/speech/v1/stt:recognize"
    params = {"lang": lang, "format": "oggopus"}

    async with aiohttp.ClientSession() as session:
        async with session.post(
            url,
            data=audio,
            params=params,
            headers={"Authorization": f"Api-Key {API_KEY}"},
        ) as resp:
            data = await resp.json()
            return data["result"]
```

### Whisper provider

```python
# speech-api/providers/whisper.py
from faster_whisper import WhisperModel
import io, soundfile as sf

model = WhisperModel("large-v3", device="cpu", compute_type="int8")

async def transcribe(audio: bytes, lang: str) -> str:
    # faster-whisper is sync — run in threadpool in prod
    segments, _ = model.transcribe(io.BytesIO(audio), language=lang[:2])
    return " ".join(s.text for s in segments)
```

---

## 8. Mock MIB API

FastAPI service. Returns HTTP 200 with a fake transaction ID for any request.

```python
# mock-mib/main.py
from fastapi import FastAPI, Request
from pydantic import BaseModel
from uuid import uuid4
from datetime import datetime, timezone

app = FastAPI(title="Mock MIB API")

class MIBResponse(BaseModel):
    status: str
    tx_id: str
    timestamp: str
    message: str

@app.api_route("/{path:path}", methods=["GET", "POST", "PUT"])
async def catch_all(path: str, request: Request) -> MIBResponse:
    body = await request.json() if request.method in ("POST", "PUT") else {}
    tx_id = f"MOCK-{uuid4().hex[:8].upper()}"

    return MIBResponse(
        status="success",
        tx_id=tx_id,
        timestamp=datetime.now(timezone.utc).isoformat(),
        message=f"Operation /{path} completed. Ref: {tx_id}",
    )
```

**Swap for real MIB:** change `MIB_API_BASE` in `.env` to the real endpoint. The `mib.py` client in orchestrator doesn't change.

### MIB client

```python
# orchestrator/services/mib.py
import httpx
from orchestrator.models import MIBResult

async def execute(endpoint: str, params: dict) -> MIBResult:
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            f"{settings.MIB_API_BASE}{endpoint}",
            json=params,
            headers={"Authorization": f"Bearer {settings.MIB_API_TOKEN}"},
            timeout=10.0,
        )
        resp.raise_for_status()
        data = resp.json()

    return MIBResult(
        status=data["status"],
        tx_id=data["tx_id"],
        message=data["message"],
    )
```

---

## 9. Session management

Redis key conventions:

| Key | Value | TTL |
|---|---|---|
| `session:{user_id}` | JSON user session (account_id, lang, etc.) | 24h |
| `confirm:{user_id}` | JSON pending confirmation payload | 120s |

Session is created on first message. Stores `account_id` after user is identified (future: auth step).

---

## 10. Data contracts

### Pydantic models

```python
# orchestrator/models.py
from pydantic import BaseModel

class ChatRequest(BaseModel):
    session_id: str
    text: str

class ChatResponse(BaseModel):
    action: str      # "confirm" | "reply"
    message: str

class IntentResult(BaseModel):
    intent: str
    params: dict[str, str]
    confidence: float

class ConfirmReplyRequest(BaseModel):
    session_id: str
    approved: bool

class MIBResult(BaseModel):
    status: str
    tx_id: str
    message: str
```

---

## 11. Docker Compose

```yaml
# docker-compose.yml
services:

  bot:
    build: ./bot
    env_file: .env
    depends_on: [orchestrator]
    restart: unless-stopped

  orchestrator:
    build: ./orchestrator
    ports: ["8000:8000"]
    env_file: .env
    depends_on: [postgres, redis]
    restart: unless-stopped

  speech-api:
    build: ./speech-api
    ports: ["8002:8002"]
    env_file: .env
    restart: unless-stopped

  mock-mib:
    build: ./mock-mib
    ports: ["8001:8001"]
    restart: unless-stopped

  postgres:
    image: postgres:16
    environment:
      POSTGRES_DB: forte
      POSTGRES_USER: forte
      POSTGRES_PASSWORD: forte
    volumes:
      - ./db/seed.sql:/docker-entrypoint-initdb.d/seed.sql
      - pgdata:/var/lib/postgresql/data

  redis:
    image: redis:7
    volumes:
      - redisdata:/data

volumes:
  pgdata:
  redisdata:
```

---

## 12. Open problems

| Problem | Notes |
|---|---|
| User identity / auth | Currently session = Telegram user ID. No real bank auth. Needs OTP or token handshake before any MIB call. |
| Multi-turn context | LLM gets single-turn input only. If user says "transfer to the same account as last time" it breaks. Need conversation history in Redis. |
| Kazakh language STT | SpeechKit supports `kk-KZ` for STT. TTS in Kazakh not available — Russian fallback only. |
| Param extraction gaps | If user says "send money to Asel" with no account number, LLM extracts `to_account: "Asel"`. Need a follow-up question loop. |
| MIB error mapping | Mock always returns 200. Real API will return domain errors (insufficient funds, invalid account). Need error → user message mapping. |
| Confirmation timeout UX | After 2 min TTL expires, user gets "No pending action". Should proactively message user that the request expired. |
| TTS voice replies | TTS endpoint in speech-api is scaffolded but not wired to bot. Bot always replies with text for now. |

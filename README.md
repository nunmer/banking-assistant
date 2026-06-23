# Forte Assistant

> Voice and text banking assistant. Users send a message or voice note to a Telegram bot, the system classifies the intent, confirms with the user, and executes the operation against the banking API.

**Internal project — ForteBank AI Department.**

---

## What it does

1. User sends a voice note or text to a Telegram bot
2. Voice is transcribed via Speech API (SpeechKit / Whisper)
3. LLM classifies intent and extracts parameters
4. System matches intent against a Scenario DB
5. User is asked to confirm: *"Transfer 10 USD to account X — confirm?"*
6. On approval, the orchestrator calls MIB API
7. Result is sent back as text or voice

---

## Stack

| Layer | Technology |
|---|---|
| Bot | Python, aiogram 3 |
| Orchestrator | Python, FastAPI |
| LLM | OpenAI-compatible API (any model) |
| Speech STT/TTS | Yandex SpeechKit / faster-whisper |
| Scenario DB | PostgreSQL |
| Session store | Redis |
| MIB API | Mock (HTTP 200) → real integration later |
| Infra | Docker Compose (dev), Kubernetes (prod) |

---

## Repo structure

```
forte-assistant/
├── bot/                    # Telegram bot (aiogram)
│   ├── main.py
│   ├── handlers/
│   │   ├── text.py
│   │   └── voice.py
│   └── keyboards.py
│
├── orchestrator/           # Core FastAPI service
│   ├── main.py
│   ├── routers/
│   │   ├── chat.py         # POST /chat
│   │   └── confirm.py      # POST /confirm/request, /confirm/reply
│   ├── services/
│   │   ├── llm.py          # OpenAI-compatible client
│   │   ├── speech.py       # STT / TTS abstraction
│   │   ├── scenario.py     # Scenario DB queries
│   │   └── mib.py          # MIB API client (mock)
│   └── models.py           # Pydantic schemas
│
├── db/
│   ├── migrations/         # Alembic
│   └── seed.sql            # Seed scenarios
│
├── speech-api/             # Thin STT/TTS wrapper service
│   ├── main.py
│   └── providers/
│       ├── speechkit.py
│       └── whisper.py
│
├── mock-mib/               # Mock MIB API
│   └── main.py
│
├── docker-compose.yml
├── .env.example
├── README.md
└── IMPLEMENTATION.md
```

---

## Quickstart

```bash
cp .env.example .env
# fill in TELEGRAM_TOKEN, OPENAI_API_KEY (or compatible endpoint), DB_URL

docker compose up --build
```

Bot goes live on Telegram. Send it a text or voice message.

---

## Scenarios (seed data)

| Intent | Example utterance | Required params |
|---|---|---|
| `transfer` | "Transfer 500 to account KZ123" | amount, currency, to_account |
| `balance` | "What's my balance?" | account_id (from session) |
| `payment` | "Pay utility bill" | bill_id, amount |
| `statement` | "Show last 5 transactions" | account_id, limit |

New scenarios are added via DB rows — no code change required.

---

## Environment variables

```env
# Bot
TELEGRAM_TOKEN=

# Orchestrator
OPENAI_API_BASE=https://api.openai.com/v1
OPENAI_API_KEY=
OPENAI_MODEL=gpt-4o

# Speech
SPEECHKIT_API_KEY=
SPEECH_PROVIDER=speechkit   # speechkit | whisper

# DB
DATABASE_URL=postgresql+asyncpg://user:pass@localhost:5432/forte

# Redis
REDIS_URL=redis://localhost:6379/0

# MIB
MIB_API_BASE=http://mock-mib:8001   # swap for real endpoint in prod
MIB_API_TOKEN=
```

---

## Status

| Component | Status |
|---|---|
| Telegram bot (text + voice) | ✅ |
| Orchestrator / FastAPI | ✅ |
| LLM intent classification | ✅ |
| Scenario DB | ✅ |
| Confirmation flow | ✅ |
| Mock MIB API | ✅ |
| Speech API (SpeechKit) | ✅ |
| Speech API (Whisper local) | ✅ |
| Real MIB integration | ⬜ |
| Auth / user identity | ⬜ |
| TTS voice replies | ⬜ |
| Kubernetes manifests | ⬜ |

# Implementation Progress

Snapshot of what has been built against `README.md` and `IMPLEMENTATION.md`.

_Last updated: 2026-06-23_

---

## Summary

Scaffolded the full multi-service Forte Assistant per the spec: Telegram bot,
FastAPI orchestrator, scenario DB, Redis-backed confirmation flow, a speech-api
wrapper, and a mock MIB API — all wired together with Docker Compose.

The **speechkit STT/TTS provider proxies to the existing speech-service**
(`https://github.com/nunmer/speechkit` / `C:\Users\sanzh\Desktop\speechkit`)
via its `POST /stt/recognize` and `POST /tts/synthesize` endpoints, instead of
re-implementing the Yandex REST contract. A local `whisper` provider
(faster-whisper) is the self-contained default.

---

## Done

### Bot (`bot/`) — aiogram 3, long polling
- `main.py` — dispatcher, registers voice router before text router
- `config.py` — env-driven settings
- `keyboards.py` — Yes/No inline confirmation keyboard
- `handlers/text.py` — `/start`, text messages, `confirm:` callback handler
- `handlers/voice.py` — download OGG → `speech-api/stt` → orchestrator, echoes transcript
- `handlers/common.py` — shared orchestrator client
- `Dockerfile`, `requirements.txt`

### Orchestrator (`orchestrator/`) — FastAPI
- `main.py` — app, routers, `/health`
- `config.py` — pydantic-settings (LLM, DB, Redis, MIB, TTLs, min-confidence)
- `models.py` — `ChatRequest/Response`, `IntentResult`, `ConfirmReplyRequest`, `MIBResult`
- `routers/chat.py` — `POST /chat`: classify → scenario lookup → validate params → store pending → confirm
- `routers/confirm.py` — `POST /confirm/reply`: clears pending first (no double-execute), calls MIB
- `services/llm.py` — OpenAI-compatible classifier, JSON-mode + regex fallback, param coercion
- `services/scenario.py` — async SQLAlchemy scenario query
- `services/confirm.py` — Redis pending-confirmation store with TTL
- `services/mib.py` — httpx MIB client with domain-error → user-message mapping
- `db/models.py` — `Scenario` ORM model, `db/database.py` — async engine/session
- `Dockerfile`, `requirements.txt`

### Speech API (`speech-api/`) — FastAPI wrapper
- `main.py` — `POST /stt` (raw bytes + `X-Lang`), `POST /tts` (JSON), `/health`, lazy provider routing
- `providers/speechkit.py` — proxies to the existing speech-service
- `providers/whisper.py` — local faster-whisper, threadpool, lazy model load
- `config.py`, `Dockerfile` (incl. ffmpeg), `requirements.txt`

### Mock MIB (`mock-mib/`)
- `main.py` — catch-all returns 200 + fake `tx_id`, `/health`
- `Dockerfile`, `requirements.txt`

### Infra / data
- `db/seed.sql` — `scenarios` schema + 4 seed rows (transfer, balance, payment, statement)
- `docker-compose.yml` — bot, orchestrator, speech-api, mock-mib, postgres (seed mount + healthcheck), redis; `host.docker.internal` for the speechkit provider
- `.env.example` — all env vars incl. `SPEECHKIT_URL`, `WHISPER_MODEL`, service URLs
- `.gitignore`

---

## Design decisions / deviations from spec

- **speech-api delegates to the existing speech-service** for the speechkit
  provider (the spec inlined the raw Yandex call). This reuses the maintained
  Yandex v3 implementation. Contract to the bot is unchanged (`/stt`, `/tts`).
- **Default `SPEECH_PROVIDER=whisper`** so the stack runs self-contained without
  external SpeechKit credentials. Switch to `speechkit` + set `SPEECHKIT_URL`
  to use Yandex.
- **Confidence gate** (`MIN_CONFIDENCE`) added: low-confidence / `unknown`
  intents get a help message instead of a wrong action.
- **`confirm/reply` clears the pending key before executing** to prevent a
  double-tap from running the operation twice.
- **MIB error mapping**: HTTP/network failures map to user-friendly messages
  rather than leaking stack traces (addresses an "Open problem" from the spec).
- TTS request shape (`OGG_OPUS`) chosen for Telegram voice replies.

---

## Not done yet (TODO)

- [ ] **Alembic migrations** (`db/migrations/`) — schema currently created via
  `seed.sql` on first postgres boot. Add Alembic for prod schema management.
- [ ] **Wire TTS voice replies into the bot** — `speech-api /tts` exists but the
  bot still replies with text only (spec lists this as an open problem).
- [ ] **Tests** — unit tests for `chat` flow (mock llm/scenario/confirm),
  `confirm/reply`, llm JSON-parse fallback, mib error mapping. Target 80%+.
- [ ] **Session store** — `session:{user_id}` (account_id, lang) is specced but
  not yet implemented; needed for `balance`/`statement` which require `account_id`.
- [ ] **Multi-turn context / follow-up param prompts** (spec open problems).
- [ ] **Auth / user identity** before MIB calls.
- [ ] **Kubernetes manifests**.
- [ ] Local validation: `docker compose build` / `up` not yet run in this env.

---

## How to run

```bash
cp .env.example .env          # set TELEGRAM_TOKEN, OPENAI_API_KEY
docker compose up --build
```

To use Yandex SpeechKit instead of local Whisper: set `SPEECH_PROVIDER=speechkit`
and `SPEECHKIT_URL` to a running speech-service instance.

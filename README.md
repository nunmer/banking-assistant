# AI MIB Voice Assistant

> Voice and text banking assistant. A user speaks or types to the web
> client, the system classifies the intent, confirms with the user, and
> executes the operation against the banking core (MIB) API.

**Internal project — ForteBank AI Department.**

---

## What it does

1. User sends a voice note or text through the web client
2. Voice is transcribed via speech-service (self-hosted GigaAM STT, self-hosted Qwen3-TTS)
3. LLM classifies intent and extracts parameters
4. System matches intent against a Scenario DB
5. User is asked to confirm: *"Transfer 10 USD to account X — confirm?"*
6. On approval, the orchestrator calls the MIB (banking-core) API
7. Result is sent back as text or voice

---

## Stack

| Layer | Technology |
|---|---|
| Orchestrator | Python, FastAPI |
| Web voice client + admin panel | Python, FastAPI |
| MIB (banking-core) service | Go — currently a mock; will be pointed at the real MIB API |
| Speech STT/TTS | Self-hosted — GigaAM (STT) / Qwen3-TTS (TTS). Yandex SpeechKit code still present as a fallback engine, not used by default |
| LLM | OpenAI-compatible API (any model) |
| Scenario/operation history DB | PostgreSQL — provided by the target VM, not a container here |
| Session store / job queue / cache | Redis — single shared, stateless container |
| Infra | Docker Compose |

This repo consolidates what used to be two separate GitHub repos
(`banking-assistant`, `speech-service`) into one, and drops the pilot's
Telegram bot in favor of the web client as the only production surface.

---

## Repo structure

```
forte-pilot/
├── orchestrator/         # Core FastAPI service — intent classification,
│                         # confirmation flow, calls speech-service and mib-service
├── web/                  # Voice/text web client + /admin panel
├── mib-service/          # Banking-core API (Go) — mock today, real MIB later
├── speech-service/       # Multi-engine STT/TTS microservice + Celery worker
├── db/                   # seed.sql — reference data for local dev only
├── tests/                # orchestrator/web tests
├── docker-compose.yml    # single consolidated compose file
├── .env.example          # orchestrator/web/mib-service config
├── speech-service/.env.example
└── docs/
    └── VAULT_SECRETS.md  # secrets inventory for DevOps's Vault setup
```

---

## Services (docker-compose.yml)

| Service | Notes |
|---|---|
| `orchestrator` | Runs Alembic migrations on boot, then serves the API |
| `web` | Voice/text UI + `/admin`. Mounts `/var/run/docker.sock` for the admin panel's log viewer — a deliberate but fragile coupling, worth revisiting once DevOps's own logging story exists |
| `mib-service` | Mock banking-core API today |
| `speech-service` / `worker` | API + Celery worker, same image, different `command` |
| `redis` | Single shared instance, **stateless** (no volume, no AOF) — used as a session store (DB 0), Celery broker/results (DB 3/4), and rate-limit/dedup/TTS cache (DB 5) |

**No Postgres container.** Both `orchestrator` and `speech-service` connect
to Postgres on the target VM via `DATABASE_URL` — two separate databases,
`forte` and `speech`, on the same instance. See "Infrastructure
prerequisites" in `docs/VAULT_SECRETS.md`.

**No Telegram bot.** The pilot's Telegram bot (aiogram) has been removed;
the web client is the only production surface. Session identity for an
anonymous browser is a client-generated UUID stored in `localStorage`.

---

## Config & secrets

Real values are not committed. `.env.example` and
`speech-service/.env.example` document every key each service reads;
`docs/VAULT_SECRETS.md` maps them to suggested Vault paths (one per
service) with a one-line purpose note for each, for DevOps to load into
Hashicorp Vault. The one live secret found during consolidation — an
OpenAI API key that was sitting in plaintext in the old pilot's `.env` —
was **not** carried forward; it needs to be rotated and issued fresh
directly into Vault.

---

## Local development

```
cp .env.example .env
cp speech-service/.env.example speech-service/.env
# fill in OPENAI_API_KEY, DATABASE_URL (point at a local/throwaway Postgres), etc.
docker compose up --build
```

`orchestrator` listens on `:8080`, `web` on `:443` (self-signed TLS —
required for microphone access in the browser), `speech-service` on
`:8000`, `mib-service` on `:8001`.

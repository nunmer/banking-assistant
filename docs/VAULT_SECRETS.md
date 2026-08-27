# Vault secrets inventory — AI MIB Voice Assistant

For DevOps: the key/value pairs each service needs, grouped by the Vault
path we'd suggest per service. Values are either left blank (secret —
DevOps issues/rotates directly into Vault) or show the current non-secret
default as a hint. **No live secret values are copied into this file** —
in particular, the `OPENAI_API_KEY` that was sitting in plaintext in the
old `banking-assistant/.env` is NOT reused here; it must be rotated and a
fresh key put directly into Vault.

Two Postgres databases and one shared Redis instance are prerequisites —
see "Infrastructure prerequisites" at the end.

## secret/forte-pilot/orchestrator

Consumed by both `orchestrator` and `web` (they share one env file/config
scope today). Maps to `.env.example` at the repo root.

| Key | Value / default | Purpose |
|---|---|---|
| `OPENAI_API_BASE` | `https://api.openai.com/v1` | LLM endpoint (or internal LiteLLM/gateway proxy URL) |
| `OPENAI_API_KEY` | *(secret)* | LLM API key — rotate, do not reuse the old pilot key |
| `OPENAI_MODEL` | `gpt-4o` | LLM model alias |
| `SPEECH_SERVICE_URL` | `http://speech-service:8000` | Internal URL of speech-service |
| `SPEECH_DEFAULT_LANG` | `ru-RU` | Fallback language (kk-KZ / ru-RU / en-US) |
| `TTS_VOICE_RU` | `marina` | Yandex TTS voice for Russian |
| `TTS_VOICE_KK` | `amira` | Yandex TTS voice for Kazakh |
| `TTS_VOICE_DEFAULT` | `marina` | Fallback TTS voice |
| `ORCHESTRATOR_URL` | `http://orchestrator:8000` | Internal URL web uses to call orchestrator |
| `TTS_VOICE_REPLIES` | `false` | Feature flag: send voice-note replies in addition to text |
| `DATABASE_URL` | *(secret — contains DB password)* | Postgres connection string, database `forte` on the VM instance |
| `REDIS_URL` | `redis://redis:6379/0` | Session store — DB index 0, reserved for this app on the shared Redis |
| `MIB_API_BASE` | `http://mib-service:8001` | Banking-core API base (currently the mock `mib-service`) |
| `MIB_API_TOKEN` | *(secret)* | Auth token for the banking-core API |
| `MIB_AUTH_URL` | *(secret)* | MIB/Auth team's OAuth base URL for the webview client |
| `MIB_AUTH_CLIENT_ID` | *(secret)* | OAuth client id, issued by the MIB/Auth team |
| `MIB_AUTH_CLIENT_SECRET` | *(secret)* | OAuth client secret, issued by the MIB/Auth team |
| `MIB_AUTH_REDIRECT_URI` | *(secret)* | OAuth redirect URI registered with the MIB/Auth team |
| `SPEECH_API_KEY` | *(secret)* | `X-API-Key` sent to speech-service; blank if speech-service auth is disabled |
| `STREAMING_VOICE_ENABLED` | `false` | Feature flag: hands-free streaming voice (buggy as of 2026-07, off by default) |
| `ADMIN_USER` | *(secret)* | Basic Auth username for `/admin` — must not ship as a weak/default value |
| `ADMIN_PASSWORD` | *(secret)* | Basic Auth password for `/admin` — must not ship as a weak/default value |

Dropped from the pilot version: `TELEGRAM_TOKEN`, `WEB_APP_URL` — the
Telegram bot is gone; the web client is the only production surface now.

## secret/forte-pilot/speech-service

Consumed by both `speech-service` and `worker`. Maps to
`speech-service/.env.example`.

| Key | Value / default | Purpose |
|---|---|---|
| `APP_ENV` | `production` | Runtime environment tag |
| `LOG_LEVEL` | `INFO` | Log verbosity |
| `LOG_JSON` | `true` | Structured (JSON) logging |
| `CORS_ORIGINS` | `*` | CORS allow-list — tighten for production if this API is public |
| `DEFAULT_STT_ENGINE` | `gigaam` | Default speech-to-text engine — self-hosted GigaAM |
| `DEFAULT_TTS_ENGINE` | `qwen` | Default text-to-speech engine — self-hosted Qwen3-TTS |
| `DATABASE_URL` | *(secret — contains DB password)* | Postgres connection string, database `speech` on the VM instance |
| `CELERY_BROKER_URL` | `redis://redis:6379/3` | Celery broker — DB index 3, reserved for this app on the shared Redis |
| `CELERY_RESULT_BACKEND` | `redis://redis:6379/4` | Celery result backend — DB index 4 |
| `REDIS_URL` | `redis://redis:6379/5` | Rate-limit/dedup/TTS cache — DB index 5 |
| `CELERY_QUEUE` | `speech_queue` | Celery queue name |
| `UPLOAD_DIR` | `/app/uploads` | Shared audio upload path (API + worker volume) |
| `API_KEY_ENABLED` | `false` | Toggle for `X-API-Key` auth on this service's own API |
| `API_KEY_HEADER` | `X-API-Key` | Header name for the above |
| `RATE_LIMIT_ENABLED` | `false` | Per-key rate limiting toggle |
| `RATE_LIMIT_MAX_REQUESTS` | `60` | Rate limit ceiling |
| `RATE_LIMIT_WINDOW_SECONDS` | `60` | Rate limit window |
| `DEDUP_ENABLED` | `true` | Request/response dedup toggle |
| `TTS_CACHE_TTL_SECONDS` | `86400` | TTS cache lifetime |
| `GIGAAM_STT_URL` | `http://10.0.94.187:8003/v1/audio/transcriptions` | Self-hosted GigaAM STT engine endpoint |
| `GIGAAM_MODEL` | `gigaam-multilingual-large-ctc` | GigaAM model name |
| `GIGAAM_TIMEOUT` | `120` | Request timeout (seconds) |
| `QWEN_TTS_URL` | `http://10.0.94.187:8002/v1/audio/speech` | Self-hosted Qwen3-TTS engine endpoint |
| `QWEN_TTS_MODEL` | `Qwen/Qwen3-TTS-12Hz-1.7B-CustomVoice` | Qwen3-TTS model name |
| `QWEN_TIMEOUT` | `120` | Request timeout (seconds) |

Dropped from the pilot version: all `YANDEX_*` vars — neither default
engine uses Yandex anymore (STT is GigaAM, TTS is Qwen3-TTS). Only needed
again if something explicitly requests `engine=yandex`, or if the
Yandex-only hands-free streaming voice feature (`STREAMING_VOICE_ENABLED`)
is ever re-enabled — see `speech-service/.env.example`'s note.

## secret/forte-pilot/mib-service

`mib-service` (the Go mock banking-core service) currently reads **no
environment variables at all** — it's a self-contained mock. Nothing to
put in Vault today. Once it's pointed at the real MIB banking-core API
(the currently-planned next step), this path will need the real API's
base URL and credentials — revisit this doc at that point.

## Infrastructure prerequisites (not application secrets, but blocking)

- **Two Postgres databases** on the existing VM instance: `forte` (used by
  `orchestrator`) and `speech` (used by `speech-service`). Each needs its
  own user/password — those passwords are exactly what's embedded in the
  two `DATABASE_URL` secrets above.
- **One shared, stateless Redis** — this repo's `docker-compose.yml`
  already runs it as a plain container with no persistent volume (matches
  "production has no PVC"). No Vault secret needed for Redis itself since
  it's unauthenticated on the internal network; flag to DevOps if that
  assumption is wrong for the target environment.

# Speech Service — Implementation Plan

## Guiding principle

Adopt an **async-job spine** plus **cost/safety controls**. The STT path is already
long-running (Yandex `recognizeFileAsync` + `poll_result`) but currently executes
**inside the FastAPI request handler**, holding a worker process open for the full
duration of recognition. Fixing that is the backbone of this plan; everything else
builds on it. We deliberately skip anything that doesn't earn its place at our scale.

---

## What we are NOT doing / removing

- **Trim k8s to a minimal set.** Keep `service.yml` and add `pv.yml` / `pvc.yml`
  (shared audio volume). **Delete** `hpa.yml`, `pdb.yml`, `ingress.yml`,
  `configmap.yml`, `secret.yml`, `namespace.yml` — premature for current scale.
  Secrets/config flow through `.env` + the platform secret store.
- **No users/admin/RBAC table.** We need API keys for cost control, not a
  user-management system.
- **No domain-specific classification/layout logic.** Not applicable to speech.
- **No node-exporter container** initially — revisit only if self-hosting bare metal.
- **TTS stays fully synchronous.** It is fast; a queue there is pure overhead.

---

## Phase 1 — Async job spine (core fix)

**Goal:** stop blocking FastAPI workers on long-running recognition.

**New infra:**
- **Redis** — Celery broker (db0) + result backend (db1).
- **Postgres + SQLAlchemy (asyncpg) + Alembic** — durable job + result storage.
- **Celery worker** — separate process/container, queue `speech_queue`.

**New code:**
- `app/db/database.py`, `app/db/models.py` — `speech_jobs` table:
  `id, kind (recognize|transcribe), engine, status (queued|processing|completed|failed),
  lang, params (jsonb), input_hash, audio_path, result (jsonb), error, timestamps`.
- `alembic/` + first migration creating `speech_jobs`.
- `app/core/celery_app.py` + `app/tasks/stt_tasks.py` — `run_stt_job(job_id)`:
  load audio from volume → call existing `YandexSTTEngine` (unchanged) →
  write result/status to DB.
- `app/tasks/startup_tasks.py` — re-queue orphaned `queued`/`processing` jobs on
  worker startup.
- **File storage:** save uploads to `/app/uploads/{uuid}.wav` on a shared volume (PVC),
  mounted into API + worker.

**Endpoint changes (`app/routers/stt.py`):**
- Keep `/stt/recognize` & `/stt/transcribe` **synchronous for short audio**
  (under a duration threshold — `wav_duration` is already computed).
- For long audio (or `?async=true`): persist job + `task.delay(job_id)` →
  return `{job_id, status: "queued"}` (HTTP 202).
- Add `app/routers/jobs.py`: `GET /jobs/{job_id}` → status + result (polling endpoint).

**Decision point:** sync/async split by *duration threshold* (recommended, ~60s)
vs *explicit flag*.

---

## Phase 2 — Cost & safety (high ROI under per-call billing)

- **API-key auth** — `app/core/auth.py` + `api_keys` table
  (`key_hash, name, is_active, created_at`); `X-API-Key` header dependency on all
  `/tts` + `/stt` routes. Hashed at rest.
- **Rate limiting** — per-key, Redis-backed (e.g. `slowapi` or a small token-bucket
  dependency).
- **Deduplication** — SHA256 of audio bytes (STT) / `hash(text+voice+lang+format)` (TTS).
  On a hit with a `completed` job, return the cached result instead of re-calling the
  upstream engine. Biggest direct cost saver.
- Lock down CORS (`allow_origins=["*"]` → configurable allowlist).

---

## Phase 3 — Observability & hardening

- **Monitoring config** (files, not new app code): `monitoring/prometheus.yml`,
  `monitoring/alerts.yml`, `monitoring/grafana/dashboards/*` — request
  rate/latency/errors, job queue depth, processing duration, engine errors,
  audio-seconds processed. Most of these metrics are already emitted.
- **Correlation IDs** — extend `RequestLoggingMiddleware` to thread `request_id` into
  job records and worker logs, so a request is traceable across the queue boundary.
  Today it stops at the HTTP layer.
- **Integration tests + mock upstream server** — `docker/mocks/mock_server.py` +
  `docker/Dockerfile.test`, so CI runs end-to-end without spending on the live paid API.
  Add `tests/integration/`.
- **Docs** — `docs/ARCHITECTURE.md` (data flow), `docs/AUTHENTICATION.md`,
  `docs/MONITORING.md`.

---

## Compose / deployment changes

- `docker-compose.yml`: add `redis`, `postgres`, `worker` services alongside `api`;
  shared `uploads` volume.
- `docker/entrypoint.sh`: branch for `api` vs `worker` start commands.
- k8s: trim to `service` + `pv`/`pvc`, add a `worker` Deployment.

---

## Sequencing

1. **Phase 1** — unblocks scalability; everything else depends on the DB + job model.
2. **Phase 2** — immediate cost/abuse protection.
3. **Phase 3** — ops maturity.

---

## Open decisions before coding Phase 1

1. **Sync/async split:** duration threshold (recommended) or explicit `?async=true` flag?
2. **Scope of this pass:** all three phases, or land Phase 1 first and review before continuing?

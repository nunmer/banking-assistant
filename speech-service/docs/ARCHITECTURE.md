# Architecture

The speech service is a multi-engine TTS/STT API with a synchronous fast path and
an asynchronous job pipeline for long-running speech-to-text.

## Components

| Component | Role |
|---|---|
| **API** (FastAPI) | HTTP endpoints, validation, auth, dedup, job submission |
| **Worker** (Celery) | Background STT processing of queued jobs |
| **Postgres** | Durable job records + results, API keys |
| **Redis** | Celery broker + result backend; rate-limit counters; TTS audio cache |
| **Shared volume** | Uploaded audio, readable by both API and worker |

All of API, worker, and the supporting services run from the same image
(`Dockerfile`); the container role is selected by the entrypoint argument
(`api` or `worker`).

## Request flows

### TTS (synchronous)

```
client → POST /tts/synthesize
      → dedup check (Redis cache by text+voice+lang+format)
      → hit:  return cached audio
      → miss: engine.synthesize() → cache → return audio
```

### STT — synchronous (short audio)

```
client → POST /stt/recognize | /stt/transcribe
      → normalize audio → engine → return result inline
```

### STT — asynchronous (long audio)

```
client → POST /stt/recognize/async | /stt/transcribe/async
      → normalize audio
      → dedup check (Postgres: completed job with same input hash)
      → hit:  return {job_id, status: completed, cached: true}
      → miss: save audio to volume
              → create job row (status=queued)
              → enqueue Celery task
              → return 202 {job_id, status: queued}

worker → run_stt_job(job_id)
      → status=processing → engine → status=completed (+result) | failed (+error)

client → GET /jobs/{job_id}  (poll)
      → {status, result|error}
```

The synchronous and asynchronous STT paths share the same engine logic
(`app/services/stt_runner.py:build_result`) so results never diverge.

## Reliability

- **Orphan recovery:** on worker startup, jobs left in `queued`/`processing`
  (e.g. after a crash) are re-queued (`app/tasks/startup_tasks.py`).
- **Acks late + prefetch 1:** a job is acknowledged only after completion, so a
  crashed worker's job is redelivered.
- **Dedup:** identical STT input returns the prior completed job; identical TTS
  input returns cached audio — avoiding repeat upstream spend.

## Key modules

```
app/
  main.py                 FastAPI app, router wiring, CORS, auth/rate-limit deps
  core/
    config.py             Pydantic settings (env-driven)
    celery_app.py         Celery configuration
    auth.py               API-key dependency
    ratelimit.py          Redis fixed-window limiter
    middleware.py         Request logging + correlation id (X-Request-ID)
  db/
    models.py             SpeechJob, ApiKey
    database.py           Engine, session_scope (worker), get_db (API dep)
  engines/                Pluggable STT/TTS engines (base ABC + factory)
  services/
    jobs.py               Job CRUD + state transitions
    stt_runner.py         Shared engine processing (sync route + worker)
    storage.py            Audio file storage on the shared volume
    dedup.py              Content hashing
    cache.py              Redis client + TTS audio cache
  tasks/
    stt_tasks.py          run_stt_job
    startup_tasks.py      orphan recovery
  routers/
    stt.py                sync + async STT endpoints
    tts.py                TTS endpoint
    jobs.py               job status polling
```

See [AUTHENTICATION.md](AUTHENTICATION.md).

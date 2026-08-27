# Authentication & Rate Limiting

## API keys

All `/tts`, `/stt`, and `/jobs` endpoints can require an API key. Disabled by
default for local development.

Enable it:

```
API_KEY_ENABLED=true
```

Clients send the key in the configured header (default `X-API-Key`):

```bash
curl -X POST http://localhost:8000/stt/recognize \
  -H "X-API-Key: <key>" \
  -F "file=@audio.wav"
```

Keys are stored as SHA256 hashes — the plaintext is shown only once at creation.

### Creating a key

```bash
python scripts/create_api_key.py "client name"
# prints the plaintext key once; store it now
```

(Run inside the API/worker container, or anywhere with `DATABASE_URL` set.)

## Rate limiting

Per-key fixed-window limiting backed by Redis. Disabled by default.

```
RATE_LIMIT_ENABLED=true
RATE_LIMIT_MAX_REQUESTS=60
RATE_LIMIT_WINDOW_SECONDS=60
```

Over-limit requests get `429 Too Many Requests`. The limiter **fails open**: if
Redis is unreachable, requests are allowed rather than blocked.

## CORS

`CORS_ORIGINS` accepts `*` (any origin) or a comma-separated allowlist:

```
CORS_ORIGINS=https://app.example.com,https://admin.example.com
```

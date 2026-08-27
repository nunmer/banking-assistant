#!/bin/sh
set -e

ROLE="${1:-api}"

case "$ROLE" in
  api)
    # Apply migrations, then serve the API.
    alembic upgrade head || echo "warning: 'alembic upgrade head' failed (continuing)"
    exec uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers "${WORKERS:-4}"
    ;;
  worker)
    exec celery -A app.core.celery_app.celery_app worker \
      --loglevel="${LOG_LEVEL:-info}" \
      -Q "${CELERY_QUEUE:-speech_queue}" \
      -c "${WORKER_CONCURRENCY:-4}"
    ;;
  *)
    # Arbitrary command (e.g. running a script).
    exec "$@"
    ;;
esac

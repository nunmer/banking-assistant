FROM mwader/static-ffmpeg:7.1 AS ffmpeg

FROM python:3.12-slim AS builder

WORKDIR /build

# All deps in requirements.txt ship manylinux wheels for this base image
# (psycopg2-binary, soundfile, numpy, grpcio) — no apt/gcc needed to build.
COPY requirements.txt .
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt


FROM python:3.12-slim AS runtime

WORKDIR /app

# soundfile's wheel already bundles libsndfile — no apt package needed.
# Healthcheck uses Python's stdlib instead of curl for the same reason.
RUN useradd -r -u 1001 -s /bin/false appuser && \
    mkdir -p /app/uploads && \
    chown appuser /app/uploads

COPY --from=builder /install /usr/local
# Static binary — same apt-unreachable workaround as banking-assistant/web.
# Only qwen's engine needs this (transcodes its WAV-only output to whatever
# `fmt` the caller asked for); yandex/gigaam don't touch it.
COPY --from=ffmpeg /ffmpeg /usr/local/bin/ffmpeg
COPY app/ app/
COPY alembic/ alembic/
COPY alembic.ini ./
COPY scripts/ scripts/
COPY docker/entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

USER appuser

EXPOSE 8000

ENV PYTHONPATH=/app

HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')" || exit 1

ENTRYPOINT ["/entrypoint.sh"]
CMD ["api"]

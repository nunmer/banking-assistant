FROM python:3.12-slim

WORKDIR /app

# DejaVu Sans: a Unicode TTF (Cyrillic + Latin) for the statement PDF —
# python:3.12-slim ships no fonts at all, and fpdf2's built-in core fonts
# are Latin-1 only, which can't render Russian/Kazakh statement text.
RUN apt-get update \
    && apt-get install -y --no-install-recommends fonts-dejavu-core \
    && rm -rf /var/lib/apt/lists/*

COPY orchestrator/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

COPY orchestrator ./orchestrator

EXPOSE 8000

# Run Alembic migrations then start the server.
CMD ["sh", "-c", "alembic -c orchestrator/alembic.ini upgrade head && uvicorn orchestrator.main:app --host 0.0.0.0 --port 8000"]

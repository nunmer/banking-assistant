FROM python:3.12-slim

WORKDIR /app

COPY orchestrator/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

COPY orchestrator ./orchestrator

EXPOSE 8000

# Run Alembic migrations then start the server.
CMD ["sh", "-c", "alembic -c orchestrator/alembic.ini upgrade head && uvicorn orchestrator.main:app --host 0.0.0.0 --port 8000"]

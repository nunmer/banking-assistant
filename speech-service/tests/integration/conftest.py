"""Integration tests exercise the full async spine (DB + Celery + endpoints).

They are skipped unless RUN_INTEGRATION=1 and a reachable DATABASE_URL are set.
Run them against the dev stack:

    docker compose -f docker-compose.dev.yml up -d postgres redis
    RUN_INTEGRATION=1 DATABASE_URL=postgresql+psycopg2://speech:speech@localhost:5432/speech \\
        pytest tests/integration
"""
import os

import pytest

if os.getenv("RUN_INTEGRATION") != "1":
    pytest.skip("integration tests disabled (set RUN_INTEGRATION=1)", allow_module_level=True)


@pytest.fixture(scope="session", autouse=True)
def _schema():
    from app.db.database import engine
    from app.db.models import Base

    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)


@pytest.fixture(autouse=True)
def _eager_celery():
    from app.core.celery_app import celery_app

    celery_app.conf.task_always_eager = True
    celery_app.conf.task_eager_propagates = False
    yield
    celery_app.conf.task_always_eager = False


@pytest.fixture(autouse=True)
def _tmp_uploads(tmp_path, monkeypatch):
    from app.core.config import settings

    monkeypatch.setattr(settings, "UPLOAD_DIR", str(tmp_path), raising=False)
    yield

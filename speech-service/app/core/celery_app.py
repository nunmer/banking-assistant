from celery import Celery

from app.core.config import settings
from app.core.logging import setup_logging

celery_app = Celery(
    "speech",
    broker=settings.CELERY_BROKER_URL,
    backend=settings.CELERY_RESULT_BACKEND,
)

celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    task_default_queue=settings.CELERY_QUEUE,
    task_acks_late=True,
    task_track_started=True,
    worker_prefetch_multiplier=1,
    worker_max_tasks_per_child=200,
    result_expires=3600,
    timezone="UTC",
)

# Ensure task modules are imported so they register with the app.
celery_app.autodiscover_tasks(["app.tasks"])


@celery_app.on_after_configure.connect
def _configure_logging(sender, **kwargs):
    setup_logging(level=settings.LOG_LEVEL, json_output=settings.LOG_JSON)

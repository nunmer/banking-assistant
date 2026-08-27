"""Worker startup hook: re-queue jobs orphaned by a crashed/restarted worker."""
import logging

from celery.signals import worker_ready

from app.db.database import session_scope
from app.services import jobs as jobs_service

logger = logging.getLogger("speech_service.tasks")


@worker_ready.connect
def requeue_orphaned_jobs(**kwargs) -> None:
    from app.tasks.stt_tasks import run_stt_job

    try:
        with session_scope() as db:
            orphans = jobs_service.find_orphans(db)
            ids = [job.id for job in orphans]
    except Exception as e:  # DB not reachable yet — don't crash the worker
        logger.warning("orphan recovery skipped: %s", e)
        return

    for job_id in ids:
        run_stt_job.delay(job_id)
    if ids:
        logger.info("re-queued %d orphaned job(s)", len(ids))

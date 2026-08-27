import logging

from app.core.celery_app import celery_app
from app.db.database import session_scope
from app.services import jobs as jobs_service, stt_runner

logger = logging.getLogger("speech_service.tasks")


@celery_app.task(name="run_stt_job", bind=True)
def run_stt_job(self, job_id: str) -> None:
    with session_scope() as db:
        job = jobs_service.get(db, job_id)
        if job is None:
            logger.error("run_stt_job: job %s not found", job_id)
            return
        request_id = job.request_id
        try:
            stt_runner.process(db, job)
            logger.info(
                "job %s completed", job_id, extra={"request_id": request_id}
            )
        except Exception as e:
            logger.error(
                "job %s failed: %s", job_id, e, extra={"request_id": request_id}
            )

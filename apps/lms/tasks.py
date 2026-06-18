"""Celery tasks for LMS asynchronous operations."""

from __future__ import annotations

import logging
from typing import Any

from celery import shared_task

from apps.lms.models import LessonVideoProcessingJob
from apps.lms.services import fail_lesson_video_job, process_lesson_video_job

logger = logging.getLogger("apps.lms")


@shared_task(
    name="apps.lms.tasks.process_lesson_video_job_task",
    bind=True,
    max_retries=3,
    default_retry_delay=120,
)
def process_lesson_video_job_task(self, *, job_id: int) -> dict[str, Any]:
    """Process one queued lesson video job through the configured processing provider."""
    try:
        job = LessonVideoProcessingJob.objects.select_related("lesson").get(pk=job_id)
        processed = process_lesson_video_job(job=job)
    except LessonVideoProcessingJob.DoesNotExist:
        logger.warning("LMS video processing job missing job_id=%s", job_id)
        return {"job_id": job_id, "status": "missing"}
    except Exception as exc:
        logger.exception("LMS video processing failed job_id=%s error_type=%s", job_id, type(exc).__name__)
        job = LessonVideoProcessingJob.objects.filter(pk=job_id).first()
        if job is not None:
            fail_lesson_video_job(job=job, error_message=type(exc).__name__)
        raise
    return {"job_id": processed.pk, "status": processed.status, "lesson_id": processed.lesson_id}

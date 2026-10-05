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
        logger.exception(
            "LMS video processing failed job_id=%s error_type=%s", job_id, type(exc).__name__
        )
        job = LessonVideoProcessingJob.objects.filter(pk=job_id).first()
        if job is not None:
            fail_lesson_video_job(job=job, error_message=type(exc).__name__)
        raise
    return {"job_id": processed.pk, "status": processed.status, "lesson_id": processed.lesson_id}


@shared_task(
    name="apps.lms.tasks.render_lesson_document_pages_task",
    bind=True,
    max_retries=2,
    default_retry_delay=60,
)
def render_lesson_document_pages_task(self, *, lesson_id: int) -> dict[str, Any]:
    """Pre-render one document lesson's pages (PDFium → WebP) out of request path.

    idempotent: با manifestِ تازه، ensure_document_pages بدونِ رندر برمی‌گردد.
    شکستِ غیرموقعی (PDF رمزدار/خراب) retry نمی‌خواهد — fallbackِ pdf.js خودش
    مراقب است؛ فقط خطاهایِ زیرساختی (storage/دیسک) دوباره تلاش می‌کنند.
    """
    from apps.lms.models import Lesson
    from apps.lms.pdf_pages import ensure_document_pages
    from apps.lms.services import LessonMediaUnavailableError

    lesson = Lesson.objects.filter(pk=lesson_id).first()
    if lesson is None or not lesson.document_file:
        return {"lesson_id": lesson_id, "status": "skipped"}
    try:
        pages = ensure_document_pages(lesson)
    except (OSError, LessonMediaUnavailableError) as exc:
        logger.warning(
            "LMS document render failed lesson_id=%s error_type=%s",
            lesson_id,
            type(exc).__name__,
        )
        raise self.retry(exc=exc) from exc
    except Exception:
        logger.exception("LMS document render failed lesson_id=%s", lesson_id)
        return {"lesson_id": lesson_id, "status": "failed"}
    return {
        "lesson_id": lesson_id,
        "status": "rendered" if pages else "unrenderable",
        "pages": len(pages or []),
    }

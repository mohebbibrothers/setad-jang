"""LMS C2 video processing worker tests."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken

from apps.audit_logs import actions as audit_actions
from apps.lms.choices import VideoProcessingStatus
from apps.lms.models import LessonVideoProcessingJob
from apps.lms.services import (
    VideoProcessingJobError,
    process_lesson_video_job,
    request_lesson_video_processing,
)
from apps.lms.tasks import process_lesson_video_job_task
from tests.factories.auth import AdminUserFactory
from tests.factories.lms import LessonFactory

pytestmark = pytest.mark.django_db

_AUDIT_TASK_PATH = "apps.audit_logs.tasks.create_audit_log_task"
_TASK_DELAY_PATH = "apps.lms.tasks.process_lesson_video_job_task.delay"


def _admin_client(admin_user=None) -> APIClient:
    """Build JWT-authenticated LMS admin client."""
    user = admin_user or AdminUserFactory()
    client = APIClient()
    refresh = RefreshToken.for_user(user)
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {refresh.access_token!s}")
    return client


def _video_file() -> SimpleUploadedFile:
    """Return a tiny fake MP4 upload for service tests."""
    return SimpleUploadedFile("lesson.mp4", b"fake-video", content_type="video/mp4")


def test_request_video_processing_requires_uploaded_video() -> None:
    """Processing request should fail when lesson has no uploaded video."""
    lesson = LessonFactory(video_file=None)

    with pytest.raises(VideoProcessingJobError, match="فایل ویدئویی"):
        request_lesson_video_processing(lesson=lesson)


def test_request_video_processing_is_idempotent_for_active_job() -> None:
    """A queued/processing job should be reused instead of duplicated."""
    lesson = LessonFactory(video_file=_video_file(), duration_seconds=120)

    first = request_lesson_video_processing(lesson=lesson)
    second = request_lesson_video_processing(lesson=lesson)

    assert first.pk == second.pk
    assert LessonVideoProcessingJob.objects.filter(lesson=lesson).count() == 1
    assert first.status == VideoProcessingStatus.QUEUED


def test_process_lesson_video_job_completes_noop_provider() -> None:
    """No-op/local provider should complete job with media metadata safely."""
    lesson = LessonFactory(video_file=_video_file(), duration_seconds=321)
    job = request_lesson_video_processing(lesson=lesson)

    processed = process_lesson_video_job(job=job)

    assert processed.status == VideoProcessingStatus.COMPLETED
    assert processed.duration_seconds == 321
    assert processed.output_video_url
    assert processed.metadata["processed_by"] == "noop_local_provider"
    assert processed.completed_at is not None


def test_video_processing_task_processes_job() -> None:
    """Celery task should process existing job and return operational result."""
    lesson = LessonFactory(video_file=_video_file(), duration_seconds=80)
    job = request_lesson_video_processing(lesson=lesson)

    result = process_lesson_video_job_task.apply(kwargs={"job_id": job.pk}).get()

    job.refresh_from_db()
    assert result["job_id"] == job.pk
    assert result["status"] == VideoProcessingStatus.COMPLETED
    assert job.status == VideoProcessingStatus.COMPLETED


def test_admin_video_processing_endpoint_queues_job_and_audits() -> None:
    """Admin endpoint should queue processing, dispatch task and audit request."""
    admin = AdminUserFactory()
    lesson = LessonFactory(video_file=_video_file(), duration_seconds=64)
    client = _admin_client(admin)

    with patch(_AUDIT_TASK_PATH) as mock_audit_task, patch(_TASK_DELAY_PATH) as mock_delay:
        mock_audit_task.delay = MagicMock()
        response = client.post(
            reverse("lms:admin-lesson-video-processing", kwargs={"lesson_id": lesson.pk})
        )

    assert response.status_code == status.HTTP_201_CREATED
    job = LessonVideoProcessingJob.objects.get(pk=response.data["data"]["id"])
    assert job.lesson == lesson
    assert job.requested_by == admin
    mock_delay.assert_called_once_with(job_id=job.pk)
    called_actions = [call.kwargs.get("action") for call in mock_audit_task.delay.call_args_list]
    assert audit_actions.LMS_VIDEO_PROCESSING_REQUESTED in called_actions


def test_admin_video_processing_status_endpoint_returns_latest_job() -> None:
    """Admin status endpoint should return latest processing job for lesson."""
    lesson = LessonFactory(video_file=_video_file())
    job = request_lesson_video_processing(lesson=lesson)
    client = _admin_client()

    response = client.get(
        reverse("lms:admin-lesson-video-processing-status", kwargs={"lesson_id": lesson.pk})
    )

    assert response.status_code == status.HTTP_200_OK
    assert response.data["data"]["id"] == job.pk

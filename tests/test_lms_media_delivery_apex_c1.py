"""LMS Apex C1 signed/CDN-ready media delivery tests."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient

from apps.audit_logs import actions as audit_actions
from apps.lms.choices import EnrollmentStatus
from apps.lms.services import (
    LessonMediaAccessError,
    LessonMediaUnavailableError,
    build_lesson_media_access,
)
from tests.factories import UserFactory
from tests.factories.lms import EnrollmentFactory, LessonFactory, PublishedCourseFactory

pytestmark = pytest.mark.django_db

_AUDIT_TASK_PATH = "apps.audit_logs.tasks.create_audit_log_task"


def _client_for(user) -> APIClient:
    """Return authenticated API client."""
    client = APIClient()
    client.force_authenticate(user=user)
    return client


def test_enrolled_user_can_get_uploaded_video_media_access() -> None:
    """Enrolled users should receive a storage URL for uploaded lesson video."""
    course = PublishedCourseFactory(title="CDN Course")
    lesson = LessonFactory(course=course, video_file=SimpleUploadedFile("lesson.mp4", b"video"))
    enrollment = EnrollmentFactory(course=course, status=EnrollmentStatus.ACTIVE)

    payload = build_lesson_media_access(lesson=lesson, user=enrollment.user, media_kind="video")

    assert payload["media_kind"] == "video"
    assert payload["provider"] == "uploaded_file"
    assert payload["expires_in_seconds"] == 600
    assert payload["lesson_id"] == lesson.pk
    assert payload["url"]


def test_enrolled_user_can_get_attachment_media_access() -> None:
    """Enrolled users should receive a storage URL for lesson attachment."""
    course = PublishedCourseFactory(title="Attachment Course")
    lesson = LessonFactory(course=course, attachment_file=SimpleUploadedFile("handout.pdf", b"pdf"), attachment_title="جزوه")
    enrollment = EnrollmentFactory(course=course, status=EnrollmentStatus.ACTIVE)

    payload = build_lesson_media_access(lesson=lesson, user=enrollment.user, media_kind="attachment")

    assert payload["media_kind"] == "attachment"
    assert payload["title"] == "جزوه"
    assert payload["url"]


def test_direct_url_video_is_returned_for_enrolled_user() -> None:
    """Direct video URL lessons should still use the media access contract."""
    course = PublishedCourseFactory()
    lesson = LessonFactory(course=course, video_url="https://cdn.example.com/video.mp4")
    enrollment = EnrollmentFactory(course=course)

    payload = build_lesson_media_access(lesson=lesson, user=enrollment.user, media_kind="video")

    assert payload["provider"] == "direct_url"
    assert payload["url"] == "https://cdn.example.com/video.mp4"
    assert payload["expires_in_seconds"] is None


def test_non_enrolled_user_cannot_access_non_preview_media() -> None:
    """Non-enrolled users must not receive private media access."""
    lesson = LessonFactory(video_file=SimpleUploadedFile("lesson.mp4", b"video"), is_preview=False)

    with pytest.raises(LessonMediaAccessError):
        build_lesson_media_access(lesson=lesson, user=UserFactory(), media_kind="video")


def test_preview_lesson_allows_media_access_without_enrollment() -> None:
    """Preview lessons may expose media to non-enrolled authenticated users."""
    lesson = LessonFactory(video_url="https://cdn.example.com/preview.mp4", is_preview=True)

    payload = build_lesson_media_access(lesson=lesson, user=UserFactory(), media_kind="video")

    assert payload["url"] == "https://cdn.example.com/preview.mp4"


def test_missing_media_raises_unavailable() -> None:
    """Unavailable media kind should fail with domain error."""
    course = PublishedCourseFactory()
    lesson = LessonFactory(course=course)
    enrollment = EnrollmentFactory(course=course)

    with pytest.raises(LessonMediaUnavailableError):
        build_lesson_media_access(lesson=lesson, user=enrollment.user, media_kind="attachment")


def test_media_access_endpoint_returns_payload_and_audits() -> None:
    """API endpoint should return media payload and dispatch audit."""
    course = PublishedCourseFactory()
    lesson = LessonFactory(course=course, video_url="https://cdn.example.com/video.mp4")
    enrollment = EnrollmentFactory(course=course)

    with patch(_AUDIT_TASK_PATH) as mock_task:
        mock_task.delay = MagicMock()
        response = _client_for(enrollment.user).get(reverse("lms:lesson-media-access", kwargs={"lesson_id": lesson.pk, "media_kind": "video"}))

    assert response.status_code == status.HTTP_200_OK
    assert response.data["data"]["url"] == "https://cdn.example.com/video.mp4"
    assert mock_task.delay.call_args.kwargs["action"] == audit_actions.LMS_LESSON_MEDIA_ACCESSED


def test_media_access_endpoint_rejects_non_enrolled_user() -> None:
    """API endpoint must enforce enrollment."""
    lesson = LessonFactory(video_url="https://cdn.example.com/private.mp4", is_preview=False)

    response = _client_for(UserFactory()).get(reverse("lms:lesson-media-access", kwargs={"lesson_id": lesson.pk, "media_kind": "video"}))

    assert response.status_code == status.HTTP_403_FORBIDDEN

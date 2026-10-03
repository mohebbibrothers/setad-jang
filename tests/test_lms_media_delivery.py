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
    sign_lesson_media_token,
)
from tests.factories import UserFactory
from tests.factories.lms import (
    DocumentLessonFactory,
    EnrollmentFactory,
    LessonFactory,
    PublishedCourseFactory,
)

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
    assert payload["expires_in_seconds"] == 12 * 60 * 60
    assert payload["lesson_id"] == lesson.pk
    assert payload["url"].startswith(f"lms/lessons/{lesson.pk}/media/video/stream/?t=")
    assert not payload["url"].startswith("/media/")


def test_enrolled_user_can_get_attachment_media_access() -> None:
    """Enrolled users should receive a storage URL for lesson attachment."""
    course = PublishedCourseFactory(title="Attachment Course")
    lesson = LessonFactory(
        course=course,
        attachment_file=SimpleUploadedFile("handout.pdf", b"pdf"),
        attachment_title="جزوه",
    )
    enrollment = EnrollmentFactory(course=course, status=EnrollmentStatus.ACTIVE)

    payload = build_lesson_media_access(
        lesson=lesson, user=enrollment.user, media_kind="attachment"
    )

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
        response = _client_for(enrollment.user).get(
            reverse(
                "lms:lesson-media-access", kwargs={"lesson_id": lesson.pk, "media_kind": "video"}
            )
        )

    assert response.status_code == status.HTTP_200_OK
    assert response.data["data"]["url"] == "https://cdn.example.com/video.mp4"
    assert mock_task.delay.call_args.kwargs["action"] == audit_actions.LMS_LESSON_MEDIA_ACCESSED


def test_media_access_endpoint_rejects_non_enrolled_user() -> None:
    """API endpoint must enforce enrollment."""
    lesson = LessonFactory(video_url="https://cdn.example.com/private.mp4", is_preview=False)

    response = _client_for(UserFactory()).get(
        reverse("lms:lesson-media-access", kwargs={"lesson_id": lesson.pk, "media_kind": "video"})
    )

    assert response.status_code == status.HTTP_403_FORBIDDEN


# ---------------------------------------------------------------------------
# In-site media streaming (no raw download links)
# ---------------------------------------------------------------------------


def _stream_url(lesson, media_kind: str) -> str:
    return reverse(
        "lms:lesson-media-stream",
        kwargs={"lesson_id": lesson.pk, "media_kind": media_kind},
    )


class TestLessonMediaStream:
    """استریمِ درون‌سایتی: فایل از خودِ بک‌اند، بدون لینکِ خامِ دانلود."""

    def test_enrolled_user_streams_document_inline_with_hardened_headers(self) -> None:
        course = PublishedCourseFactory()
        lesson = DocumentLessonFactory(course=course, order=1)
        enrollment = EnrollmentFactory(course=course, status=EnrollmentStatus.ACTIVE)

        with patch("apps.lms.views_learning.log_action_async") as mock_log:
            response = _client_for(enrollment.user).get(_stream_url(lesson, "document"))

        assert response.status_code == status.HTTP_200_OK
        assert response["Content-Type"] == "application/pdf"
        assert response["X-Content-Type-Options"] == "nosniff"
        assert response["Cache-Control"] == "private, must-revalidate"
        assert response["Content-Security-Policy"] == "sandbox"
        assert "attachment" not in response["Content-Disposition"]
        assert b"".join(response.streaming_content) == b"%PDF-1.4 fixture"
        mock_log.assert_called_once()
        assert mock_log.call_args.kwargs["action"] == audit_actions.LMS_LESSON_MEDIA_STREAMED

    def test_enrolled_user_streams_video_inline(self) -> None:
        course = PublishedCourseFactory()
        lesson = LessonFactory(course=course, video_file=SimpleUploadedFile("lesson.mp4", b"video"))
        enrollment = EnrollmentFactory(course=course, status=EnrollmentStatus.ACTIVE)

        response = _client_for(enrollment.user).get(_stream_url(lesson, "video"))

        assert response.status_code == status.HTTP_200_OK
        assert response["Content-Type"] == "video/mp4"
        assert b"".join(response.streaming_content) == b"video"

    def test_stranger_cannot_stream_lesson_media(self) -> None:
        lesson = DocumentLessonFactory(is_preview=False)

        response = _client_for(UserFactory()).get(_stream_url(lesson, "document"))

        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_sequence_locked_lesson_cannot_be_streamed(self) -> None:
        course = PublishedCourseFactory()
        DocumentLessonFactory(course=course, order=1)
        second = DocumentLessonFactory(course=course, order=2)
        enrollment = EnrollmentFactory(course=course, status=EnrollmentStatus.ACTIVE)

        response = _client_for(enrollment.user).get(_stream_url(second, "document"))

        assert response.status_code == status.HTTP_403_FORBIDDEN
        assert "قفل" in response.data["message"]

    def test_document_stream_on_video_lesson_is_404(self) -> None:
        course = PublishedCourseFactory()
        lesson = LessonFactory(course=course, video_file=SimpleUploadedFile("lesson.mp4", b"video"))
        enrollment = EnrollmentFactory(course=course, status=EnrollmentStatus.ACTIVE)

        response = _client_for(enrollment.user).get(_stream_url(lesson, "document"))

        assert response.status_code == status.HTTP_404_NOT_FOUND


class TestLessonMediaStreamSignedToken:
    """مسیرِ امضاشده (بدون نشست) برای عناصرِ <video>/<embed> مرورگر."""

    def test_signed_token_streams_video_without_session(self) -> None:
        course = PublishedCourseFactory()
        lesson = LessonFactory(course=course, video_file=SimpleUploadedFile("lesson.mp4", b"video"))
        enrollment = EnrollmentFactory(course=course, status=EnrollmentStatus.ACTIVE)
        token = sign_lesson_media_token(lesson=lesson, user=enrollment.user, media_kind="video")

        response = APIClient().get(f"{_stream_url(lesson, 'video')}?t={token}")

        assert response.status_code == status.HTTP_200_OK
        assert response["Content-Type"] == "video/mp4"
        assert b"".join(response.streaming_content) == b"video"

    def test_media_access_url_end_to_end_unlocks_stream(self) -> None:
        """نشانی‌ای که access می‌دهد باید بدون نشست هم همان فایل را استریم کند."""
        course = PublishedCourseFactory()
        lesson = DocumentLessonFactory(course=course, order=1)
        enrollment = EnrollmentFactory(course=course, status=EnrollmentStatus.ACTIVE)
        payload = build_lesson_media_access(
            lesson=lesson, user=enrollment.user, media_kind="document"
        )

        response = APIClient().get(f"/api/v1/{payload['url']}")

        assert response.status_code == status.HTTP_200_OK
        assert b"".join(response.streaming_content) == b"%PDF-1.4 fixture"

    def test_tampered_or_wrong_kind_token_is_403(self) -> None:
        course = PublishedCourseFactory()
        lesson = LessonFactory(course=course, video_file=SimpleUploadedFile("lesson.mp4", b"video"))
        enrollment = EnrollmentFactory(course=course, status=EnrollmentStatus.ACTIVE)
        good = sign_lesson_media_token(lesson=lesson, user=enrollment.user, media_kind="video")

        tampered = APIClient().get(f"{_stream_url(lesson, 'video')}?t={good[:-2]}xx")
        wrong_kind = APIClient().get(f"{_stream_url(lesson, 'document')}?t={good}")

        assert tampered.status_code == status.HTTP_403_FORBIDDEN
        assert wrong_kind.status_code == status.HTTP_403_FORBIDDEN

    def test_token_of_another_lesson_does_not_unlock_this_one(self) -> None:
        course = PublishedCourseFactory()
        first = LessonFactory(course=course, order=1, video_file=SimpleUploadedFile("a.mp4", b"a"))
        second = LessonFactory(course=course, order=2, video_file=SimpleUploadedFile("b.mp4", b"b"))
        enrollment = EnrollmentFactory(course=course, status=EnrollmentStatus.ACTIVE)
        token_first = sign_lesson_media_token(
            lesson=first, user=enrollment.user, media_kind="video"
        )

        response = APIClient().get(f"{_stream_url(second, 'video')}?t={token_first}")

        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_anonymous_without_token_gets_401(self) -> None:
        lesson = LessonFactory(video_file=SimpleUploadedFile("lesson.mp4", b"video"))

        response = APIClient().get(_stream_url(lesson, "video"))

        assert response.status_code == status.HTTP_401_UNAUTHORIZED

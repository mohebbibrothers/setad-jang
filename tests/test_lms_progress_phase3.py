"""
LMS Phase 3 progress tracking tests.

این تست‌ها ثبت پیشرفت ویدئو را مثل یک سایت آموزشی حرفه‌ای validate می‌کنند:
- فقط کاربر ثبت‌نام‌کرده می‌تواند progress ثبت کند.
- watched_seconds monotonic است و با eventهای عقب‌تر کاهش پیدا نمی‌کند.
- last_position_seconds می‌تواند برای rewind جلو/عقب شود.
- درصد جلسه و دوره از source of truth محاسبه می‌شود.
- تکمیل همه جلسات enrollment را completed می‌کند.
- IDOR و audit dispatch پوشش داده می‌شود.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient

from apps.audit_logs import actions as audit_actions
from apps.lms.choices import EnrollmentStatus
from apps.lms.models import Enrollment, LessonProgress
from apps.lms.services import sync_course_counters
from tests.factories import UserFactory
from tests.factories.lms import LessonFactory, PublishedCourseFactory

pytestmark = pytest.mark.django_db

_AUDIT_TASK_PATH = "apps.audit_logs.tasks.create_audit_log_task"


def _client_for(user) -> APIClient:
    """Return authenticated APIClient for user."""
    client = APIClient()
    client.force_authenticate(user=user)
    return client


def _complete_profile(user) -> None:
    """Fill minimal LMS enrollment profile fields."""
    user.first_name = "Ali"
    user.last_name = "Mohammadi"
    user.save(update_fields=["first_name", "last_name"])
    user.profile.national_code = "0123456789"
    user.profile.save(update_fields=["national_code"])


def _enroll(user, course) -> Enrollment:
    """Create enrollment through API to exercise real route and service."""
    _complete_profile(user)
    response = _client_for(user).post(reverse("lms:course-enroll", kwargs={"slug": course.slug}))
    assert response.status_code == status.HTTP_201_CREATED, response.data
    return Enrollment.objects.get(user=user, course=course)


class TestLMSLessonProgressAPI:
    """Progress update API contract tests."""

    def test_enrolled_user_can_update_progress_and_audit_is_dispatched(self) -> None:
        course = PublishedCourseFactory()
        lesson = LessonFactory(course=course, order=1, duration_seconds=100)
        sync_course_counters(course=course)
        user = UserFactory()
        enrollment = _enroll(user, course)

        with patch(_AUDIT_TASK_PATH) as mock_task:
            mock_task.delay = MagicMock()
            response = _client_for(user).post(
                reverse("lms:lesson-progress-update", kwargs={"lesson_id": lesson.pk}),
                data={"watched_seconds": 30, "last_position_seconds": 25},
                format="json",
            )

        assert response.status_code == status.HTTP_200_OK
        assert response.data["data"]["watched_seconds"] == 30
        assert response.data["data"]["last_position_seconds"] == 25
        assert response.data["data"]["progress_percent"] == "30.00"

        enrollment.refresh_from_db()
        assert enrollment.watched_seconds == 30
        assert enrollment.progress_percent == 30
        assert enrollment.last_accessed_lesson_id == lesson.pk
        assert mock_task.delay.call_args.kwargs["action"] == audit_actions.LMS_PROGRESS_UPDATED

    def test_progress_is_monotonic_but_last_position_can_rewind(self) -> None:
        course = PublishedCourseFactory()
        lesson = LessonFactory(course=course, order=1, duration_seconds=100)
        sync_course_counters(course=course)
        user = UserFactory()
        _enroll(user, course)
        client = _client_for(user)

        client.post(
            reverse("lms:lesson-progress-update", kwargs={"lesson_id": lesson.pk}),
            data={"watched_seconds": 80, "last_position_seconds": 80},
            format="json",
        )
        response = client.post(
            reverse("lms:lesson-progress-update", kwargs={"lesson_id": lesson.pk}),
            data={"watched_seconds": 20, "last_position_seconds": 10},
            format="json",
        )

        assert response.status_code == status.HTTP_200_OK
        progress = LessonProgress.objects.get(lesson=lesson)
        assert progress.watched_seconds == 80
        assert progress.last_position_seconds == 10

    def test_course_progress_uses_total_course_duration_not_only_started_lessons(self) -> None:
        course = PublishedCourseFactory()
        lesson_a = LessonFactory(course=course, order=1, duration_seconds=100)
        LessonFactory(course=course, order=2, duration_seconds=100)
        sync_course_counters(course=course)
        user = UserFactory()
        enrollment = _enroll(user, course)

        response = _client_for(user).post(
            reverse("lms:lesson-progress-update", kwargs={"lesson_id": lesson_a.pk}),
            data={"watched_seconds": 100},
            format="json",
        )

        assert response.status_code == status.HTTP_200_OK
        enrollment.refresh_from_db()
        assert enrollment.watched_seconds == 100
        assert enrollment.total_seconds_snapshot == 200
        assert enrollment.progress_percent == 50
        assert enrollment.status == EnrollmentStatus.ACTIVE

    def test_enrollment_completes_when_all_lessons_are_completed(self) -> None:
        course = PublishedCourseFactory()
        lesson_a = LessonFactory(course=course, order=1, duration_seconds=100)
        lesson_b = LessonFactory(course=course, order=2, duration_seconds=100)
        sync_course_counters(course=course)
        user = UserFactory()
        enrollment = _enroll(user, course)
        client = _client_for(user)

        client.post(
            reverse("lms:lesson-progress-update", kwargs={"lesson_id": lesson_a.pk}),
            data={"watched_seconds": 90},
            format="json",
        )
        response = client.post(
            reverse("lms:lesson-progress-update", kwargs={"lesson_id": lesson_b.pk}),
            data={"watched_seconds": 90},
            format="json",
        )

        assert response.status_code == status.HTTP_200_OK
        enrollment.refresh_from_db()
        assert enrollment.status == EnrollmentStatus.COMPLETED
        assert enrollment.completed_at is not None
        assert enrollment.progress_percent == 90

    def test_user_cannot_update_progress_without_enrollment(self) -> None:
        course = PublishedCourseFactory()
        lesson = LessonFactory(course=course, order=1, duration_seconds=100)
        user = UserFactory()

        response = _client_for(user).post(
            reverse("lms:lesson-progress-update", kwargs={"lesson_id": lesson.pk}),
            data={"watched_seconds": 10},
            format="json",
        )

        assert response.status_code == status.HTTP_403_FORBIDDEN
        assert LessonProgress.objects.count() == 0

    def test_user_cannot_read_other_user_enrollment_detail(self) -> None:
        course = PublishedCourseFactory()
        owner = UserFactory()
        other = UserFactory()
        enrollment = _enroll(owner, course)

        response = _client_for(other).get(
            reverse("lms:user-enrollment-detail", kwargs={"enrollment_id": enrollment.pk})
        )

        assert response.status_code == status.HTTP_404_NOT_FOUND

    def test_enrollment_detail_includes_lesson_progress(self) -> None:
        course = PublishedCourseFactory()
        lesson = LessonFactory(course=course, order=1, duration_seconds=100)
        sync_course_counters(course=course)
        user = UserFactory()
        enrollment = _enroll(user, course)
        client = _client_for(user)
        client.post(
            reverse("lms:lesson-progress-update", kwargs={"lesson_id": lesson.pk}),
            data={"watched_seconds": 40},
            format="json",
        )

        response = client.get(reverse("lms:user-enrollment-detail", kwargs={"enrollment_id": enrollment.pk}))

        assert response.status_code == status.HTTP_200_OK
        assert len(response.data["data"]["lesson_progress"]) == 1
        assert response.data["data"]["lesson_progress"][0]["watched_seconds"] == 40

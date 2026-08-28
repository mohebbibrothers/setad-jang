"""
LMS Phase 8 final polish and performance contract tests.

این تست‌ها آخرین guardهای معماری LMS هستند:
- serializerهای پرترافیک بعد از selector مناسب نباید N+1 query تولید کنند.
- permission boundaryهای public/user/admin باید واضح بمانند.
- certificate PDF sample و renderer باید قابل اتکا باشند.
"""

from __future__ import annotations

from decimal import Decimal

import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APIClient

from apps.authentication.choices import Gender
from apps.lms import selectors
from apps.lms.certificate import build_certificate_pdf_bytes
from apps.lms.choices import DiscussionStatus
from apps.lms.models import Enrollment, LessonAnswer, LessonProgress, LessonQuestion
from apps.lms.serializers import (
    CourseDetailSerializer,
    EnrollmentDetailSerializer,
    LessonQuestionSerializer,
)
from tests.factories import AdminUserFactory, UserFactory
from tests.factories.lms import LessonFactory, PublishedCourseFactory

pytestmark = pytest.mark.django_db


def _client_for(user) -> APIClient:
    """Return authenticated APIClient."""
    client = APIClient()
    client.force_authenticate(user=user)
    return client


def _complete_profile(user) -> None:
    """Fill minimum LMS profile fields."""
    user.first_name = "Ali"
    user.last_name = "Mohammadi"
    user.save(update_fields=["first_name", "last_name"])
    user.profile.national_code = "0123456789"
    user.profile.gender = Gender.MALE
    user.profile.save(update_fields=["national_code", "gender"])


def _enroll(user, course) -> Enrollment:
    """Enroll a user in a published course through the API."""
    _complete_profile(user)
    response = _client_for(user).post(reverse("lms:course-enroll", kwargs={"slug": course.slug}))
    assert response.status_code == status.HTTP_201_CREATED, response.data
    return Enrollment.objects.get(user=user, course=course)


class TestLMSQueryPerformanceContracts:
    """N+1 regression tests for LMS selector/serializer contracts."""

    def test_course_detail_serializer_does_not_query_after_public_selector(self) -> None:
        course = PublishedCourseFactory(title="Performance Course")
        LessonFactory(course=course, order=1, title="Lesson 1")
        LessonFactory(course=course, order=2, title="Lesson 2")

        prefetched = selectors.get_public_course_by_slug(course.slug)

        with CaptureQueriesContext(connection) as captured:
            data = CourseDetailSerializer(prefetched).data

        assert data["id"] == course.pk
        assert len(data["lessons"]) == 2
        assert len(captured) == 0

    def test_enrollment_detail_serializer_does_not_query_after_user_selector(self) -> None:
        course = PublishedCourseFactory(title="Progress Course")
        lesson = LessonFactory(course=course, order=1, duration_seconds=100)
        user = UserFactory()
        enrollment = _enroll(user, course)
        LessonProgress.objects.create(
            enrollment=enrollment,
            lesson=lesson,
            watched_seconds=50,
            duration_seconds_snapshot=100,
            progress_percent=Decimal("50.00"),
        )

        prefetched = selectors.get_user_enrollment_by_id(
            user_id=user.pk, enrollment_id=enrollment.pk
        )

        with CaptureQueriesContext(connection) as captured:
            data = EnrollmentDetailSerializer(prefetched).data

        assert data["id"] == enrollment.pk
        assert len(data["lesson_progress"]) == 1
        assert len(captured) == 0

    def test_lesson_question_serializer_does_not_query_after_question_selector(self) -> None:
        course = PublishedCourseFactory(title="Q&A Performance")
        lesson = LessonFactory(course=course, order=1)
        user = UserFactory()
        _enroll(user, course)
        question = LessonQuestion.objects.create(
            lesson=lesson,
            user=user,
            title="Question",
            body="A meaningful question body",
            status=DiscussionStatus.VISIBLE,
        )
        LessonAnswer.objects.create(question=question, user=user, body="A meaningful answer")

        questions = list(selectors.get_lesson_questions(lesson_id=lesson.pk))

        with CaptureQueriesContext(connection) as captured:
            data = LessonQuestionSerializer(questions, many=True).data

        assert len(data) == 1
        assert len(data[0]["answers"]) == 1
        assert len(captured) == 0


class TestLMSPermissionSmokeContracts:
    """Permission boundary smoke tests for LMS user/admin APIs."""

    def test_anonymous_user_cannot_enroll(self) -> None:
        course = PublishedCourseFactory()

        response = APIClient().post(reverse("lms:course-enroll", kwargs={"slug": course.slug}))

        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    def test_regular_user_cannot_access_admin_course_list(self) -> None:
        user = UserFactory(email="regular-lms@test.local")

        response = _client_for(user).get(reverse("lms:admin-course-list-create"))

        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_admin_can_access_admin_course_list(self) -> None:
        admin = AdminUserFactory(email="admin-lms@test.local")

        response = _client_for(admin).get(reverse("lms:admin-course-list-create"))

        assert response.status_code == status.HTTP_200_OK


class TestLMSCertificateAssetContract:
    """Certificate rendering and static asset smoke tests."""

    def test_certificate_pdf_sample_is_tracked_and_non_empty(self) -> None:
        from pathlib import Path

        sample = Path("docs/assets/lms/basat_mardom_certificate_sample.pdf")
        logo = Path("static/lms/certificates/basat_mardom_logo.jpg")

        assert sample.exists()
        assert sample.stat().st_size > 10_000
        assert logo.exists()
        assert logo.stat().st_size > 10_000

    def test_certificate_pdf_renderer_outputs_pdf_bytes(self) -> None:
        from types import SimpleNamespace

        certificate = SimpleNamespace(
            gender_snapshot=Gender.MALE,
            full_name_snapshot="علی محمدی",
            national_code_snapshot="0250915308",
            course_title_snapshot="آموزش پایتون",
            instructor_name_snapshot="استاد بعثت",
            score_out_of_20=Decimal("18.50"),
            certificate_code="BASAT-TEST-0001",
            verification_slug="basat-test-0001",
            issued_at=timezone.now(),
        )

        payload = build_certificate_pdf_bytes(certificate)

        assert payload.startswith(b"%PDF")
        assert len(payload) > 10_000

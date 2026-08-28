"""
LMS Phase 2 API tests.

این تست‌ها public catalog، admin CRUD/publish/report و ثبت‌نام user را پوشش
می‌دهند تا foundation مدل‌ها به API قابل استفاده و envelope-compatible تبدیل شود.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient

from apps.audit_logs import actions as audit_actions
from apps.lms.choices import CourseStatus, EnrollmentStatus
from apps.lms.models import Enrollment, Lesson, LMSCategory
from tests.factories import AdminUserFactory, UserFactory
from tests.factories.lms import CourseFactory, LessonFactory, PublishedCourseFactory

pytestmark = pytest.mark.django_db

_AUDIT_TASK_PATH = "apps.audit_logs.tasks.create_audit_log_task"


def _auth_client(user) -> APIClient:
    """Return an APIClient authenticated as user."""
    client = APIClient()
    client.force_authenticate(user=user)
    return client


def _complete_minimum_lms_profile(user) -> None:
    """Fill profile fields required for LMS enrollment."""
    user.first_name = "Ali"
    user.last_name = "Mohammadi"
    user.save(update_fields=["first_name", "last_name"])
    user.profile.national_code = "0123456789"
    user.profile.save(update_fields=["national_code"])


class TestLMSPublicCatalogAPI:
    """Public course/category catalog API tests."""

    def test_public_course_list_returns_only_published_courses(self) -> None:
        published = PublishedCourseFactory(title="دوره منتشرشده")
        CourseFactory(title="دوره پیش‌نویس")

        response = APIClient().get(reverse("lms:course-list"))

        assert response.status_code == status.HTTP_200_OK
        titles = [item["title"] for item in response.data["data"]["results"]]
        assert titles == [published.title]

    def test_public_course_detail_includes_ordered_lessons(self) -> None:
        course = PublishedCourseFactory(title="دوره با جلسه")
        first = LessonFactory(course=course, order=1, title="جلسه اول")
        second = LessonFactory(course=course, order=2, title="جلسه دوم")

        response = APIClient().get(reverse("lms:course-detail", kwargs={"slug": course.slug}))

        assert response.status_code == status.HTTP_200_OK
        assert response.data["data"]["title"] == course.title
        assert [lesson["id"] for lesson in response.data["data"]["lessons"]] == [
            first.pk,
            second.pk,
        ]

    def test_public_category_list_uses_dynamic_admin_categories(self) -> None:
        category = LMSCategory.objects.create(title="هوش مصنوعی", order=1)
        LMSCategory.objects.create(title="غیرفعال", is_active=False, order=2)

        response = APIClient().get(reverse("lms:category-list"))

        assert response.status_code == status.HTTP_200_OK
        assert [item["title"] for item in response.data["data"]] == [category.title]


class TestLMSAdminCourseManagementAPI:
    """Admin management APIs for categories, courses, lessons, and reports."""

    def test_admin_can_create_course_publish_and_add_lesson(self) -> None:
        admin = AdminUserFactory()
        client = _auth_client(admin)
        category = LMSCategory.objects.create(title="برنامه‌نویسی")

        with patch(_AUDIT_TASK_PATH) as mock_task:
            mock_task.delay = MagicMock()
            create_response = client.post(
                reverse("lms:admin-course-list-create"),
                data={
                    "category_id": category.pk,
                    "title": "آموزش Django حرفه‌ای",
                    "description": "توضیحات کامل دوره",
                    "instructor_name": "استاد جنگو",
                    "short_description": "شروع سریع Django",
                },
                format="json",
            )

        assert create_response.status_code == status.HTTP_201_CREATED
        course_id = create_response.data["data"]["id"]
        assert mock_task.delay.call_args.kwargs["action"] == audit_actions.LMS_COURSE_CREATED

        publish_response = client.post(
            reverse("lms:admin-course-publish", kwargs={"course_id": course_id})
        )
        assert publish_response.status_code == status.HTTP_200_OK
        assert publish_response.data["data"]["status"] == CourseStatus.PUBLISHED

        lesson_response = client.post(
            reverse("lms:admin-lesson-list-create", kwargs={"course_id": course_id}),
            data={
                "title": "جلسه اول",
                "order": 1,
                "duration_seconds": 900,
                "video_url": "https://example.com/django-1.mp4",
            },
            format="json",
        )
        assert lesson_response.status_code == status.HTTP_201_CREATED
        assert Lesson.objects.filter(course_id=course_id).count() == 1

    def test_admin_course_report_returns_participants_and_graduates_summary(self) -> None:
        admin = AdminUserFactory()
        course = PublishedCourseFactory()
        user = UserFactory(email="learner@example.com")
        _complete_minimum_lms_profile(user)
        Enrollment.objects.create(user=user, course=course, status=EnrollmentStatus.ACTIVE)

        response = _auth_client(admin).get(
            reverse("lms:admin-course-report", kwargs={"course_id": course.pk})
        )

        assert response.status_code == status.HTTP_200_OK
        assert response.data["data"]["summary"]["participants_count"] == 1
        assert response.data["data"]["summary"]["graduates_count"] == 0
        assert response.data["data"]["enrollments"][0]["user_email"] == "learner@example.com"


class TestLMSUserEnrollmentAPI:
    """User enrollment API tests."""

    def test_user_can_enroll_with_minimum_profile_and_second_call_is_idempotent(self) -> None:
        user = UserFactory(email="student@example.com")
        _complete_minimum_lms_profile(user)
        course = PublishedCourseFactory()
        client = _auth_client(user)

        with patch(_AUDIT_TASK_PATH) as mock_task:
            mock_task.delay = MagicMock()
            first = client.post(reverse("lms:course-enroll", kwargs={"slug": course.slug}))
            second = client.post(reverse("lms:course-enroll", kwargs={"slug": course.slug}))

        assert first.status_code == status.HTTP_201_CREATED
        assert second.status_code == status.HTTP_200_OK
        assert Enrollment.objects.filter(user=user, course=course).count() == 1
        assert (
            mock_task.delay.call_args_list[0].kwargs["action"]
            == audit_actions.LMS_ENROLLMENT_CREATED
        )

    def test_user_without_minimum_profile_cannot_enroll(self) -> None:
        user = UserFactory(first_name="", last_name="")
        course = PublishedCourseFactory()

        response = _auth_client(user).post(
            reverse("lms:course-enroll", kwargs={"slug": course.slug})
        )

        assert response.status_code == status.HTTP_403_FORBIDDEN
        assert Enrollment.objects.count() == 0

    def test_user_enrollment_list_returns_owned_enrollments(self) -> None:
        user = UserFactory()
        _complete_minimum_lms_profile(user)
        course = PublishedCourseFactory()
        Enrollment.objects.create(user=user, course=course, status=EnrollmentStatus.ACTIVE)
        Enrollment.objects.create(
            user=UserFactory(), course=PublishedCourseFactory(), status=EnrollmentStatus.ACTIVE
        )

        response = _auth_client(user).get(reverse("lms:user-enrollment-list"))

        assert response.status_code == status.HTTP_200_OK
        assert response.data["data"]["count"] == 1
        assert response.data["data"]["results"][0]["course"]["id"] == course.pk

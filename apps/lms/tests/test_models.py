"""
Model tests for LMS Phase 1.

These tests verify the foundational domain model contracts before API/service
phases are added: dynamic admin-managed categories, slug generation, constraints,
quiz/certificate structures, and admin read-only safety for evidence records.
"""

from __future__ import annotations

import pytest
from django.contrib.admin.sites import AdminSite
from django.db import IntegrityError, transaction
from rest_framework.test import APIClient

from apps.lms.admin import CertificateAdmin, EnrollmentAdmin, QuizAnswerAdmin, QuizAttemptAdmin
from apps.lms.choices import CourseStatus, DiscussionReportStatus
from apps.lms.models import Certificate, Enrollment, LessonDiscussionReport, QuizAnswer, QuizAttempt
from tests.factories import (
    CourseFactory,
    EnrollmentFactory,
    LessonFactory,
    LMSCategoryFactory,
    PublishedCourseFactory,
    QuizAttemptFactory,
    QuizFactory,
    QuizOptionFactory,
    QuizQuestionFactory,
    UserFactory,
)

pytestmark = pytest.mark.django_db


class TestLMSCategoryAndCourseModels:
    """Foundational category/course model contracts."""

    def test_categories_are_dynamic_admin_managed_records(self) -> None:
        category = LMSCategoryFactory(title="برنامه‌نویسی پیشرفته")

        assert category.pk is not None
        assert category.slug
        assert category.is_active is True

    def test_course_generates_unique_slug_and_detects_published_state(self) -> None:
        category = LMSCategoryFactory(title="طراحی")
        first = PublishedCourseFactory(category=category, title="آموزش پایتون")
        second = CourseFactory(category=category, title="آموزش پایتون")

        assert first.slug == "آموزش-پایتون"
        assert second.slug.startswith("آموزش-پایتون-")
        assert first.is_published is True
        assert second.status == CourseStatus.DRAFT
        assert second.is_published is False

    def test_lesson_order_is_unique_per_course(self) -> None:
        course = CourseFactory()
        LessonFactory(course=course, order=1, title="جلسه اول")

        with pytest.raises(IntegrityError), transaction.atomic():
            LessonFactory(course=course, order=1, title="جلسه تکراری")


class TestEnrollmentAndProgressModels:
    """Enrollment/progress constraints."""

    def test_user_can_enroll_only_once_per_course(self) -> None:
        course = PublishedCourseFactory()
        user = UserFactory()
        EnrollmentFactory(course=course, user=user)

        with pytest.raises(IntegrityError), transaction.atomic():
            EnrollmentFactory(course=course, user=user)


class TestDiscussionReportModel:
    """Q&A moderation model constraints."""

    def test_discussion_report_requires_exactly_one_target(self) -> None:
        reporter = UserFactory()

        with pytest.raises(IntegrityError), transaction.atomic():
            LessonDiscussionReport.objects.create(
                reported_by=reporter,
                reason="spam",
                status=DiscussionReportStatus.PENDING,
            )


class TestQuizFoundationModels:
    """Quiz engine foundational constraints."""

    def test_quiz_question_and_option_order_are_unique_per_parent(self) -> None:
        quiz = QuizFactory()
        question = QuizQuestionFactory(quiz=quiz, order=1)

        with pytest.raises(IntegrityError), transaction.atomic():
            QuizQuestionFactory(quiz=quiz, order=1)

        QuizOptionFactory(question=question, order=1, is_correct=True)
        with pytest.raises(IntegrityError), transaction.atomic():
            QuizOptionFactory(question=question, order=1)

    def test_quiz_attempt_number_unique_per_user_and_quiz(self) -> None:
        attempt = QuizAttemptFactory(attempt_number=1)

        with pytest.raises(IntegrityError), transaction.atomic():
            QuizAttemptFactory(
                quiz=attempt.quiz,
                user=attempt.user,
                enrollment=attempt.enrollment,
                attempt_number=1,
            )


class TestLMSAdminSafety:
    """Admin safety for service-controlled evidence records."""

    def test_read_only_admins_block_direct_mutation_for_sensitive_records(self) -> None:
        site = AdminSite()
        request = APIClient().request().wsgi_request

        assert EnrollmentAdmin(Enrollment, site).has_add_permission(request) is False
        assert EnrollmentAdmin(Enrollment, site).has_change_permission(request) is False
        assert EnrollmentAdmin(Enrollment, site).has_delete_permission(request) is False

        assert QuizAttemptAdmin(QuizAttempt, site).has_add_permission(request) is False
        assert QuizAttemptAdmin(QuizAttempt, site).has_change_permission(request) is False
        assert QuizAttemptAdmin(QuizAttempt, site).has_delete_permission(request) is False

        assert QuizAnswerAdmin(QuizAnswer, site).has_add_permission(request) is False
        assert CertificateAdmin(Certificate, site).has_add_permission(request) is False

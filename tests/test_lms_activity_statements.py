"""LMS C4 xAPI-like learning activity statement tests."""

from __future__ import annotations

import pytest
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken

from apps.lms.choices import EnrollmentStatus, LearningStatementVerb, QuizAttemptStatus, QuizStatus
from apps.lms.models import LearningActivityStatement, QuizAttempt
from apps.lms.services import (
    record_learning_activity_statement,
    start_quiz_attempt,
    submit_quiz_attempt,
    update_lesson_progress,
)
from tests.factories.auth import AdminUserFactory, UserFactory
from tests.factories.lms import (
    EnrollmentFactory,
    LessonFactory,
    PublishedCourseFactory,
    QuizFactory,
    QuizOptionFactory,
    QuizQuestionFactory,
)

pytestmark = pytest.mark.django_db


def _client(user) -> APIClient:
    """Return JWT-authenticated API client."""
    client = APIClient()
    refresh = RefreshToken.for_user(user)
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {refresh.access_token!s}")
    return client


def _published_quiz_for_course(course):
    """Create a minimal published quiz with two questions and correct options."""
    quiz = QuizFactory(course=course, status=QuizStatus.PUBLISHED)
    for order in (1, 2):
        question = QuizQuestionFactory(quiz=quiz, order=order, weight=1)
        QuizOptionFactory(question=question, order=1, is_correct=True)
        QuizOptionFactory(question=question, order=2, is_correct=False)
    return quiz


def test_record_learning_statement_is_idempotent() -> None:
    """Statement recording should honor idempotency keys."""
    user = UserFactory()
    course = PublishedCourseFactory()

    first = record_learning_activity_statement(
        actor=user,
        course=course,
        verb=LearningStatementVerb.INITIALIZED,
        object_type="course",
        object_id=course.pk,
        idempotency_key="statement-idem-1",
    )
    second = record_learning_activity_statement(
        actor=user,
        course=course,
        verb=LearningStatementVerb.INITIALIZED,
        object_type="course",
        object_id=course.pk,
        idempotency_key="statement-idem-1",
    )

    assert first.pk == second.pk
    assert LearningActivityStatement.objects.count() == 1


def test_lesson_progress_records_progressed_and_completed_statement() -> None:
    """Lesson progress updates should emit xAPI-like progress/completion statements."""
    user = UserFactory()
    course = PublishedCourseFactory()
    lesson = LessonFactory(course=course, duration_seconds=100)
    enrollment = EnrollmentFactory(user=user, course=course, status=EnrollmentStatus.ACTIVE)

    update_lesson_progress(enrollment=enrollment, lesson=lesson, watched_seconds=30)
    update_lesson_progress(enrollment=enrollment, lesson=lesson, watched_seconds=95)

    verbs = list(
        LearningActivityStatement.objects.filter(actor=user, lesson=lesson).values_list(
            "verb", flat=True
        )
    )
    assert LearningStatementVerb.PROGRESSED in verbs
    assert LearningStatementVerb.COMPLETED in verbs


def test_quiz_start_submit_and_certificate_issue_emit_statements() -> None:
    """Quiz lifecycle should emit initialized, passed and certificate-issued statements."""
    user = UserFactory(first_name="علی", last_name="آموزگار")
    user.profile.national_code = "0012345678"
    user.profile.save(update_fields=["national_code", "updated_at"])
    course = PublishedCourseFactory()
    enrollment = EnrollmentFactory(user=user, course=course, status=EnrollmentStatus.ACTIVE)
    quiz = _published_quiz_for_course(course)

    attempt, created = start_quiz_attempt(quiz=quiz, user=user)
    answers = [
        {"question_id": question.pk, "selected_option_id": question.options.get(is_correct=True).pk}
        for question in quiz.questions.order_by("order")
    ]
    submitted = submit_quiz_attempt(attempt=attempt, answers=answers)

    assert created is True
    assert submitted.status == QuizAttemptStatus.PASSED
    verbs = set(
        LearningActivityStatement.objects.filter(actor=user, course=course).values_list(
            "verb", flat=True
        )
    )
    assert LearningStatementVerb.INITIALIZED in verbs
    assert LearningStatementVerb.PASSED in verbs
    assert LearningStatementVerb.CERTIFICATE_ISSUED in verbs
    assert QuizAttempt.objects.get(pk=attempt.pk).activity_statements.count() >= 2
    enrollment.refresh_from_db()
    assert enrollment.status == EnrollmentStatus.COMPLETED


def test_admin_learning_activity_statement_list_endpoint() -> None:
    """Admin endpoint should expose paginated learning activity statements."""
    admin = AdminUserFactory()
    user = UserFactory()
    course = PublishedCourseFactory()
    statement = record_learning_activity_statement(
        actor=user,
        course=course,
        verb=LearningStatementVerb.INITIALIZED,
        object_type="course",
        object_id=course.pk,
    )

    response = _client(admin).get(
        reverse("lms:admin-activity-statement-list"),
        data={"verb": LearningStatementVerb.INITIALIZED},
    )

    assert response.status_code == status.HTTP_200_OK
    assert response.data["success"] is True
    assert response.data["data"]["count"] == 1
    assert response.data["data"]["results"][0]["statement_id"] == str(statement.statement_id)

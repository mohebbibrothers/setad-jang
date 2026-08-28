"""
LMS Phase 5 professional quiz engine tests.

این تست‌ها تضمین می‌کنند فقط ادمین quiz/questions/options را می‌سازد، تلاش آزمون
snapshot/randomized دارد، نمره وزن‌دار از ۲۰ محاسبه می‌شود، پاسخ صحیح قبل از
قبولی leak نمی‌شود، محدودیت تلاش/تأخیر ۱۴ روزه و unlock ادمین enforce می‌شود.
"""

from __future__ import annotations

from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest
from django.urls import reverse
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APIClient

from apps.audit_logs import actions as audit_actions
from apps.lms.choices import QuizAttemptStatus, QuizStatus
from apps.lms.models import Enrollment, QuizAttempt, QuizOption, QuizQuestion
from apps.lms.services import publish_quiz, sync_course_counters
from tests.factories import AdminUserFactory, UserFactory
from tests.factories.lms import LessonFactory, PublishedCourseFactory, QuizFactory

pytestmark = pytest.mark.django_db

_AUDIT_TASK_PATH = "apps.audit_logs.tasks.create_audit_log_task"


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
    user.profile.save(update_fields=["national_code"])


def _enroll(user, course) -> Enrollment:
    """Enroll user through API."""
    _complete_profile(user)
    response = _client_for(user).post(reverse("lms:course-enroll", kwargs={"slug": course.slug}))
    assert response.status_code == status.HTTP_201_CREATED, response.data
    return Enrollment.objects.get(user=user, course=course)


def _build_publishable_quiz(course, *, passing_score=Decimal("12.00")):
    """Create a published quiz with two weighted questions and answer options."""
    quiz = QuizFactory(
        course=course,
        title="آزمون حرفه‌ای",
        passing_score=passing_score,
        status=QuizStatus.DRAFT,
        shuffle_questions=True,
        shuffle_options=True,
        max_attempts=2,
        retake_delay_days=14,
    )
    q1 = QuizQuestion.objects.create(quiz=quiz, text="۲ + ۲؟", order=1, weight=Decimal("1.00"))
    q2 = QuizQuestion.objects.create(quiz=quiz, text="۳ + ۳؟", order=2, weight=Decimal("3.00"))
    q1_wrong = QuizOption.objects.create(question=q1, text="۳", order=1, is_correct=False)
    q1_correct = QuizOption.objects.create(question=q1, text="۴", order=2, is_correct=True)
    q2_wrong = QuizOption.objects.create(question=q2, text="۵", order=1, is_correct=False)
    q2_correct = QuizOption.objects.create(question=q2, text="۶", order=2, is_correct=True)
    publish_quiz(quiz=quiz)
    return (
        quiz,
        {q1.pk: q1_correct.pk, q2.pk: q2_correct.pk},
        {q1.pk: q1_wrong.pk, q2.pk: q2_wrong.pk},
    )


class TestLMSAdminQuizBuilder:
    """Admin-only quiz builder tests."""

    def test_admin_can_create_quiz_question_option_and_publish(self) -> None:
        admin = AdminUserFactory()
        course = PublishedCourseFactory()
        client = _client_for(admin)

        with patch(_AUDIT_TASK_PATH) as mock_task:
            mock_task.delay = MagicMock()
            quiz_response = client.post(
                reverse("lms:admin-quiz-detail-create", kwargs={"course_id": course.pk}),
                data={"title": "آزمون نهایی", "passing_score": "12.00", "time_limit_minutes": 20},
                format="json",
            )

        assert quiz_response.status_code == status.HTTP_201_CREATED
        question_response = client.post(
            reverse("lms:admin-quiz-question-create", kwargs={"course_id": course.pk}),
            data={"text": "سؤال اول", "order": 1, "weight": "2.00"},
            format="json",
        )
        assert question_response.status_code == status.HTTP_201_CREATED
        question_id = question_response.data["data"]["id"]
        client.post(
            reverse("lms:admin-quiz-option-create", kwargs={"question_id": question_id}),
            data={"text": "غلط", "order": 1},
            format="json",
        )
        client.post(
            reverse("lms:admin-quiz-option-create", kwargs={"question_id": question_id}),
            data={"text": "درست", "order": 2, "is_correct": True},
            format="json",
        )

        publish_response = client.post(
            reverse("lms:admin-quiz-publish", kwargs={"course_id": course.pk})
        )

        assert publish_response.status_code == status.HTTP_200_OK
        assert publish_response.data["data"]["status"] == QuizStatus.PUBLISHED
        assert mock_task.delay.call_args.kwargs["action"] == audit_actions.LMS_QUIZ_CREATED

    def test_regular_user_cannot_create_quiz_question(self) -> None:
        user = UserFactory()
        course = PublishedCourseFactory()
        QuizFactory(course=course)

        response = _client_for(user).post(
            reverse("lms:admin-quiz-question-create", kwargs={"course_id": course.pk}),
            data={"text": "نباید ساخته شود", "order": 1},
            format="json",
        )

        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_publish_rejects_question_without_exactly_one_correct_option(self) -> None:
        admin = AdminUserFactory()
        course = PublishedCourseFactory()
        quiz = QuizFactory(course=course, status=QuizStatus.DRAFT)
        question = QuizQuestion.objects.create(quiz=quiz, text="بی‌پاسخ", order=1)
        QuizOption.objects.create(question=question, text="الف", order=1, is_correct=False)
        QuizOption.objects.create(question=question, text="ب", order=2, is_correct=False)

        response = _client_for(admin).post(
            reverse("lms:admin-quiz-publish", kwargs={"course_id": course.pk})
        )

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        quiz.refresh_from_db()
        assert quiz.status == QuizStatus.DRAFT


class TestLMSQuizAttemptFlow:
    """User quiz start/submit and anti-leak tests."""

    def test_enrolled_user_can_start_attempt_with_question_snapshot(self) -> None:
        course = PublishedCourseFactory()
        LessonFactory(course=course, order=1, duration_seconds=100)
        sync_course_counters(course=course)
        user = UserFactory()
        _enroll(user, course)
        quiz, _correct, _wrong = _build_publishable_quiz(course)

        with patch(_AUDIT_TASK_PATH) as mock_task:
            mock_task.delay = MagicMock()
            response = _client_for(user).post(
                reverse("lms:quiz-attempt-start", kwargs={"slug": course.slug})
            )

        assert response.status_code == status.HTTP_201_CREATED
        attempt = QuizAttempt.objects.get(pk=response.data["data"]["id"])
        assert attempt.quiz_id == quiz.pk
        assert len(attempt.question_snapshot) == 2
        assert set(attempt.option_order_snapshot) == {str(qid) for qid in attempt.question_snapshot}
        serialized = str(response.data)
        assert "is_correct" not in serialized
        assert mock_task.delay.call_args.kwargs["action"] == audit_actions.LMS_QUIZ_ATTEMPT_STARTED

    def test_submit_failed_attempt_hides_correct_answers(self) -> None:
        course = PublishedCourseFactory()
        user = UserFactory()
        _enroll(user, course)
        _quiz, _correct, wrong = _build_publishable_quiz(course, passing_score=Decimal("20.00"))
        start = _client_for(user).post(
            reverse("lms:quiz-attempt-start", kwargs={"slug": course.slug})
        )
        attempt_id = start.data["data"]["id"]
        answers = [
            {"question_id": question_id, "selected_option_id": option_id}
            for question_id, option_id in wrong.items()
        ]

        response = _client_for(user).post(
            reverse("lms:quiz-attempt-submit", kwargs={"attempt_id": attempt_id}),
            data={"answers": answers},
            format="json",
        )

        assert response.status_code == status.HTTP_200_OK
        assert response.data["data"]["status"] == QuizAttemptStatus.FAILED
        response_text = str(response.data)
        assert "correct_option_id" not in response_text
        assert "explanation" not in response_text

    def test_submit_passed_attempt_reveals_correct_answers(self) -> None:
        course = PublishedCourseFactory()
        user = UserFactory()
        _enroll(user, course)
        _quiz, correct, _wrong = _build_publishable_quiz(course, passing_score=Decimal("12.00"))
        start = _client_for(user).post(
            reverse("lms:quiz-attempt-start", kwargs={"slug": course.slug})
        )
        attempt_id = start.data["data"]["id"]
        answers = [
            {"question_id": question_id, "selected_option_id": option_id}
            for question_id, option_id in correct.items()
        ]

        response = _client_for(user).post(
            reverse("lms:quiz-attempt-submit", kwargs={"attempt_id": attempt_id}),
            data={"answers": answers},
            format="json",
        )

        assert response.status_code == status.HTTP_200_OK
        assert response.data["data"]["status"] == QuizAttemptStatus.PASSED
        assert "correct_option_id" in str(response.data)
        assert response.data["data"]["score_out_of_20"] == "20.00"

    def test_second_attempt_is_blocked_until_retake_delay(self) -> None:
        course = PublishedCourseFactory()
        user = UserFactory()
        _enroll(user, course)
        _quiz, _correct, wrong = _build_publishable_quiz(course, passing_score=Decimal("20.00"))
        client = _client_for(user)
        start = client.post(reverse("lms:quiz-attempt-start", kwargs={"slug": course.slug}))
        attempt_id = start.data["data"]["id"]
        client.post(
            reverse("lms:quiz-attempt-submit", kwargs={"attempt_id": attempt_id}),
            data={
                "answers": [{"question_id": q, "selected_option_id": o} for q, o in wrong.items()]
            },
            format="json",
        )

        response = client.post(reverse("lms:quiz-attempt-start", kwargs={"slug": course.slug}))

        assert response.status_code == status.HTTP_403_FORBIDDEN
        assert "هنوز فعال نشده" in response.data["message"]

    def test_admin_unlock_allows_extra_attempt(self) -> None:
        admin = AdminUserFactory()
        course = PublishedCourseFactory()
        user = UserFactory()
        _enroll(user, course)
        _quiz, _correct, wrong = _build_publishable_quiz(course, passing_score=Decimal("20.00"))
        client = _client_for(user)
        for _ in range(2):
            start = client.post(reverse("lms:quiz-attempt-start", kwargs={"slug": course.slug}))
            attempt_id = start.data["data"]["id"]
            attempt = QuizAttempt.objects.get(pk=attempt_id)
            attempt.submitted_at = timezone.now() - timezone.timedelta(days=15)
            attempt.save(update_fields=["submitted_at"])
            client.post(
                reverse("lms:quiz-attempt-submit", kwargs={"attempt_id": attempt_id}),
                data={
                    "answers": [
                        {"question_id": q, "selected_option_id": o} for q, o in wrong.items()
                    ]
                },
                format="json",
            )
            QuizAttempt.objects.filter(pk=attempt_id).update(
                submitted_at=timezone.now() - timezone.timedelta(days=15)
            )

        locked = client.post(reverse("lms:quiz-attempt-start", kwargs={"slug": course.slug}))
        assert locked.status_code == status.HTTP_403_FORBIDDEN

        unlock_response = _client_for(admin).post(
            reverse("lms:admin-quiz-unlock", kwargs={"course_id": course.pk}),
            data={"user_id": user.pk, "reason": "فرصت مجدد آموزشی", "extra_attempts": 1},
            format="json",
        )
        assert unlock_response.status_code == status.HTTP_201_CREATED

        unlocked_start = client.post(
            reverse("lms:quiz-attempt-start", kwargs={"slug": course.slug})
        )
        assert unlocked_start.status_code == status.HTTP_201_CREATED
        assert unlocked_start.data["data"]["attempt_number"] == 3

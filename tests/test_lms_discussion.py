"""
LMS Phase 4 lesson Q&A tests.

این تست‌ها پرسش‌وپاسخ حرفه‌ای جلسات را پوشش می‌دهند:
- فقط ثبت‌نام‌شده‌ها می‌توانند سؤال/پاسخ ثبت کنند.
- سؤال‌ها بلافاصله visible می‌شوند.
- پاسخ پذیرفته‌شده، سؤال را answered می‌کند.
- report/moderation/admin review با audit و IDOR کنترل می‌شود.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient

from apps.audit_logs import actions as audit_actions
from apps.lms.choices import DiscussionReportStatus, DiscussionStatus
from apps.lms.models import Enrollment, LessonAnswer, LessonDiscussionReport, LessonQuestion
from tests.factories import AdminUserFactory, UserFactory
from tests.factories.lms import LessonFactory, PublishedCourseFactory

pytestmark = pytest.mark.django_db

_AUDIT_TASK_PATH = "apps.audit_logs.tasks.create_audit_log_task"


def _client_for(user) -> APIClient:
    """Return authenticated client."""
    client = APIClient()
    client.force_authenticate(user=user)
    return client


def _complete_profile(user) -> None:
    """Fill minimum enrollment profile."""
    user.first_name = "Ali"
    user.last_name = "Mohammadi"
    user.save(update_fields=["first_name", "last_name"])
    user.profile.national_code = "0123456789"
    user.profile.save(update_fields=["national_code"])


def _enroll(user, course) -> Enrollment:
    """Enroll user in course through API."""
    _complete_profile(user)
    response = _client_for(user).post(reverse("lms:course-enroll", kwargs={"slug": course.slug}))
    assert response.status_code == status.HTTP_201_CREATED, response.data
    return Enrollment.objects.get(user=user, course=course)


class TestLMSLessonQuestions:
    """Question creation/listing tests."""

    def test_enrolled_user_can_create_question_and_audit_is_dispatched(self) -> None:
        course = PublishedCourseFactory()
        lesson = LessonFactory(course=course, order=1)
        user = UserFactory()
        _enroll(user, course)

        with patch(_AUDIT_TASK_PATH) as mock_task:
            mock_task.delay = MagicMock()
            response = _client_for(user).post(
                reverse("lms:lesson-question-list-create", kwargs={"lesson_id": lesson.pk}),
                data={"title": "سؤال مهم", "body": "چطور این مفهوم را بهتر تمرین کنم؟"},
                format="json",
            )

        assert response.status_code == status.HTTP_201_CREATED
        question = LessonQuestion.objects.get(pk=response.data["data"]["id"])
        assert question.status == DiscussionStatus.VISIBLE
        assert question.user_id == user.pk
        assert mock_task.delay.call_args.kwargs["action"] == audit_actions.LMS_QUESTION_CREATED

    def test_non_enrolled_user_cannot_create_question(self) -> None:
        course = PublishedCourseFactory()
        lesson = LessonFactory(course=course, order=1)
        user = UserFactory()

        response = _client_for(user).post(
            reverse("lms:lesson-question-list-create", kwargs={"lesson_id": lesson.pk}),
            data={"title": "سؤال مهم", "body": "متن سؤال معتبر برای جلسه"},
            format="json",
        )

        assert response.status_code == status.HTTP_403_FORBIDDEN
        assert LessonQuestion.objects.count() == 0

    def test_enrolled_user_can_list_visible_questions_with_answers(self) -> None:
        course = PublishedCourseFactory()
        lesson = LessonFactory(course=course, order=1)
        user = UserFactory()
        _enroll(user, course)
        question = LessonQuestion.objects.create(
            lesson=lesson,
            user=user,
            title="سؤال",
            body="متن سؤال معتبر",
        )
        LessonAnswer.objects.create(question=question, user=user, body="پاسخ معتبر")

        response = _client_for(user).get(
            reverse("lms:lesson-question-list-create", kwargs={"lesson_id": lesson.pk})
        )

        assert response.status_code == status.HTTP_200_OK
        assert response.data["data"]["count"] == 1
        assert response.data["data"]["results"][0]["answers"][0]["body"] == "پاسخ معتبر"


class TestLMSLessonAnswersAndAccept:
    """Answer creation and accepted answer tests."""

    def test_enrolled_user_can_answer_question(self) -> None:
        course = PublishedCourseFactory()
        lesson = LessonFactory(course=course, order=1)
        owner = UserFactory()
        answerer = UserFactory()
        _enroll(owner, course)
        _enroll(answerer, course)
        question = LessonQuestion.objects.create(
            lesson=lesson, user=owner, title="سؤال", body="متن سؤال معتبر"
        )

        with patch(_AUDIT_TASK_PATH) as mock_task:
            mock_task.delay = MagicMock()
            response = _client_for(answerer).post(
                reverse("lms:question-answer-create", kwargs={"question_id": question.pk}),
                data={"body": "این پاسخ پیشنهادی من است."},
                format="json",
            )

        assert response.status_code == status.HTTP_201_CREATED
        question.refresh_from_db()
        assert question.answer_count == 1
        assert mock_task.delay.call_args.kwargs["action"] == audit_actions.LMS_ANSWER_CREATED

    def test_question_owner_can_accept_answer(self) -> None:
        course = PublishedCourseFactory()
        lesson = LessonFactory(course=course, order=1)
        owner = UserFactory()
        answerer = UserFactory()
        _enroll(owner, course)
        _enroll(answerer, course)
        question = LessonQuestion.objects.create(
            lesson=lesson, user=owner, title="سؤال", body="متن سؤال معتبر"
        )
        answer = LessonAnswer.objects.create(question=question, user=answerer, body="پاسخ معتبر")

        response = _client_for(owner).post(
            reverse(
                "lms:question-answer-accept",
                kwargs={"question_id": question.pk, "answer_id": answer.pk},
            )
        )

        assert response.status_code == status.HTTP_200_OK
        answer.refresh_from_db()
        question.refresh_from_db()
        assert answer.is_accepted is True
        assert question.is_answered is True

    def test_non_owner_cannot_accept_answer(self) -> None:
        course = PublishedCourseFactory()
        lesson = LessonFactory(course=course, order=1)
        owner = UserFactory()
        other = UserFactory()
        _enroll(owner, course)
        _enroll(other, course)
        question = LessonQuestion.objects.create(
            lesson=lesson, user=owner, title="سؤال", body="متن سؤال معتبر"
        )
        answer = LessonAnswer.objects.create(question=question, user=other, body="پاسخ معتبر")

        response = _client_for(other).post(
            reverse(
                "lms:question-answer-accept",
                kwargs={"question_id": question.pk, "answer_id": answer.pk},
            )
        )

        assert response.status_code == status.HTTP_403_FORBIDDEN
        answer.refresh_from_db()
        assert answer.is_accepted is False


class TestLMSDiscussionReportsAndModeration:
    """Report and admin moderation tests."""

    def test_enrolled_user_can_report_question(self) -> None:
        course = PublishedCourseFactory()
        lesson = LessonFactory(course=course, order=1)
        owner = UserFactory()
        reporter = UserFactory()
        _enroll(owner, course)
        _enroll(reporter, course)
        question = LessonQuestion.objects.create(
            lesson=lesson, user=owner, title="سؤال", body="متن سؤال معتبر"
        )

        with patch(_AUDIT_TASK_PATH) as mock_task:
            mock_task.delay = MagicMock()
            response = _client_for(reporter).post(
                reverse("lms:question-report", kwargs={"question_id": question.pk}),
                data={"reason": "spam", "description": "تبلیغ نامناسب"},
                format="json",
            )

        assert response.status_code == status.HTTP_201_CREATED
        report = LessonDiscussionReport.objects.get(pk=response.data["data"]["id"])
        assert report.status == DiscussionReportStatus.PENDING
        assert mock_task.delay.call_args.kwargs["action"] == audit_actions.LMS_DISCUSSION_REPORTED

    def test_admin_can_hide_question_and_review_report(self) -> None:
        course = PublishedCourseFactory()
        lesson = LessonFactory(course=course, order=1)
        user = UserFactory()
        admin = AdminUserFactory()
        _enroll(user, course)
        question = LessonQuestion.objects.create(
            lesson=lesson, user=user, title="سؤال", body="متن سؤال معتبر"
        )
        report = LessonDiscussionReport.objects.create(
            question=question, reported_by=user, reason="spam"
        )

        hide_response = _client_for(admin).patch(
            reverse("lms:admin-question-moderate", kwargs={"question_id": question.pk}),
            data={"status": DiscussionStatus.HIDDEN, "is_pinned": False},
            format="json",
        )
        review_response = _client_for(admin).patch(
            reverse("lms:admin-discussion-report-review", kwargs={"report_id": report.pk}),
            data={"status": DiscussionReportStatus.REVIEWED},
            format="json",
        )

        assert hide_response.status_code == status.HTTP_200_OK
        assert review_response.status_code == status.HTTP_200_OK
        question.refresh_from_db()
        report.refresh_from_db()
        assert question.status == DiscussionStatus.HIDDEN
        assert report.status == DiscussionReportStatus.REVIEWED
        assert report.reviewed_by_id == admin.pk

    def test_hidden_questions_are_not_listed_for_users(self) -> None:
        course = PublishedCourseFactory()
        lesson = LessonFactory(course=course, order=1)
        user = UserFactory()
        _enroll(user, course)
        LessonQuestion.objects.create(
            lesson=lesson,
            user=user,
            title="مخفی",
            body="متن سؤال معتبر",
            status=DiscussionStatus.HIDDEN,
        )

        response = _client_for(user).get(
            reverse("lms:lesson-question-list-create", kwargs={"lesson_id": lesson.pk})
        )

        assert response.status_code == status.HTTP_200_OK
        assert response.data["data"]["count"] == 0


class TestLMSLessonAnswerReplies:
    """ردهای تودرتوی یک‌سطحی (الگوی یوتیوب): parent/reply_to + اعتبارسنجی هدف."""

    def _question(self, lesson, user):
        return LessonQuestion.objects.create(
            lesson=lesson, user=user, title="سؤال مهم", body="متن سؤال معتبر برای تست"
        )

    def _reply(self, user, question, body, parent_id):
        with patch(_AUDIT_TASK_PATH) as mock_task:
            mock_task.delay = MagicMock()
            response = _client_for(user).post(
                reverse("lms:question-answer-create", kwargs={"question_id": question.pk}),
                data={"body": body, "parent_id": parent_id},
                format="json",
            )
        return response

    def test_user_can_reply_under_another_users_answer(self) -> None:
        course = PublishedCourseFactory()
        lesson = LessonFactory(course=course, order=1)
        owner = UserFactory()
        replier = UserFactory()
        _enroll(owner, course)
        _enroll(replier, course)
        question = self._question(lesson, owner)
        root = LessonAnswer.objects.create(question=question, user=owner, body="پاسخ اولیه")

        response = self._reply(replier, question, "رد من روی پاسخ تو", root.pk)

        assert response.status_code == status.HTTP_201_CREATED
        payload = response.data["data"]
        assert payload["parent_id"] == root.pk
        assert payload["reply_to_display"]
        reply = LessonAnswer.objects.get(pk=payload["id"])
        assert reply.parent_id == root.pk
        assert reply.reply_to_id == root.pk

    def test_question_owner_can_answer_own_question(self) -> None:
        course = PublishedCourseFactory()
        lesson = LessonFactory(course=course, order=1)
        owner = UserFactory()
        _enroll(owner, course)
        question = self._question(lesson, owner)

        with patch(_AUDIT_TASK_PATH) as mock_task:
            mock_task.delay = MagicMock()
            response = _client_for(owner).post(
                reverse("lms:question-answer-create", kwargs={"question_id": question.pk}),
                data={"body": "توضیح تکمیلی از خودِ سؤال‌کننده"},
                format="json",
            )

        assert response.status_code == status.HTTP_201_CREATED

    def test_reply_payload_carries_reply_to_id_and_excerpt(self) -> None:
        """نقل‌قولِ دقیقِ هدفِ رد: reply_to_id + reply_to_excerpt (بریده تا ۱۴۰ نویسه)."""
        course = PublishedCourseFactory()
        lesson = LessonFactory(course=course, order=1)
        owner = UserFactory()
        replier = UserFactory()
        _enroll(owner, course)
        _enroll(replier, course)
        question = self._question(lesson, owner)
        long_body = "چون var فقط یک اسکوپ تابعی دارد و این خیلی مهم است " * 9
        root = LessonAnswer.objects.create(question=question, user=owner, body=long_body)

        response = self._reply(replier, question, "پاسخ دقیق همین بود، ممنون", root.pk)

        assert response.status_code == status.HTTP_201_CREATED
        payload = response.data["data"]
        assert payload["reply_to_id"] == root.pk
        excerpt = payload["reply_to_excerpt"]
        assert excerpt is not None
        assert excerpt.endswith("…")
        body_part = excerpt[:-1]
        assert 120 <= len(body_part) <= 137
        assert long_body.startswith(body_part)

        short = LessonAnswer.objects.create(question=question, user=owner, body="کوتاه و شفاف")
        response2 = self._reply(replier, question, "رد کوتاه هم اوکی است", short.pk)
        assert response2.status_code == status.HTTP_201_CREATED
        assert response2.data["data"]["reply_to_excerpt"] == "کوتاه و شفاف"

        listing = _client_for(replier).get(
            reverse("lms:lesson-question-list-create", kwargs={"lesson_id": lesson.pk})
        )
        assert listing.status_code == status.HTTP_200_OK
        top_answers = listing.data["data"]["results"][0]["answers"]
        nested = top_answers[0]["replies"][0]
        assert nested["reply_to_id"] == root.pk
        assert nested["reply_to_excerpt"].startswith(long_body[:20])
        # پاسخِ سطح‌صفر هرگز نقل‌قول ندارد
        assert top_answers[0]["reply_to_id"] is None
        assert top_answers[0]["reply_to_excerpt"] is None

    def test_reply_to_reply_is_anchored_to_thread_root(self) -> None:
        course = PublishedCourseFactory()
        lesson = LessonFactory(course=course, order=1)
        users = [UserFactory() for _ in range(3)]
        for u in users:
            _enroll(u, course)
        question = self._question(lesson, users[0])
        root = LessonAnswer.objects.create(question=question, user=users[0], body="پاسخ ریشه")
        first = self._reply(users[1], question, "رد سطح یک", root.pk)
        assert first.status_code == status.HTTP_201_CREATED
        first_id = first.data["data"]["id"]

        second = self._reply(users[2], question, "رد روی رد", first_id)

        assert second.status_code == status.HTTP_201_CREATED
        payload = second.data["data"]
        assert payload["parent_id"] == root.pk  # لنگرِ رشته
        assert payload["reply_to_display"]  # زنجیره‌ی نمایشی حفظ شده
        reply_obj = LessonAnswer.objects.get(pk=payload["id"])
        assert reply_obj.parent_id == root.pk
        assert reply_obj.reply_to_id == first_id

        # خروجی لیست: هر دو رد زیرِ ریشه، نه به‌صورت تخت
        listing = _client_for(users[0]).get(
            reverse("lms:lesson-question-list-create", kwargs={"lesson_id": lesson.pk})
        )
        answers = listing.data["data"]["results"][0]["answers"]
        assert [a["id"] for a in answers] == [root.pk]
        reply_ids = {r["id"] for a in answers for r in a["replies"]}
        assert reply_ids == {first_id, payload["id"]}
        second_in_tree = next(r for a in answers for r in a["replies"] if r["id"] == payload["id"])
        assert second_in_tree["reply_to_display"]

    def test_reply_to_answer_of_another_question_rejected(self) -> None:
        course = PublishedCourseFactory()
        lesson = LessonFactory(course=course, order=1)
        user = UserFactory()
        _enroll(user, course)
        q1 = self._question(lesson, user)
        q2 = self._question(lesson, user)
        foreign = LessonAnswer.objects.create(question=q2, user=user, body="پاسخ سؤال دیگر")

        response = self._reply(user, q1, "رد به جای اشتباه", foreign.pk)

        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_reply_to_hidden_answer_rejected(self) -> None:
        course = PublishedCourseFactory()
        lesson = LessonFactory(course=course, order=1)
        user = UserFactory()
        _enroll(user, course)
        question = self._question(lesson, user)
        root = LessonAnswer.objects.create(question=question, user=user, body="پاسخی که مخفی شد")
        root.status = DiscussionStatus.HIDDEN
        root.save(update_fields=["status", "updated_at"])

        response = self._reply(user, question, "رد روی پاسخ مخفی", root.pk)

        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_non_enrolled_user_cannot_reply(self) -> None:
        course = PublishedCourseFactory()
        lesson = LessonFactory(course=course, order=1)
        owner = UserFactory()
        stranger = UserFactory()
        _enroll(owner, course)
        _complete_profile(stranger)
        question = self._question(lesson, owner)
        root = LessonAnswer.objects.create(question=question, user=owner, body="پاسخ ریشه")

        response = self._reply(stranger, question, "ردِ غریبه", root.pk)

        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_reply_bumps_answer_count_for_thread_counters(self) -> None:
        course = PublishedCourseFactory()
        lesson = LessonFactory(course=course, order=1)
        owner = UserFactory()
        replier = UserFactory()
        _enroll(owner, course)
        _enroll(replier, course)
        question = self._question(lesson, owner)
        root = LessonAnswer.objects.create(question=question, user=owner, body="پاسخ ریشه")
        question.answer_count = 1
        question.save(update_fields=["answer_count", "updated_at"])

        response = self._reply(replier, question, "رد تازه", root.pk)

        assert response.status_code == status.HTTP_201_CREATED
        question.refresh_from_db()
        assert question.answer_count == 2

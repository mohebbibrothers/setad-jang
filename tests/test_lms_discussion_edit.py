"""
LMS discussion self-service editing — ویرایش/حذفِ متنِ خودِ کاربر + گاردِ گزارش.

این سوئیت قواعد جدیدِ گفتگو را تضمین می‌کند:
- نویسنده (یا ادمین) بتواند پرسش/پاسخ خودش را ویرایش کند؛ مهرِ «ویرایش‌شده» می‌خورد.
- حذفِ متنِ دارای گفتگوی زنده «سنگ‌قبر» می‌شود (متن اصلی هرگز لو نمی‌رود) و
  حذفِ برگ کاملاً نابود می‌شود؛ شمارنده‌ها همگام می‌مانند.
- گزارشِ متنِ خود معنا ندارد و روی سیم ۴۰۰ می‌شود (جلوِ UI گرفتن کافی نیست).
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient

from apps.audit_logs import actions as audit_actions
from apps.lms.choices import DiscussionStatus
from apps.lms.models import Enrollment, LessonAnswer, LessonDiscussionReport, LessonQuestion
from tests.factories import AdminUserFactory, UserFactory
from tests.factories.lms import LessonFactory, PublishedCourseFactory

pytestmark = pytest.mark.django_db

_AUDIT_TASK_PATH = "apps.audit_logs.tasks.create_audit_log_task"


def _client_for(user) -> APIClient:
    client = APIClient()
    client.force_authenticate(user=user)
    return client


def _complete_profile(user) -> None:
    user.first_name = "Ali"
    user.last_name = "Mohammadi"
    user.save(update_fields=["first_name", "last_name"])
    user.profile.national_code = "0123456789"
    user.profile.save(update_fields=["national_code"])


def _enroll(user, course) -> Enrollment:
    _complete_profile(user)
    response = _client_for(user).post(reverse("lms:course-enroll", kwargs={"slug": course.slug}))
    assert response.status_code == status.HTTP_201_CREATED, response.data
    return Enrollment.objects.get(user=user, course=course)


def _setup_thread():
    """Course + one lesson + two enrolled users + a question with answer+reply."""
    course = PublishedCourseFactory()
    lesson = LessonFactory(course=course, order=1)
    owner = UserFactory()
    other = UserFactory()
    third = UserFactory()
    _enroll(owner, course)
    _enroll(other, course)
    _enroll(third, course)
    question = LessonQuestion.objects.create(
        lesson=lesson,
        user=owner,
        title="سؤال دارای رشته",
        body="متنِ کاملِ سؤال برای تستِ ویرایش و حذف.",
        status=DiscussionStatus.VISIBLE,
        answer_count=2,
    )
    answer = LessonAnswer.objects.create(
        question=question,
        user=other,
        body="پاسخِ کاربرِ دیگر با متنِ کافی.",
        status=DiscussionStatus.VISIBLE,
    )
    reply = LessonAnswer.objects.create(
        question=question,
        user=owner,
        parent=answer,
        reply_to=answer,
        body="ردِ صاحبِ پرسش زیرِ پاسخ.",
        status=DiscussionStatus.VISIBLE,
    )
    return lesson, owner, other, third, question, answer, reply


class TestQuestionEditDelete:
    def test_owner_can_edit_question_and_gets_edited_stamp(self) -> None:
        _lesson, owner, *_rest, question, _a, _r = _setup_thread()
        response = _client_for(owner).patch(
            reverse("lms:question-detail", kwargs={"question_id": question.pk}),
            data={
                "title": "عنوانِ اصلاح‌شده‌ی سؤال",
                "body": "متنِ جدید و کامل برای سؤال بعد از ویرایش.",
            },
            format="json",
        )
        assert response.status_code == status.HTTP_200_OK
        question.refresh_from_db()
        assert question.title == "عنوانِ اصلاح‌شده‌ی سؤال"
        assert question.edited_at is not None
        assert response.data["data"]["edited_at"] is not None

    def test_stranger_cannot_edit_question(self) -> None:
        _lesson, _owner, other, *_rest, question, _a, _r = _setup_thread()
        response = _client_for(other).patch(
            reverse("lms:question-detail", kwargs={"question_id": question.pk}),
            data={"title": "عنوانِ دزدیده‌شده", "body": "متنِ جایگزینِ نامعتبر برای رخنه."},
            format="json",
        )
        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_admin_can_edit_any_question(self) -> None:
        _lesson, *_rest, question, _a, _r = _setup_thread()
        admin = AdminUserFactory()
        response = _client_for(admin).patch(
            reverse("lms:question-detail", kwargs={"question_id": question.pk}),
            data={"title": "ویرایشِ توسط تیم", "body": "مداخله‌ی مدیریتی در متن پرسش کاربر."},
            format="json",
        )
        assert response.status_code == status.HTTP_200_OK

    def test_deleted_question_cannot_be_edited(self) -> None:
        _lesson, owner, *_rest, question, _a, _r = _setup_thread()
        question.status = DiscussionStatus.DELETED
        question.save(update_fields=["status"])
        response = _client_for(owner).patch(
            reverse("lms:question-detail", kwargs={"question_id": question.pk}),
            data={"title": "زنده‌کردنِ سنگ‌قبر", "body": "تلاش برای ویرایشِ پرسشِ حذف‌شده."},
            format="json",
        )
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_delete_question_without_visible_answers_is_hard(self) -> None:
        course = PublishedCourseFactory()
        lesson = LessonFactory(course=course, order=1)
        owner = UserFactory()
        _enroll(owner, course)
        question = LessonQuestion.objects.create(
            lesson=lesson,
            user=owner,
            title="سؤالِ تنها",
            body="بدونِ هیچ پاسخی — باید کامل نابود شود.",
            status=DiscussionStatus.VISIBLE,
        )
        with patch(_AUDIT_TASK_PATH) as mock_task:
            mock_task.delay = MagicMock()
            response = _client_for(owner).delete(
                reverse("lms:question-detail", kwargs={"question_id": question.pk})
            )
        assert response.status_code == status.HTTP_200_OK
        assert response.data["data"]["mode"] == "hard"
        assert not LessonQuestion.objects.filter(pk=question.pk).exists()
        assert mock_task.delay.call_args.kwargs["action"] == audit_actions.LMS_QUESTION_DELETED

    def test_delete_question_with_live_answers_becomes_tombstone(self) -> None:
        lesson, owner, other, *_rest, question, _answer, _reply = _setup_thread()
        response = _client_for(owner).delete(
            reverse("lms:question-detail", kwargs={"question_id": question.pk})
        )
        assert response.status_code == status.HTTP_200_OK
        assert response.data["data"]["mode"] == "tombstone"
        question.refresh_from_db()
        assert question.status == DiscussionStatus.DELETED
        # رشته در فهرست با سنگ‌قبر می‌آید و متنِ اصلی لو نمی‌رود
        lst = _client_for(other).get(
            reverse("lms:lesson-question-list-create", kwargs={"lesson_id": lesson.pk})
        )
        assert lst.status_code == status.HTTP_200_OK
        row = next(q for q in lst.data["data"]["results"] if q["id"] == question.pk)
        assert row["is_deleted"] is True
        assert row["title"] == "" and row["body"] == ""
        assert len(row["answers"]) == 1  # پاسخِ زنده زیرش مانده

    def test_tombstone_cannot_be_deleted_again(self) -> None:
        _lesson, owner, *_rest, question, _a, _r = _setup_thread()
        question.status = DiscussionStatus.DELETED
        question.save(update_fields=["status"])
        response = _client_for(owner).delete(
            reverse("lms:question-detail", kwargs={"question_id": question.pk})
        )
        assert response.status_code == status.HTTP_400_BAD_REQUEST


class TestAnswerEditDelete:
    def test_owner_can_edit_answer(self) -> None:
        _lesson, _owner, other, *_rest, _question, answer, _reply = _setup_thread()
        response = _client_for(other).patch(
            reverse("lms:answer-detail", kwargs={"answer_id": answer.pk}),
            data={"body": "متنِ اصلاح‌شده‌ی پاسخ — نسخه‌ی بهتر."},
            format="json",
        )
        assert response.status_code == status.HTTP_200_OK
        answer.refresh_from_db()
        assert answer.body.startswith("متنِ اصلاح‌شده‌ی")
        assert answer.edited_at is not None
        assert response.data["data"]["edited_at"] is not None

    def test_stranger_cannot_edit_answer(self) -> None:
        _lesson, *_rest, third, _question, answer, _reply = _setup_thread()
        response = _client_for(third).patch(
            reverse("lms:answer-detail", kwargs={"answer_id": answer.pk}),
            data={"body": "دست‌کاریِ پاسخِ دیگران."},
            format="json",
        )
        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_delete_leaf_answer_is_hard_and_resyncs_counter(self) -> None:
        _lesson, owner, *_rest, question, _answer, reply = _setup_thread()
        # ردِ برگ (بدون فرزند) → hard
        question.answer_count = LessonAnswer.objects.filter(
            question=question, status=DiscussionStatus.VISIBLE
        ).count()
        question.save(update_fields=["answer_count"])
        before = question.answer_count
        with patch(_AUDIT_TASK_PATH) as mock_task:
            mock_task.delay = MagicMock()
            response = _client_for(owner).delete(
                reverse("lms:answer-detail", kwargs={"answer_id": reply.pk})
            )
        assert response.status_code == status.HTTP_200_OK
        assert response.data["data"]["mode"] == "hard"
        assert not LessonAnswer.objects.filter(pk=reply.pk).exists()
        question.refresh_from_db()
        assert question.answer_count == before - 1
        assert mock_task.delay.call_args.kwargs["action"] == audit_actions.LMS_ANSWER_DELETED

    def test_delete_answer_with_live_reply_becomes_tombstone_keeps_chain(self) -> None:
        lesson, owner, other, *_rest, question, answer, reply = _setup_thread()
        response = _client_for(other).delete(
            reverse("lms:answer-detail", kwargs={"answer_id": answer.pk})
        )
        assert response.status_code == status.HTTP_200_OK
        assert response.data["data"]["mode"] == "tombstone"
        answer.refresh_from_db()
        assert answer.status == DiscussionStatus.DELETED
        # زنجیره در فهرست: ریشه سنگ‌قبر است اما ردِ زیرش زنده
        lst = _client_for(owner).get(
            reverse("lms:lesson-question-list-create", kwargs={"lesson_id": lesson.pk})
        )
        row = next(q for q in lst.data["data"]["results"] if q["id"] == question.pk)
        top = next(a for a in row["answers"] if a["id"] == answer.pk)
        assert top["is_deleted"] is True
        assert top["body"] == ""
        assert [r["id"] for r in top["replies"]] == [reply.pk]
        # نقل‌قولِ «در پاسخ به» روی رد، بدنه‌ی حذف‌شده را لو نمی‌دهد
        assert top["replies"][0]["reply_to_excerpt"] is None


class TestSelfReportGuard:
    def test_report_own_question_is_400(self) -> None:
        _lesson, owner, *_rest, question, _a, _r = _setup_thread()
        response = _client_for(owner).post(
            reverse("lms:question-report", kwargs={"question_id": question.pk}),
            data={"reason": "اسپم"},
            format="json",
        )
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "خودتان" in str(response.data)
        assert LessonDiscussionReport.objects.count() == 0

    def test_report_own_answer_is_400(self) -> None:
        _lesson, _owner, other, *_rest, _question, answer, _r = _setup_thread()
        response = _client_for(other).post(
            reverse("lms:answer-report", kwargs={"answer_id": answer.pk}),
            data={"reason": "توهین"},
            format="json",
        )
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "خودتان" in str(response.data)
        assert LessonDiscussionReport.objects.count() == 0

    def test_report_other_users_reply_still_works(self) -> None:
        _lesson, _owner, _other, third, _question, _answer, reply = _setup_thread()
        with patch(_AUDIT_TASK_PATH) as mock_task:
            mock_task.delay = MagicMock()
            response = _client_for(third).post(
                reverse("lms:answer-report", kwargs={"answer_id": reply.pk}),
                data={"reason": "محتوای نامرتبط"},
                format="json",
            )
        assert response.status_code == status.HTTP_201_CREATED
        assert LessonDiscussionReport.objects.filter(answer=reply).exists()

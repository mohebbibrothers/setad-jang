"""Tests for the review-hardening batch (mirrors, server-stamped engagement,
stream-token revocation, render safety caps, and automated pre-render wiring).

Each test locks one finding from the senior review so the fix cannot silently
regress: the quiz-state endpoint must mirror what start_quiz_attempt enforces,
opening media via the access API must itself satisfy the document-completion
gate, a live stream token must die the moment its enrollment dies, PDFium
pre-render must be area capped and queued off the publish/request path, and the
bundled Vazirmatn fonts must ship their OFL license text.
"""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path
from unittest.mock import patch

import pytest
from django.test import TestCase
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient

from apps.audit_logs import actions as audit_actions
from apps.lms.choices import CourseStatus, EnrollmentStatus, QuizStatus
from apps.lms.models import LessonProgress, QuizOption, QuizQuestion
from apps.lms.pdf_pages import MAX_PAGE_PIXELS, RENDER_SCALE, page_render_scale
from apps.lms.services import (
    LessonMediaEngagementRequiredError,
    build_lesson_media_access,
    publish_course,
    publish_quiz,
    update_lesson,
    update_lesson_progress,
)
from tests.factories import UserFactory
from tests.factories.lms import (
    CourseFactory,
    DocumentLessonFactory,
    LessonFactory,
    PublishedCourseFactory,
    QuizFactory,
)

_REPO_ROOT = Path(__file__).resolve().parents[1]
_OFL = _REPO_ROOT / "static" / "lms" / "certificates" / "fonts" / "OFL.txt"


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


def _enroll(user, course):
    _complete_profile(user)
    response = _client_for(user).post(reverse("lms:course-enroll", kwargs={"slug": course.slug}))
    assert response.status_code == status.HTTP_201_CREATED, response.data
    return course.enrollments.get(user=user)


def _meta(client, slug) -> dict:
    response = client.get(reverse("lms:course-quiz", kwargs={"slug": slug}))
    assert response.status_code == status.HTTP_200_OK
    return response.data["data"]["attempt_state"]


def _build_publishable_quiz(course, *, passing_score=Decimal("12.00")):
    quiz = QuizFactory(
        course=course,
        title="آزمون بازبینی",
        passing_score=passing_score,
        status=QuizStatus.DRAFT,
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
        {
            "answers": [
                {"question_id": q1.pk, "selected_option_id": q1_wrong.pk},
                {"question_id": q2.pk, "selected_option_id": q2_wrong.pk},
            ]
        },
        {
            "answers": [
                {"question_id": q1.pk, "selected_option_id": q1_correct.pk},
                {"question_id": q2.pk, "selected_option_id": q2_correct.pk},
            ]
        },
    )


def _complete_all_lessons(enrollment) -> None:
    for lesson in enrollment.course.lessons.filter(is_active=True):
        manual = lesson.supports_manual_completion
        update_lesson_progress(
            enrollment=enrollment,
            lesson=lesson,
            watched_seconds=lesson.duration_seconds or 600,
            last_position_seconds=lesson.duration_seconds or 600,
            mark_completed=manual,
        )


@pytest.mark.django_db
class TestQuizStateMirrorsStartGate:
    """Y1: the state endpoint must mirror what start_quiz_attempt enforces."""

    def test_state_locks_lessons_remaining_then_unlocks_after_completion(self) -> None:
        course = PublishedCourseFactory()
        LessonFactory(course=course, duration_seconds=540)
        LessonFactory(course=course, duration_seconds=540)
        _quiz, _wrong, right = _build_publishable_quiz(course)
        user = UserFactory()
        enrollment = _enroll(user, course)

        body = _meta(_client_for(user), course.slug)
        assert body["can_attempt"] is False
        assert body["locked_reason"] == "lessons_remaining"
        assert body["lessons_remaining"] == 2

        # the mirror cuts both ways: POST start enforces exactly the same rule
        start = _client_for(user).post(
            reverse("lms:quiz-attempt-start", kwargs={"slug": course.slug})
        )
        assert start.status_code == status.HTTP_403_FORBIDDEN
        assert "هنوز 2 جلسه مانده" in start.data["message"]

        _complete_all_lessons(enrollment)
        body2 = _meta(_client_for(user), course.slug)
        assert body2["can_attempt"] is True
        assert body2["locked_reason"] is None
        assert body2["lessons_remaining"] == 0

        started = _client_for(user).post(
            reverse("lms:quiz-attempt-start", kwargs={"slug": course.slug})
        )
        assert started.status_code == status.HTTP_201_CREATED
        sub = _client_for(user).post(
            reverse(
                "lms:quiz-attempt-submit",
                kwargs={"attempt_id": started.data["data"]["id"]},
            ),
            right,
            format="json",
        )
        assert sub.status_code == status.HTTP_200_OK, sub.data
        passed = _meta(_client_for(user), course.slug)
        # passed outranks everything — including the (now satisfied) lessons gate
        assert passed["passed_before"] is True
        assert passed["locked_reason"] == "passed"
        assert passed["can_attempt"] is False

    def test_in_progress_attempt_is_exempt_from_the_state_gate_too(self) -> None:
        course = PublishedCourseFactory()
        LessonFactory(course=course, duration_seconds=540)
        _quiz, _wrong, _right = _build_publishable_quiz(course)
        user = UserFactory()
        enrollment = _enroll(user, course)
        _complete_all_lessons(enrollment)
        started = _client_for(user).post(
            reverse("lms:quiz-attempt-start", kwargs={"slug": course.slug})
        )
        assert started.status_code == status.HTTP_201_CREATED
        # progress vanishes mid-attempt (retake flow re-unchecks a lesson)
        enrollment.lesson_progress.update(is_completed=False, completed_at=None)

        state = _meta(_client_for(user), course.slug)
        assert state["has_in_progress"] is True
        assert state["locked_reason"] is None
        assert state["can_attempt"] is True
        resume = _client_for(user).post(
            reverse("lms:quiz-attempt-start", kwargs={"slug": course.slug})
        )
        assert resume.status_code == status.HTTP_200_OK

    def test_completed_enrollment_never_sees_lessons_remaining(self) -> None:
        course = PublishedCourseFactory()
        LessonFactory(course=course, duration_seconds=540)
        _quiz, _wrong, _right = _build_publishable_quiz(course)
        user = UserFactory()
        enrollment = _enroll(user, course)
        enrollment.status = EnrollmentStatus.COMPLETED
        enrollment.save(update_fields=["status"])
        state = _meta(_client_for(user), course.slug)
        assert state["lessons_remaining"] == 0
        assert state["locked_reason"] is None


@pytest.mark.django_db
class TestServerStampedDocumentEngagement:
    """Y2: opening media via the access API stamps engagement server-side."""

    def _doc_lesson(self, settings, tmp_path):
        settings.MEDIA_ROOT = tmp_path
        course = PublishedCourseFactory()
        return DocumentLessonFactory(course=course), course

    def test_access_open_stamps_and_satisfies_gate_without_client_flag(
        self, settings, tmp_path
    ) -> None:
        lesson, course = self._doc_lesson(settings, tmp_path)
        user = UserFactory()
        enrollment = _enroll(user, course)
        assert not LessonProgress.objects.filter(enrollment=enrollment, lesson=lesson).exists()

        build_lesson_media_access(lesson=lesson, user=user, media_kind="document")
        progress = LessonProgress.objects.get(enrollment=enrollment, lesson=lesson)
        assert progress.media_opened_at is not None
        assert progress.duration_seconds_snapshot == lesson.duration_seconds

        # mark_completed now succeeds with NO client-side confession
        update_lesson_progress(
            enrollment=enrollment, lesson=lesson, watched_seconds=10, mark_completed=True
        )
        progress.refresh_from_db()
        assert progress.is_completed is True

    def test_mark_completed_before_any_real_open_is_blocked(self, settings, tmp_path) -> None:
        lesson, course = self._doc_lesson(settings, tmp_path)
        user = UserFactory()
        enrollment = _enroll(user, course)
        with pytest.raises(LessonMediaEngagementRequiredError):
            update_lesson_progress(
                enrollment=enrollment, lesson=lesson, watched_seconds=10, mark_completed=True
            )
        # legacy client flag still works (backward-compatibility contract)
        update_lesson_progress(
            enrollment=enrollment,
            lesson=lesson,
            watched_seconds=10,
            mark_completed=True,
            media_opened=True,
        )
        assert LessonProgress.objects.get(enrollment=enrollment, lesson=lesson).is_completed is True

    def test_preview_open_creates_no_progress_row(self, settings, tmp_path) -> None:
        lesson, _course = self._doc_lesson(settings, tmp_path)
        lesson.is_preview = True
        lesson.save(update_fields=["is_preview"])
        user = UserFactory()
        build_lesson_media_access(lesson=lesson, user=user, media_kind="document")
        assert not LessonProgress.objects.filter(lesson=lesson).exists()


@pytest.mark.django_db
class TestStreamTokenRevocationAndAudit:
    """Y3: live tokens die with the enrollment; streams leave audit trails."""

    def _doc(self, settings, tmp_path):
        settings.MEDIA_ROOT = tmp_path
        course = PublishedCourseFactory()
        return DocumentLessonFactory(course=course), course

    def test_cancelled_enrollment_kills_a_live_stream_token(self, settings, tmp_path) -> None:
        lesson, course = self._doc(settings, tmp_path)
        user = UserFactory()
        enrollment = _enroll(user, course)
        payload = build_lesson_media_access(lesson=lesson, user=user, media_kind="document")
        stream_url = f"/api/v1/{payload['url']}"
        ok = APIClient().get(stream_url)
        assert ok.status_code == status.HTTP_200_OK
        assert "inline" in ok["Content-Disposition"]
        assert b"".join(ok.streaming_content)  # مصرف تا آخر تا هندلِ فایل بسته شود

        enrollment.status = EnrollmentStatus.CANCELED
        enrollment.save(update_fields=["status"])
        dead = APIClient().get(stream_url)
        assert dead.status_code == status.HTTP_403_FORBIDDEN
        assert "ثبت‌نام" in dead.data["message"]
        # the file is still there — death is access-side, not media-side
        assert bool(lesson.document_file)

    def test_completed_enrollment_keeps_streaming(self, settings, tmp_path) -> None:
        lesson, course = self._doc(settings, tmp_path)
        user = UserFactory()
        enrollment = _enroll(user, course)
        enrollment.status = EnrollmentStatus.COMPLETED
        enrollment.save(update_fields=["status"])
        payload = build_lesson_media_access(lesson=lesson, user=user, media_kind="document")
        ok = APIClient().get(f"/api/v1/{payload['url']}")
        assert ok.status_code == status.HTTP_200_OK
        assert b"".join(ok.streaming_content)

    def test_token_stream_is_audited_as_its_owner(self, settings, tmp_path) -> None:
        lesson, course = self._doc(settings, tmp_path)
        user = UserFactory()
        _enroll(user, course)
        payload = build_lesson_media_access(lesson=lesson, user=user, media_kind="document")
        with patch("apps.lms.views_learning.log_action_async") as audit:
            resp = APIClient().get(f"/api/v1/{payload['url']}")
            assert resp.status_code == status.HTTP_200_OK
            assert b"".join(resp.streaming_content)
        audit.assert_called_once()
        kwargs = audit.call_args.kwargs
        assert kwargs["user_id"] == user.pk
        assert kwargs["action"] == audit_actions.LMS_LESSON_MEDIA_STREAMED


@pytest.mark.django_db
class TestDocumentRenderSafetyAndScheduling:
    """Y4/Y5: area-capped pre-render, queued off the request path."""

    def test_extreme_aspect_pages_are_area_capped(self) -> None:
        # healthy A4 keeps the full scale
        assert page_render_scale(595.32, 841.92) == pytest.approx(RENDER_SCALE)
        # pathological 1×4M page: width caps are useless — the area cap bites
        scale = page_render_scale(1.0, 4_000_000.0)
        assert 1.0 * scale * 4_000_000.0 * scale <= MAX_PAGE_PIXELS * 1.000001
        assert scale < RENDER_SCALE

    def test_document_update_queues_prerender_within_on_commit(self, settings, tmp_path) -> None:
        settings.MEDIA_ROOT = tmp_path
        course = PublishedCourseFactory()
        lesson = DocumentLessonFactory(course=course)
        with (
            patch("apps.lms.tasks.render_lesson_document_pages_task.delay") as queue,
            TestCase.captureOnCommitCallbacks(execute=True),
        ):
            update_lesson(lesson=lesson, document_file="replaced/path.pdf")
        queue.assert_called_once_with(lesson_id=lesson.pk)

    def test_video_only_update_does_not_queue_document_render(self, settings, tmp_path) -> None:
        course = PublishedCourseFactory()
        lesson = LessonFactory(course=course, duration_seconds=600)
        with (
            patch("apps.lms.tasks.render_lesson_document_pages_task.delay") as queue,
            TestCase.captureOnCommitCallbacks(execute=True),
        ):
            update_lesson(lesson=lesson, title="تازه‌سازی")
        queue.assert_not_called()

    def test_publish_queues_prerender_for_documents_with_files_only(
        self, settings, tmp_path
    ) -> None:
        settings.MEDIA_ROOT = tmp_path
        course = CourseFactory(status=CourseStatus.DRAFT)
        DocumentLessonFactory(course=course)
        # فعال‌بدون‌فایل تاوانِ validate می‌دهد؛ اینجا پرت است — گاردِ
        # schedule مستقیم در تستِ جدا اثبات می‌شود.
        DocumentLessonFactory(course=course, document_file=None, is_active=False)
        LessonFactory(course=course, duration_seconds=600, video_url="https://cdn.example/v1.mp4")
        with (
            patch("apps.lms.tasks.render_lesson_document_pages_task.delay") as queue,
            TestCase.captureOnCommitCallbacks(execute=True),
        ):
            publish_course(course=course)
        assert queue.call_count == 1

    def test_republish_of_published_course_does_not_resweep(self, settings, tmp_path) -> None:
        settings.MEDIA_ROOT = tmp_path
        course = PublishedCourseFactory()
        DocumentLessonFactory(course=course)
        with (
            patch("apps.lms.tasks.render_lesson_document_pages_task.delay") as queue,
            TestCase.captureOnCommitCallbacks(execute=True),
        ):
            publish_course(course=course)
        queue.assert_not_called()

    def test_broker_failure_never_breaks_publish(self, settings, tmp_path) -> None:
        settings.MEDIA_ROOT = tmp_path
        course = PublishedCourseFactory()
        DocumentLessonFactory(course=course)
        course.status = CourseStatus.DRAFT
        course.save(update_fields=["status"])
        with (
            patch(
                "apps.lms.tasks.render_lesson_document_pages_task.delay",
                side_effect=RuntimeError("no broker"),
            ),
            TestCase.captureOnCommitCallbacks(execute=True),
        ):
            published = publish_course(course=course)
        assert published.status == CourseStatus.PUBLISHED

    def test_schedule_guard_skips_document_less_lessons(self, settings, tmp_path) -> None:
        from apps.lms.services import schedule_document_render

        settings.MEDIA_ROOT = tmp_path
        doc = DocumentLessonFactory(course=PublishedCourseFactory())
        with (
            patch("apps.lms.tasks.render_lesson_document_pages_task.delay") as queue,
            TestCase.captureOnCommitCallbacks(execute=True),
        ):
            doc.document_file = ""
            schedule_document_render(lesson=doc)  # بی‌فایل → بی‌صف
            doc.refresh_from_db()
            schedule_document_render(lesson=doc)  # فایلِ واقعی → یک صف
        assert queue.call_count == 1

    def test_render_task_skips_missing_lesson(self) -> None:
        from apps.lms.tasks import render_lesson_document_pages_task

        result = render_lesson_document_pages_task.apply(kwargs={"lesson_id": 999_999})
        assert result.result == {"lesson_id": 999_999, "status": "skipped"}


@pytest.mark.django_db
class TestFontLicenseBundling:
    """Y6: Vazirmatn is OFL — the license text must ship with the fonts."""

    def test_ofl_text_ships_next_to_vazirmatn(self) -> None:
        assert _OFL.exists(), "OFL.txt must accompany the bundled Vazirmatn fonts"
        text = _OFL.read_text(encoding="utf-8")
        assert "SIL OPEN FONT LICENSE Version 1.1" in text
        assert "Vazirmatn" in text

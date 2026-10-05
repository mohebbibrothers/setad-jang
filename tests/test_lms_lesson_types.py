"""
LMS multi-content-type lessons & certificate-policy tests.

این تست‌ها دو اصلاح بنيادین را قفل می‌کنند:
1) جلسات دیگر ویدئو-محور نیستند: سند/PDF و متن درون‌برنامه‌ای (article) و صوت
   به‌عنوان نوع محتوا پشتیبانی می‌شوند؛ جلسهٔ سند/متنی با «علامت تکمیل» بسته
   می‌شود نه درصد تماشا، و publish دوره جلوی انتشارِ جلسهٔ بی‌محتوا را می‌گیرد.
2) سیاست مدرک آزمون اعمال می‌شود: اگر آزمون دوره‌ای is_required_for_certificate
   داشته باشد قبولی گواهی صادر می‌کند، و اگر نداشته باشد فقط ثبت‌نام تکمیل می‌شود.
"""

from __future__ import annotations

from decimal import Decimal

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient

from apps.lms.choices import (
    EnrollmentStatus,
    LessonContentType,
    QuizStatus,
)
from apps.lms.models import Enrollment, Lesson, LessonProgress, QuizOption, QuizQuestion
from apps.lms.serializers import LessonSummarySerializer
from apps.lms.services import (
    CourseInvalidStateError,
    LessonCompletionModeError,
    LessonMediaAccessError,
    LessonMediaUnavailableError,
    build_lesson_media_access,
    publish_course,
    publish_quiz,
    sync_course_counters,
    update_lesson_progress,
)
from tests.factories import (
    ArticleLessonFactory,
    DocumentLessonFactory,
    EnrollmentFactory,
    LessonFactory,
    PublishedCourseFactory,
    UserFactory,
)
from tests.factories.lms import QuizFactory

pytestmark = pytest.mark.django_db


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


def _build_publishable_quiz(course, *, passing_score, certificate_required: bool):
    quiz = QuizFactory(
        course=course,
        passing_score=passing_score,
        status=QuizStatus.DRAFT,
        max_attempts=2,
        retake_delay_days=0,
        is_required_for_certificate=certificate_required,
    )
    q1 = QuizQuestion.objects.create(quiz=quiz, text="سؤال یک", order=1, weight=Decimal("1.00"))
    QuizOption.objects.create(question=q1, text="غلط", order=1, is_correct=False)
    correct1 = QuizOption.objects.create(question=q1, text="درست", order=2, is_correct=True)
    publish_quiz(quiz=quiz)
    return quiz, {q1.pk: correct1.pk}


# ---------------------------------------------------------------------------
# Model content-type helpers
# ---------------------------------------------------------------------------


class TestLessonContentTypeModel:
    def test_video_lesson_is_media_and_needs_media_content(self) -> None:
        video = LessonFactory(video_url="https://cdn.example.com/v.mp4")
        assert video.content_type == LessonContentType.VIDEO
        assert video.is_media_type is True
        assert video.supports_manual_completion is False
        assert video.has_required_content() is True

    def test_document_and_article_are_manual_completion_types(self) -> None:
        document = DocumentLessonFactory()
        article = ArticleLessonFactory()
        assert document.supports_manual_completion is True
        assert article.supports_manual_completion is True
        assert document.is_media_type is False
        assert document.has_required_content() is True
        assert article.has_required_content() is True

    def test_content_required_matches_declared_type(self) -> None:
        empty_doc = Lesson.objects.create(
            course=PublishedCourseFactory(),
            title="سند خالی",
            content_type=LessonContentType.DOCUMENT,
            order=99,
        )
        assert empty_doc.has_required_content() is False
        empty_video = LessonFactory(video_url="", embed_url="")
        assert empty_video.has_required_content() is False


# ---------------------------------------------------------------------------
# Publish gate: no empty-content lesson can be published
# ---------------------------------------------------------------------------


class TestCoursePublishContentGate:
    def test_publish_blocked_when_document_lesson_missing_file(self) -> None:
        course = PublishedCourseFactory()
        DocumentLessonFactory(course=course, order=1, document_file=None, document_title="")
        with pytest.raises(CourseInvalidStateError):
            publish_course(course=course)

    def test_publish_ok_when_all_lessons_have_content(self) -> None:
        course = PublishedCourseFactory()
        DocumentLessonFactory(course=course, order=1)
        ArticleLessonFactory(course=course, order=2)
        LessonFactory(course=course, order=3, video_url="https://cdn.example.com/lesson.mp4")
        course = publish_course(course=course)
        assert course.status == "published"
        assert course.published_at is not None

    def test_publish_allows_zero_lessons_for_backward_compatibility(self) -> None:
        # انتشار دورهٔ هنوز-خالی نباید در این مرحله بشکند (سابقاً مجاز بود؛
        # فقط جلسه‌های موجود اعتبارسنجی می‌شوند، نه الزام به وجود جلسه).
        course = PublishedCourseFactory()
        course.status = "draft"
        course.published_at = None
        course.save()
        course = publish_course(course=course)
        assert course.published_at is not None

    def test_admin_publish_endpoint_returns_400_on_incomplete_lesson(self) -> None:
        from tests.factories import AdminUserFactory

        admin = AdminUserFactory()
        course = PublishedCourseFactory()
        course.status = "draft"
        course.published_at = None
        course.save()
        DocumentLessonFactory(course=course, order=1, document_file=None)
        response = _client_for(admin).post(
            reverse("lms:admin-course-publish", kwargs={"course_id": course.pk})
        )
        assert response.status_code == status.HTTP_400_BAD_REQUEST


# ---------------------------------------------------------------------------
# Manual completion for document/article lessons
# ---------------------------------------------------------------------------


class TestManualCompletionProgress:
    def test_mark_completed_finalizes_document_and_enrollment(self) -> None:
        course = DocumentLessonFactory().course
        DocumentLessonFactory(course=course, order=2)
        publish_course(course=course)
        enrollment = EnrollmentFactory(course=course, status=EnrollmentStatus.ACTIVE)

        first = Lesson.objects.filter(course=course).order_by("order").first()
        second = Lesson.objects.filter(course=course).order_by("order").last()
        update_lesson_progress(
            enrollment=enrollment, lesson=first, mark_completed=True, media_opened=True
        )
        enrollment.refresh_from_db()
        assert enrollment.status == EnrollmentStatus.ACTIVE  # یکی از دو جلسه
        update_lesson_progress(
            enrollment=enrollment, lesson=second, mark_completed=True, media_opened=True
        )
        enrollment.refresh_from_db()
        progress = LessonProgress.objects.get(enrollment=enrollment, lesson=second)
        assert progress.is_completed is True
        assert progress.progress_percent == Decimal("100.00")
        assert enrollment.status == EnrollmentStatus.COMPLETED

    def test_media_lesson_rejects_manual_completion(self) -> None:
        course = PublishedCourseFactory()
        lesson = LessonFactory(
            course=course, order=1, duration_seconds=100, video_url="https://cdn.example.com/v.mp4"
        )
        sync_course_counters(course=course)
        enrollment = EnrollmentFactory(course=course, status=EnrollmentStatus.ACTIVE)
        with pytest.raises(LessonCompletionModeError):
            update_lesson_progress(enrollment=enrollment, lesson=lesson, mark_completed=True)

    def test_document_partial_reading_stays_incomplete(self) -> None:
        course = PublishedCourseFactory()
        lesson = DocumentLessonFactory(course=course, order=1, duration_seconds=600)
        sync_course_counters(course=course)
        enrollment = EnrollmentFactory(course=course, status=EnrollmentStatus.ACTIVE)
        progress = update_lesson_progress(enrollment=enrollment, lesson=lesson, watched_seconds=540)
        assert progress.is_completed is False
        assert progress.progress_percent == Decimal("0.00")

    def test_progress_endpoint_accepts_mark_completed_for_document(self) -> None:
        course = PublishedCourseFactory()
        lesson = DocumentLessonFactory(course=course, order=1, duration_seconds=0)
        sync_course_counters(course=course)
        user = UserFactory()
        _enroll(user, course)
        response = _client_for(user).post(
            reverse("lms:lesson-progress-update", kwargs={"lesson_id": lesson.pk}),
            data={"mark_completed": True, "media_opened": True},
            format="json",
        )
        assert response.status_code == status.HTTP_200_OK
        assert response.data["data"]["is_completed"] is True

    def test_progress_endpoint_rejects_no_signal(self) -> None:
        course = PublishedCourseFactory()
        lesson = DocumentLessonFactory(course=course, order=1, duration_seconds=0)
        user = UserFactory()
        _enroll(user, course)
        response = _client_for(user).post(
            reverse("lms:lesson-progress-update", kwargs={"lesson_id": lesson.pk}),
            data={},
            format="json",
        )
        assert response.status_code == status.HTTP_400_BAD_REQUEST


# ---------------------------------------------------------------------------
# Document / Article media access
# ---------------------------------------------------------------------------


class TestDocumentArticleMediaAccess:
    def test_enrolled_user_gets_document_signed_url(self) -> None:
        course = PublishedCourseFactory()
        lesson = DocumentLessonFactory(course=course, order=1)
        enrollment = EnrollmentFactory(course=course)
        payload = build_lesson_media_access(
            lesson=lesson, user=enrollment.user, media_kind="document"
        )
        assert payload["media_kind"] == "document"
        assert payload["provider"] == "uploaded_file"
        assert payload["expires_in_seconds"] == 12 * 60 * 60
        assert payload["url"].startswith(f"lms/lessons/{lesson.pk}/media/document/stream/?t=")
        assert not payload["url"].startswith("/media/")
        assert payload["title"] == "سند جلسه"

    def test_enrolled_user_gets_inline_article_body(self) -> None:
        course = PublishedCourseFactory()
        lesson = ArticleLessonFactory(course=course, order=1)
        enrollment = EnrollmentFactory(course=course)
        payload = build_lesson_media_access(
            lesson=lesson, user=enrollment.user, media_kind="article"
        )
        assert payload["provider"] == "inline"
        assert payload["url"] == ""
        assert "متن کامل جلسه" in payload["body"]

    def test_non_enrolled_user_cannot_access_document(self) -> None:
        lesson = DocumentLessonFactory(is_preview=False)
        with pytest.raises(LessonMediaAccessError):
            build_lesson_media_access(lesson=lesson, user=UserFactory(), media_kind="document")

    def test_document_kind_on_video_lesson_is_unavailable(self) -> None:
        course = PublishedCourseFactory()
        lesson = LessonFactory(course=course, order=1, video_url="https://x/y.mp4")
        enrollment = EnrollmentFactory(course=course)
        with pytest.raises(LessonMediaUnavailableError):
            build_lesson_media_access(lesson=lesson, user=enrollment.user, media_kind="document")


# ---------------------------------------------------------------------------
# Public catalog serializer must not leak private content fields
# ---------------------------------------------------------------------------


class TestCatalogLeakGuard:
    def test_lesson_summary_serializer_omits_document_and_article_fields(self) -> None:
        lesson = DocumentLessonFactory()
        data = LessonSummarySerializer(lesson).data
        assert data["content_type"] == LessonContentType.DOCUMENT
        assert "document_file" not in data
        assert "article_body" not in data


# ---------------------------------------------------------------------------
# Certificate policy enforced at quiz submit
# ---------------------------------------------------------------------------


class TestCertificatePolicyEnforcement:
    def test_quiz_with_certificate_required_issues_certificate_on_pass(self) -> None:
        course = PublishedCourseFactory()
        user = UserFactory()
        _enroll(user, course)
        _quiz, correct = _build_publishable_quiz(
            course, passing_score=Decimal("1.00"), certificate_required=True
        )
        attempt_id = (
            _client_for(user)
            .post(reverse("lms:quiz-attempt-start", kwargs={"slug": course.slug}))
            .data["data"]["id"]
        )
        answers = [{"question_id": q, "selected_option_id": o} for q, o in correct.items()]
        submit = _client_for(user).post(
            reverse("lms:quiz-attempt-submit", kwargs={"attempt_id": attempt_id}),
            data={"answers": answers},
            format="json",
        )
        assert submit.data["data"]["status"] == "passed"
        from apps.lms.models import Certificate

        assert Certificate.objects.filter(user=user, course=course).exists() is True

    def test_quiz_without_certificate_required_completes_without_certificate(self) -> None:
        course = PublishedCourseFactory()
        user = UserFactory()
        enrollment = _enroll(user, course)
        _quiz, correct = _build_publishable_quiz(
            course, passing_score=Decimal("1.00"), certificate_required=False
        )
        start = _client_for(user).post(
            reverse("lms:quiz-attempt-start", kwargs={"slug": course.slug})
        )
        attempt_id = start.data["data"]["id"]
        answers = [{"question_id": q, "selected_option_id": o} for q, o in correct.items()]
        submit = _client_for(user).post(
            reverse("lms:quiz-attempt-submit", kwargs={"attempt_id": attempt_id}),
            data={"answers": answers},
            format="json",
        )
        assert submit.data["data"]["status"] == "passed"
        from apps.lms.models import Certificate

        assert Certificate.objects.filter(user=user, course=course).exists() is False
        enrollment.refresh_from_db()
        assert enrollment.status == EnrollmentStatus.COMPLETED

    def test_fail_never_issues_certificate_regardless_of_flag(self) -> None:
        course = PublishedCourseFactory()
        user = UserFactory()
        _enroll(user, course)
        _quiz, correct = _build_publishable_quiz(
            course, passing_score=Decimal("20.00"), certificate_required=True
        )
        attempt_id = (
            _client_for(user)
            .post(reverse("lms:quiz-attempt-start", kwargs={"slug": course.slug}))
            .data["data"]["id"]
        )
        # پاسخ نادرست: همان گزینهٔ درستِ سؤال ۱ ولی passing=۲۰ و یک سؤال ⇒ درست ⇒
        # قبول. برای رد، گزینه نادرست می‌سازیم.
        q = next(iter(correct))
        wrong = QuizOption.objects.filter(question=q, is_correct=False).first()
        submit = _client_for(user).post(
            reverse("lms:quiz-attempt-submit", kwargs={"attempt_id": attempt_id}),
            data={"answers": [{"question_id": q, "selected_option_id": wrong.pk}]},
            format="json",
        )
        assert submit.data["data"]["status"] == "failed"
        from apps.lms.models import Certificate

        assert Certificate.objects.filter(user=user, course=course).exists() is False


class TestDocumentValidator:
    """وِالیدیتور مجوزهای فایل سند — هم نوع‌های مجاز، هم ردِ اجرایی‌ها."""

    def test_executable_extension_is_rejected(self) -> None:
        from django.core.exceptions import ValidationError as DjangoValidationError

        from apps.lms.validators import validate_lesson_document_file

        bad = SimpleUploadedFile("shell.exe", b"MZ...", content_type="application/octet-stream")
        with pytest.raises(DjangoValidationError):
            validate_lesson_document_file(bad)

    def test_oversized_document_is_rejected(self) -> None:
        from django.core.exceptions import ValidationError as DjangoValidationError

        from apps.lms.validators import MAX_LESSON_DOCUMENT_MB, validate_lesson_document_file

        class _BigPdf:  # فقط .name و .size مصرف می‌شوند؛ ۱۰۰ مگابایت واقعی نمی‌خواهیم
            name = "big.pdf"
            size = MAX_LESSON_DOCUMENT_MB * 1024 * 1024 + 1

        with pytest.raises(DjangoValidationError):
            validate_lesson_document_file(_BigPdf())

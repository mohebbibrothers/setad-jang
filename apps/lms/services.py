"""Business services for LMS mutations.

All LMS state changes go through this module so views stay orchestration-only and
state transitions remain auditable, transactional, and testable.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from django.core.files.base import ContentFile
from django.db import transaction
from django.db.models import Count, Sum
from django.utils import timezone

from apps.lms.choices import (
    BadgeLevel,
    CertificateStatus,
    CourseStatus,
    EnrollmentStatus,
    VideoProcessingStatus,
)
from apps.lms.models import (
    Certificate,
    Course,
    Enrollment,
    Lesson,
    LessonProgress,
    LessonVideoProcessingJob,
    LMSCategory,
    LMSUserSkill,
)


class LMSServiceError(Exception):
    """Base service-layer exception for LMS domain errors."""


class LMSProfileIncompleteError(LMSServiceError):
    """Raised when a user profile misses required enrollment fields."""


class CourseNotEnrollabeError(LMSServiceError):
    """Raised when a course cannot accept enrollments."""


class CourseInvalidStateError(LMSServiceError):
    """Raised when a course lifecycle transition is not valid."""


class EnrollmentNotActiveError(LMSServiceError):
    """Raised when progress is attempted for a non-active enrollment."""


class LessonNotInEnrollmentCourseError(LMSServiceError):
    """Raised when a lesson does not belong to the user's enrolled course."""


class LessonMediaAccessError(LMSServiceError):
    """Raised when lesson media cannot be accessed by a user."""


class LessonMediaUnavailableError(LMSServiceError):
    """Raised when requested lesson media does not exist."""


class VideoProcessingJobError(LMSServiceError):
    """Raised when a lesson video processing job cannot be executed."""


LESSON_COMPLETION_THRESHOLD_PERCENT = Decimal("90.00")


@transaction.atomic
def sync_course_counters(*, course: Course) -> Course:
    """Recalculate denormalized course counters from source-of-truth rows."""
    lesson_aggregates = Lesson.objects.filter(course=course, is_active=True).aggregate(
        duration=Sum("duration_seconds"),
        lessons=Count("id"),
    )
    course.estimated_duration_seconds = lesson_aggregates["duration"] or 0
    course.lessons_count = lesson_aggregates["lessons"] or 0
    course.enrollments_count = Enrollment.objects.filter(
        course=course,
        status=EnrollmentStatus.ACTIVE,
    ).count()
    course.graduates_count = Enrollment.objects.filter(
        course=course,
        status=EnrollmentStatus.COMPLETED,
    ).count()
    course.save(
        update_fields=[
            "estimated_duration_seconds",
            "lessons_count",
            "enrollments_count",
            "graduates_count",
            "updated_at",
        ]
    )
    return course


def ensure_user_can_enroll(user: Any) -> None:
    """Validate minimum identity/profile requirements for LMS enrollment."""
    profile = getattr(user, "profile", None)
    if not (
        getattr(user, "first_name", "").strip()
        and getattr(user, "last_name", "").strip()
        and profile
        and getattr(profile, "national_code", "").strip()
    ):
        raise LMSProfileIncompleteError(
            "برای ثبت‌نام در دوره باید نام، نام خانوادگی و کد ملی را در پروفایل تکمیل کنید."
        )


@transaction.atomic
def create_category(*, title: str, description: str = "", icon: str = "", order: int = 0) -> LMSCategory:
    """Create an admin-managed LMS category."""
    return LMSCategory.objects.create(title=title, description=description, icon=icon, order=order)


@transaction.atomic
def update_category(*, category: LMSCategory, **fields: Any) -> LMSCategory:
    """Update mutable category fields."""
    allowed = {"title", "description", "icon", "cover_image", "order", "is_active"}
    update_fields: list[str] = []
    for field, value in fields.items():
        if field in allowed:
            setattr(category, field, value)
            update_fields.append(field)
    if update_fields:
        update_fields.append("updated_at")
        category.save(update_fields=list(set(update_fields)))
    return category


@transaction.atomic
def delete_category(*, category: LMSCategory) -> None:
    """Soft-delete a category; existing courses are preserved."""
    category.soft_delete()


@transaction.atomic
def create_course(*, category: LMSCategory, **fields: Any) -> Course:
    """Create a course in draft state."""
    course = Course.objects.create(category=category, status=CourseStatus.DRAFT, **fields)
    sync_course_counters(course=course)
    return course


@transaction.atomic
def update_course(*, course: Course, **fields: Any) -> Course:
    """Update mutable course fields."""
    allowed = {
        "category",
        "title",
        "subtitle",
        "short_description",
        "description",
        "cover_image",
        "instructor_name",
        "instructor_bio",
        "instructor_avatar",
        "level",
        "language",
        "is_featured",
        "intro_video_url",
        "is_active",
    }
    update_fields: list[str] = []
    for field, value in fields.items():
        if field in allowed:
            setattr(course, field, value)
            update_fields.append(field)
    if update_fields:
        update_fields.append("updated_at")
        course.save(update_fields=list(set(update_fields)))
    return course


@transaction.atomic
def publish_course(*, course: Course) -> Course:
    """Publish a course and set published_at idempotently."""
    if course.status != CourseStatus.PUBLISHED:
        course.status = CourseStatus.PUBLISHED
        course.published_at = timezone.now()
        course.archived_at = None
        course.save(update_fields=["status", "published_at", "archived_at", "updated_at"])
    return course


@transaction.atomic
def archive_course(*, course: Course) -> Course:
    """Archive a course and hide it from public catalog."""
    if course.status != CourseStatus.ARCHIVED:
        course.status = CourseStatus.ARCHIVED
        course.archived_at = timezone.now()
        course.save(update_fields=["status", "archived_at", "updated_at"])
    return course


@transaction.atomic
def delete_course(*, course: Course) -> None:
    """Soft-delete a course and hide it from public catalog."""
    course.soft_delete()


@transaction.atomic
def create_lesson(*, course: Course, **fields: Any) -> Lesson:
    """Create a lesson and resync course counters."""
    lesson = Lesson.objects.create(course=course, **fields)
    sync_course_counters(course=course)
    return lesson


@transaction.atomic
def update_lesson(*, lesson: Lesson, **fields: Any) -> Lesson:
    """Update lesson fields and resync course counters if needed."""
    allowed = {
        "title",
        "description",
        "order",
        "video_provider",
        "video_url",
        "embed_url",
        "video_file",
        "duration_seconds",
        "transcript",
        "summary",
        "homework",
        "attachment_file",
        "attachment_title",
        "is_preview",
        "is_active",
        "published_at",
    }
    update_fields: list[str] = []
    for field, value in fields.items():
        if field in allowed:
            setattr(lesson, field, value)
            update_fields.append(field)
    if update_fields:
        update_fields.append("updated_at")
        lesson.save(update_fields=list(set(update_fields)))
        if "duration_seconds" in update_fields or "is_active" in update_fields:
            sync_course_counters(course=lesson.course)
    return lesson


@transaction.atomic
def delete_lesson(*, lesson: Lesson) -> None:
    """Soft-delete a lesson and resync course counters."""
    course = lesson.course
    lesson.soft_delete()
    sync_course_counters(course=course)


@transaction.atomic
def enroll_user_in_course(*, user: Any, course: Course) -> tuple[Enrollment, bool]:
    """Enroll a user in a published free course idempotently."""
    ensure_user_can_enroll(user)
    if not course.is_published:
        raise CourseNotEnrollabeError("این دوره در حال حاضر قابل ثبت‌نام نیست.")
    enrollment, created = Enrollment.objects.get_or_create(
        user=user,
        course=course,
        defaults={
            "status": EnrollmentStatus.ACTIVE,
            "total_seconds_snapshot": course.estimated_duration_seconds,
        },
    )
    if created:
        sync_course_counters(course=course)
    return enrollment, created


def badge_level_for_score(score: Decimal) -> str:
    """Map certificate score to a badge level."""
    if score >= Decimal("19.50"):
        return BadgeLevel.DISTINCTION
    if score >= Decimal("18.00"):
        return BadgeLevel.GOLD
    if score >= Decimal("16.00"):
        return BadgeLevel.SILVER
    return BadgeLevel.BRONZE


@transaction.atomic
def create_skill_for_certificate(*, certificate) -> LMSUserSkill:
    """Create or return the profile-visible skill granted by a certificate."""
    skill, created = LMSUserSkill.objects.get_or_create(
        user=certificate.user,
        course=certificate.course,
        defaults={
            "certificate": certificate,
            "title": certificate.course_title_snapshot,
            "badge_level": badge_level_for_score(certificate.score_out_of_20),
        },
    )
    if created:
        from apps.notifications.domain import notify_lms_certificate_issued

        notify_lms_certificate_issued(certificate=certificate)
    return skill


# ============================================================
# Video processing jobs
# ============================================================

@transaction.atomic
def request_lesson_video_processing(*, lesson: Lesson, requested_by: Any | None = None) -> LessonVideoProcessingJob:
    """Queue an idempotent video processing job for an uploaded lesson video."""
    if not lesson.video_file:
        raise VideoProcessingJobError("برای این جلسه فایل ویدئویی آپلود نشده است.")
    existing = lesson.video_processing_jobs.filter(status__in=[VideoProcessingStatus.QUEUED, VideoProcessingStatus.PROCESSING]).first()
    if existing is not None:
        return existing
    return LessonVideoProcessingJob.objects.create(
        lesson=lesson,
        requested_by=requested_by if getattr(requested_by, "pk", None) else None,
        provider="noop",
        source_file_name=getattr(lesson.video_file, "name", "") or "",
        metadata={"provider_mode": "noop", "reason": "processing infrastructure not configured"},
    )


@transaction.atomic
def process_lesson_video_job(*, job: LessonVideoProcessingJob) -> LessonVideoProcessingJob:
    """Process a lesson video job with a safe no-op/local provider contract."""
    locked = LessonVideoProcessingJob.objects.select_for_update().select_related("lesson").get(pk=job.pk)
    if locked.status == VideoProcessingStatus.COMPLETED:
        return locked
    if locked.status not in {VideoProcessingStatus.QUEUED, VideoProcessingStatus.FAILED}:
        raise VideoProcessingJobError("Job در وضعیت قابل پردازش نیست.")
    locked.status = VideoProcessingStatus.PROCESSING
    locked.started_at = timezone.now()
    locked.save(update_fields=["status", "started_at", "updated_at"])
    lesson = locked.lesson
    locked.output_video_url = lesson.video_file.url if lesson.video_file else ""
    locked.thumbnail_url = ""
    locked.duration_seconds = lesson.duration_seconds
    locked.status = VideoProcessingStatus.COMPLETED
    locked.completed_at = timezone.now()
    locked.metadata = {
        **locked.metadata,
        "processed_by": "noop_local_provider",
        "output_video_url_source": "lesson.video_file.url",
    }
    locked.error_message = ""
    locked.save(update_fields=["output_video_url", "thumbnail_url", "duration_seconds", "status", "completed_at", "metadata", "error_message", "updated_at"])
    return locked


@transaction.atomic
def fail_lesson_video_job(*, job: LessonVideoProcessingJob, error_message: str) -> LessonVideoProcessingJob:
    """Mark a video processing job as failed with a safe error message."""
    locked = LessonVideoProcessingJob.objects.select_for_update().get(pk=job.pk)
    locked.status = VideoProcessingStatus.FAILED
    locked.error_message = error_message[:500]
    locked.save(update_fields=["status", "error_message", "updated_at"])
    return locked


# ============================================================
# Secure media access
# ============================================================


def build_lesson_media_access(*, lesson: Lesson, user: Any, media_kind: str) -> dict[str, Any]:
    """Return a signed/CDN-ready media access payload for an enrolled user.

    For S3 private storage, Django storage `.url` returns a signed URL. For local
    storage it returns a development URL. The view layer only orchestrates this
    service and records audit.
    """
    enrollment = Enrollment.objects.filter(
        user=user,
        course=lesson.course,
        status__in=[EnrollmentStatus.ACTIVE, EnrollmentStatus.COMPLETED],
    ).first()
    if enrollment is None and not lesson.is_preview:
        raise LessonMediaAccessError("برای دسترسی به رسانه این جلسه باید در کلاس ثبت‌نام کرده باشید.")
    if media_kind == "video":
        if lesson.video_file:
            return {
                "media_kind": "video",
                "provider": "uploaded_file",
                "url": lesson.video_file.url,
                "expires_in_seconds": 600,
                "lesson_id": lesson.pk,
                "course_id": lesson.course_id,
            }
        if lesson.video_url:
            return {"media_kind": "video", "provider": "direct_url", "url": lesson.video_url, "expires_in_seconds": None, "lesson_id": lesson.pk, "course_id": lesson.course_id}
        if lesson.embed_url:
            return {"media_kind": "video", "provider": "embed", "url": lesson.embed_url, "expires_in_seconds": None, "lesson_id": lesson.pk, "course_id": lesson.course_id}
    if media_kind == "attachment" and lesson.attachment_file:
        return {
            "media_kind": "attachment",
            "provider": "uploaded_file",
            "url": lesson.attachment_file.url,
            "expires_in_seconds": 600,
            "lesson_id": lesson.pk,
            "course_id": lesson.course_id,
            "title": lesson.attachment_title,
        }
    raise LessonMediaUnavailableError("رسانه درخواستی برای این جلسه موجود نیست.")


# ============================================================
# Progress tracking
# ============================================================


def _calculate_percent(*, watched_seconds: int, duration_seconds: int) -> Decimal:
    """Calculate a 0..100 percentage with two decimals."""
    if duration_seconds <= 0:
        return Decimal("100.00") if watched_seconds > 0 else Decimal("0.00")
    value = (Decimal(watched_seconds) / Decimal(duration_seconds)) * Decimal("100")
    return min(value.quantize(Decimal("0.01")), Decimal("100.00"))


def _sync_enrollment_progress(*, enrollment: Enrollment) -> Enrollment:
    """Recalculate aggregate enrollment progress from lesson progress records."""
    aggregates = enrollment.lesson_progress.aggregate(
        watched=Sum("watched_seconds"),
        duration=Sum("duration_seconds_snapshot"),
    )
    watched = aggregates["watched"] or 0
    duration = enrollment.course.estimated_duration_seconds or aggregates["duration"] or 0
    enrollment.watched_seconds = watched
    enrollment.total_seconds_snapshot = duration
    enrollment.progress_percent = _calculate_percent(
        watched_seconds=watched,
        duration_seconds=duration,
    )

    active_lessons_count = Lesson.objects.filter(course=enrollment.course, is_active=True).count()
    completed_lessons_count = enrollment.lesson_progress.filter(is_completed=True).count()
    should_complete = active_lessons_count > 0 and completed_lessons_count >= active_lessons_count
    if should_complete and enrollment.status == EnrollmentStatus.ACTIVE:
        enrollment.status = EnrollmentStatus.COMPLETED
        enrollment.completed_at = timezone.now()

    enrollment.save(
        update_fields=[
            "watched_seconds",
            "total_seconds_snapshot",
            "progress_percent",
            "status",
            "completed_at",
            "updated_at",
        ]
    )
    return enrollment


@transaction.atomic
def update_lesson_progress(
    *,
    enrollment: Enrollment,
    lesson: Lesson,
    watched_seconds: int,
    last_position_seconds: int | None = None,
) -> LessonProgress:
    """
    Update lesson progress monotonically and sync aggregate enrollment progress.

    watched_seconds is monotonic: clients may send repeated/out-of-order progress
    events and the server keeps the maximum watched value. last_position_seconds
    represents current playback position and may move backwards for rewinds.
    """
    locked_enrollment = (
        Enrollment.objects.select_for_update()
        .select_related("course")
        .get(pk=enrollment.pk)
    )
    if locked_enrollment.status not in {EnrollmentStatus.ACTIVE, EnrollmentStatus.COMPLETED}:
        raise EnrollmentNotActiveError("ثبت‌نام شما برای ثبت پیشرفت فعال نیست.")

    locked_lesson = Lesson.objects.select_related("course").get(pk=lesson.pk)
    if locked_lesson.course_id != locked_enrollment.course_id:
        raise LessonNotInEnrollmentCourseError("این جلسه متعلق به کلاس ثبت‌نام‌شده شما نیست.")

    duration_snapshot = locked_lesson.duration_seconds or 0
    progress, _created = LessonProgress.objects.select_for_update().get_or_create(
        enrollment=locked_enrollment,
        lesson=locked_lesson,
        defaults={
            "duration_seconds_snapshot": duration_snapshot,
            "first_watched_at": timezone.now(),
        },
    )

    normalized_watched = max(0, watched_seconds)
    capped_watched = min(normalized_watched, duration_snapshot) if duration_snapshot else normalized_watched
    progress.watched_seconds = max(progress.watched_seconds, capped_watched)
    progress.duration_seconds_snapshot = duration_snapshot
    if last_position_seconds is not None:
        normalized_position = max(0, last_position_seconds)
        progress.last_position_seconds = (
            min(normalized_position, duration_snapshot) if duration_snapshot else normalized_position
        )
    else:
        progress.last_position_seconds = progress.watched_seconds

    progress.progress_percent = _calculate_percent(
        watched_seconds=progress.watched_seconds,
        duration_seconds=duration_snapshot,
    )
    progress.last_watched_at = timezone.now()
    if progress.first_watched_at is None:
        progress.first_watched_at = progress.last_watched_at

    if progress.progress_percent >= LESSON_COMPLETION_THRESHOLD_PERCENT:
        progress.is_completed = True
        if progress.completed_at is None:
            progress.completed_at = progress.last_watched_at

    progress.save(
        update_fields=[
            "watched_seconds",
            "duration_seconds_snapshot",
            "progress_percent",
            "is_completed",
            "last_position_seconds",
            "first_watched_at",
            "last_watched_at",
            "completed_at",
            "updated_at",
        ]
    )

    locked_enrollment.last_accessed_lesson = locked_lesson
    locked_enrollment.save(update_fields=["last_accessed_lesson", "updated_at"])
    _sync_enrollment_progress(enrollment=locked_enrollment)
    return progress


# ============================================================
# Lesson Q&A / Discussion
# ============================================================


class LMSDiscussionAccessError(LMSServiceError):
    """Raised when a user cannot interact with a lesson discussion."""


class LMSDiscussionModerationError(LMSServiceError):
    """Raised when a discussion moderation action is invalid."""


def ensure_user_enrolled_for_lesson(*, user: Any, lesson: Lesson) -> Enrollment:
    """Return active/completed enrollment that allows discussion access for a lesson."""
    enrollment = Enrollment.objects.filter(
        user=user,
        course=lesson.course,
        status__in=[EnrollmentStatus.ACTIVE, EnrollmentStatus.COMPLETED],
    ).first()
    if enrollment is None:
        raise LMSDiscussionAccessError("برای مشارکت در پرسش‌وپاسخ باید در این کلاس ثبت‌نام کرده باشید.")
    return enrollment


@transaction.atomic
def create_lesson_question(*, lesson: Lesson, user: Any, title: str, body: str):
    """Create an immediately visible lesson question for an enrolled user."""
    from apps.lms.choices import DiscussionStatus
    from apps.lms.models import LessonQuestion

    ensure_user_enrolled_for_lesson(user=user, lesson=lesson)
    question = LessonQuestion.objects.create(
        lesson=lesson,
        user=user,
        title=title.strip(),
        body=body.strip(),
        status=DiscussionStatus.VISIBLE,
        last_activity_at=timezone.now(),
    )
    return question


@transaction.atomic
def create_lesson_answer(*, question, user: Any, body: str, is_instructor_answer: bool = False):
    """Create an answer under a lesson question and update counters/activity."""
    from apps.lms.choices import DiscussionStatus
    from apps.lms.models import LessonAnswer

    ensure_user_enrolled_for_lesson(user=user, lesson=question.lesson)
    answer = LessonAnswer.objects.create(
        question=question,
        user=user,
        body=body.strip(),
        status=DiscussionStatus.VISIBLE,
        is_instructor_answer=is_instructor_answer,
    )
    question.answer_count = question.answers.filter(status=DiscussionStatus.VISIBLE).count()
    question.last_activity_at = timezone.now()
    question.save(update_fields=["answer_count", "last_activity_at", "updated_at"])
    return answer


@transaction.atomic
def accept_lesson_answer(*, question, answer, user: Any):
    """Mark an answer as accepted by question owner or admin/staff."""
    if answer.question_id != question.pk:
        raise LMSDiscussionModerationError("این پاسخ متعلق به سؤال انتخاب‌شده نیست.")
    is_admin = bool(getattr(user, "is_staff", False) or getattr(user, "is_superuser", False) or getattr(user, "role", "") == "admin")
    if question.user_id != user.pk and not is_admin:
        raise LMSDiscussionAccessError("فقط صاحب سؤال یا ادمین می‌تواند پاسخ را تأیید کند.")
    question.answers.update(is_accepted=False)
    answer.is_accepted = True
    answer.save(update_fields=["is_accepted", "updated_at"])
    question.is_answered = True
    question.save(update_fields=["is_answered", "updated_at"])
    return answer


@transaction.atomic
def report_lesson_question(*, question, reported_by: Any, reason: str, description: str = ""):
    """Report a question for admin moderation."""
    from apps.lms.models import LessonDiscussionReport

    ensure_user_enrolled_for_lesson(user=reported_by, lesson=question.lesson)
    return LessonDiscussionReport.objects.create(
        question=question,
        reported_by=reported_by,
        reason=reason.strip(),
        description=description.strip(),
    )


@transaction.atomic
def report_lesson_answer(*, answer, reported_by: Any, reason: str, description: str = ""):
    """Report an answer for admin moderation."""
    from apps.lms.models import LessonDiscussionReport

    ensure_user_enrolled_for_lesson(user=reported_by, lesson=answer.question.lesson)
    return LessonDiscussionReport.objects.create(
        answer=answer,
        reported_by=reported_by,
        reason=reason.strip(),
        description=description.strip(),
    )


@transaction.atomic
def moderate_lesson_question(*, question, status: str, is_pinned: bool | None = None) -> Any:
    """Admin moderation for a question."""
    from apps.lms.choices import DiscussionStatus

    if status not in DiscussionStatus.values:
        raise LMSDiscussionModerationError("وضعیت گفتگو نامعتبر است.")
    question.status = status
    if is_pinned is not None:
        question.is_pinned = is_pinned
    question.save(update_fields=["status", "is_pinned", "updated_at"])
    return question


@transaction.atomic
def moderate_lesson_answer(*, answer, status: str, is_accepted: bool | None = None) -> Any:
    """Admin moderation for an answer."""
    from apps.lms.choices import DiscussionStatus

    if status not in DiscussionStatus.values:
        raise LMSDiscussionModerationError("وضعیت گفتگو نامعتبر است.")
    answer.status = status
    if is_accepted is not None:
        if is_accepted:
            answer.question.answers.update(is_accepted=False)
            answer.question.is_answered = True
            answer.question.save(update_fields=["is_answered", "updated_at"])
        answer.is_accepted = is_accepted
    answer.save(update_fields=["status", "is_accepted", "updated_at"])
    return answer


@transaction.atomic
def review_discussion_report(*, report, reviewed_by: Any, status: str) -> Any:
    """Mark a discussion report as reviewed/rejected."""
    from apps.lms.choices import DiscussionReportStatus

    if status not in DiscussionReportStatus.values:
        raise LMSDiscussionModerationError("وضعیت گزارش نامعتبر است.")
    report.status = status
    report.reviewed_by = reviewed_by
    report.reviewed_at = timezone.now()
    report.save(update_fields=["status", "reviewed_by", "reviewed_at", "updated_at"])
    return report


# ============================================================
# Professional Quiz Engine
# ============================================================


class LMSQuizError(LMSServiceError):
    """Base exception for LMS quiz engine errors."""


class QuizNotAvailableError(LMSQuizError):
    """Raised when a quiz is not currently available to a user."""


class QuizValidationError(LMSQuizError):
    """Raised when quiz publishing or submission data is invalid."""


class QuizAttemptLockedError(LMSQuizError):
    """Raised when the user cannot start another quiz attempt."""


class QuizAttemptSubmissionError(LMSQuizError):
    """Raised when an attempt submission is invalid."""


@transaction.atomic
def create_or_update_quiz(*, course: Course, **fields: Any):
    """Create or update a course quiz in draft state."""
    from apps.lms.models import Quiz

    quiz, created = Quiz.objects.get_or_create(
        course=course,
        defaults={
            "title": fields.pop("title", f"آزمون {course.title}"),
            **fields,
        },
    )
    if not created:
        allowed = {
            "title",
            "description",
            "time_limit_minutes",
            "passing_score",
            "max_attempts",
            "retake_delay_days",
            "shuffle_questions",
            "shuffle_options",
            "show_result_immediately",
            "show_correct_answers_after_pass",
            "is_required_for_certificate",
        }
        update_fields: list[str] = []
        for field, value in fields.items():
            if field in allowed:
                setattr(quiz, field, value)
                update_fields.append(field)
        if update_fields:
            update_fields.append("updated_at")
            quiz.save(update_fields=list(set(update_fields)))
    return quiz, created


@transaction.atomic
def create_quiz_question(*, quiz, text: str, explanation: str = "", order: int = 1, weight: Decimal | int | str = 1):
    """Create a weighted single-choice question for an admin-managed quiz."""
    from apps.lms.models import QuizQuestion

    return QuizQuestion.objects.create(
        quiz=quiz,
        text=text,
        explanation=explanation,
        order=order,
        weight=weight,
    )


@transaction.atomic
def create_quiz_option(*, question, text: str, is_correct: bool = False, order: int = 1):
    """Create one answer option for an admin-managed quiz question."""
    from apps.lms.models import QuizOption

    return QuizOption.objects.create(
        question=question,
        text=text,
        is_correct=is_correct,
        order=order,
    )


def validate_quiz_publishable(*, quiz) -> None:
    """Validate that quiz has publishable question/option structure."""
    questions = list(quiz.questions.filter(is_active=True).prefetch_related("options"))
    if not questions:
        raise QuizValidationError("برای انتشار آزمون حداقل یک سؤال فعال لازم است.")
    for question in questions:
        options = list(question.options.filter(is_active=True))
        correct_count = sum(1 for option in options if option.is_correct)
        if len(options) < 2:
            raise QuizValidationError("هر سؤال آزمون باید حداقل دو گزینه فعال داشته باشد.")
        if correct_count != 1:
            raise QuizValidationError("هر سؤال چهارگزینه‌ای باید دقیقاً یک پاسخ صحیح داشته باشد.")


@transaction.atomic
def publish_quiz(*, quiz):
    """Publish a quiz after validating questions and correct options."""
    from apps.lms.choices import QuizStatus

    validate_quiz_publishable(quiz=quiz)
    quiz.status = QuizStatus.PUBLISHED
    quiz.published_at = timezone.now()
    quiz.save(update_fields=["status", "published_at", "updated_at"])
    return quiz


def _valid_unlocks_count(*, quiz, user) -> int:
    """Return extra attempts granted by currently valid admin unlocks."""
    from apps.lms.models import QuizUnlock

    now = timezone.now()
    return sum(
        unlock.extra_attempts
        for unlock in QuizUnlock.objects.filter(quiz=quiz, user=user)
        if unlock.valid_until is None or unlock.valid_until >= now
    )


def _next_attempt_number(*, quiz, user) -> int:
    """Return next attempt number for a user/quiz pair."""
    from apps.lms.models import QuizAttempt

    latest = QuizAttempt.objects.filter(quiz=quiz, user=user).order_by("-attempt_number").first()
    return (latest.attempt_number + 1) if latest else 1


def _build_attempt_snapshots(*, quiz) -> tuple[list[int], dict[str, list[int]]]:
    """Build randomized question and option order snapshots."""
    import random

    questions = list(quiz.questions.filter(is_active=True).prefetch_related("options").order_by("order", "id"))
    question_ids = [question.pk for question in questions]
    if quiz.shuffle_questions:
        random.shuffle(question_ids)

    option_order: dict[str, list[int]] = {}
    question_by_id = {question.pk: question for question in questions}
    for question_id in question_ids:
        options = list(question_by_id[question_id].options.filter(is_active=True).order_by("order", "id"))
        option_ids = [option.pk for option in options]
        if quiz.shuffle_options:
            random.shuffle(option_ids)
        option_order[str(question_id)] = option_ids
    return question_ids, option_order


@transaction.atomic
def start_quiz_attempt(*, quiz, user: Any):
    """Start a new quiz attempt with immutable question/option order snapshots."""
    from apps.lms.choices import QuizAttemptStatus, QuizStatus
    from apps.lms.models import Enrollment, QuizAttempt

    if quiz.status != QuizStatus.PUBLISHED or not quiz.is_active:
        raise QuizNotAvailableError("آزمون این کلاس در حال حاضر فعال نیست.")
    enrollment = Enrollment.objects.filter(
        user=user,
        course=quiz.course,
        status__in=[EnrollmentStatus.ACTIVE, EnrollmentStatus.COMPLETED],
    ).first()
    if enrollment is None:
        raise QuizNotAvailableError("برای شرکت در آزمون باید در کلاس ثبت‌نام کرده باشید.")

    existing_in_progress = QuizAttempt.objects.filter(
        quiz=quiz,
        user=user,
        status=QuizAttemptStatus.IN_PROGRESS,
    ).order_by("-started_at").first()
    now = timezone.now()
    if existing_in_progress is not None:
        if existing_in_progress.expires_at and existing_in_progress.expires_at <= now:
            existing_in_progress.status = QuizAttemptStatus.EXPIRED
            existing_in_progress.save(update_fields=["status", "updated_at"])
        else:
            return existing_in_progress, False

    terminal_attempts = QuizAttempt.objects.filter(quiz=quiz, user=user).exclude(
        status=QuizAttemptStatus.IN_PROGRESS,
    )
    if terminal_attempts.filter(is_passed=True).exists():
        raise QuizAttemptLockedError("شما قبلاً این آزمون را با موفقیت گذرانده‌اید.")

    attempt_number = _next_attempt_number(quiz=quiz, user=user)
    allowed_attempts = quiz.max_attempts + _valid_unlocks_count(quiz=quiz, user=user)
    if attempt_number > allowed_attempts:
        raise QuizAttemptLockedError("تعداد تلاش‌های مجاز شما برای این آزمون به پایان رسیده است.")

    last_failed = terminal_attempts.filter(status=QuizAttemptStatus.FAILED).order_by("-submitted_at").first()
    if last_failed is not None and attempt_number <= quiz.max_attempts:
        unlocks = _valid_unlocks_count(quiz=quiz, user=user)
        retry_at = last_failed.submitted_at + timezone.timedelta(days=quiz.retake_delay_days)
        if unlocks <= 0 and now < retry_at:
            raise QuizAttemptLockedError("تلاش بعدی شما هنوز فعال نشده است. لطفاً در زمان تعیین‌شده مراجعه کنید.")

    validate_quiz_publishable(quiz=quiz)
    question_snapshot, option_order_snapshot = _build_attempt_snapshots(quiz=quiz)
    expires_at = now + timezone.timedelta(minutes=quiz.time_limit_minutes)
    attempt = QuizAttempt.objects.create(
        quiz=quiz,
        course=quiz.course,
        enrollment=enrollment,
        user=user,
        attempt_number=attempt_number,
        status=QuizAttemptStatus.IN_PROGRESS,
        started_at=now,
        expires_at=expires_at,
        question_snapshot=question_snapshot,
        option_order_snapshot=option_order_snapshot,
    )
    return attempt, True


@transaction.atomic
def submit_quiz_attempt(*, attempt, answers: list[dict[str, int]]):
    """Submit a quiz attempt, persist answers, and calculate weighted score."""
    from apps.lms.choices import QuizAttemptStatus
    from apps.lms.models import QuizAnswer, QuizOption, QuizQuestion

    locked_attempt = (
        attempt.__class__.objects.select_for_update()
        .select_related("quiz")
        .get(pk=attempt.pk)
    )
    if locked_attempt.status != QuizAttemptStatus.IN_PROGRESS:
        raise QuizAttemptSubmissionError("این تلاش آزمون قابل ثبت پاسخ نیست.")
    now = timezone.now()
    if locked_attempt.expires_at and locked_attempt.expires_at <= now:
        locked_attempt.status = QuizAttemptStatus.EXPIRED
        locked_attempt.submitted_at = now
        locked_attempt.save(update_fields=["status", "submitted_at", "updated_at"])
        raise QuizAttemptSubmissionError("زمان آزمون به پایان رسیده است.")

    question_ids = [int(item) for item in locked_attempt.question_snapshot]
    allowed_options = {
        int(question_id): {int(option_id) for option_id in option_ids}
        for question_id, option_ids in locked_attempt.option_order_snapshot.items()
    }
    answer_map = {int(item["question_id"]): int(item["selected_option_id"]) for item in answers}
    if set(answer_map) != set(question_ids):
        raise QuizAttemptSubmissionError("باید به تمام سؤال‌های آزمون پاسخ دهید.")

    questions = {question.pk: question for question in QuizQuestion.objects.filter(pk__in=question_ids)}
    options = {option.pk: option for option in QuizOption.objects.filter(pk__in=answer_map.values())}

    total_weight = sum(Decimal(questions[qid].weight) for qid in question_ids)
    awarded_weight = Decimal("0.00")
    QuizAnswer.objects.filter(attempt=locked_attempt).delete()
    for question_id in question_ids:
        selected_option_id = answer_map[question_id]
        if selected_option_id not in allowed_options.get(question_id, set()):
            raise QuizAttemptSubmissionError("گزینه انتخاب‌شده معتبر نیست.")
        selected_option = options[selected_option_id]
        question = questions[question_id]
        is_correct = selected_option.question_id == question_id and selected_option.is_correct
        score_awarded = Decimal(question.weight) if is_correct else Decimal("0.00")
        awarded_weight += score_awarded
        QuizAnswer.objects.create(
            attempt=locked_attempt,
            question=question,
            selected_option=selected_option,
            is_correct=is_correct,
            weight=question.weight,
            score_awarded=score_awarded,
        )

    score_percent = (awarded_weight / total_weight * Decimal("100.00")) if total_weight else Decimal("0.00")
    score_out_of_20 = (awarded_weight / total_weight * Decimal("20.00")) if total_weight else Decimal("0.00")
    score_percent = score_percent.quantize(Decimal("0.01"))
    score_out_of_20 = score_out_of_20.quantize(Decimal("0.01"))
    is_passed = score_out_of_20 >= locked_attempt.quiz.passing_score

    locked_attempt.score_raw = awarded_weight
    locked_attempt.score_percent = score_percent
    locked_attempt.score_out_of_20 = score_out_of_20
    locked_attempt.is_passed = is_passed
    locked_attempt.status = QuizAttemptStatus.PASSED if is_passed else QuizAttemptStatus.FAILED
    locked_attempt.submitted_at = now
    locked_attempt.save(
        update_fields=[
            "score_raw",
            "score_percent",
            "score_out_of_20",
            "is_passed",
            "status",
            "submitted_at",
            "updated_at",
        ]
    )
    if is_passed:
        issue_certificate_for_attempt(attempt=locked_attempt)
    return locked_attempt


@transaction.atomic
def unlock_quiz_for_user(*, quiz, user: Any, unlocked_by: Any, reason: str, extra_attempts: int = 1, valid_until=None):
    """Grant manual extra attempts for a locked quiz user."""
    from apps.lms.models import QuizUnlock

    return QuizUnlock.objects.create(
        quiz=quiz,
        course=quiz.course,
        user=user,
        unlocked_by=unlocked_by,
        reason=reason,
        extra_attempts=extra_attempts,
        valid_until=valid_until,
    )


# ============================================================
# Certificates / Skills
# ============================================================


class CertificateIssueError(LMSServiceError):
    """Raised when certificate issuance is not allowed."""


@transaction.atomic
def issue_certificate_for_attempt(*, attempt) -> Certificate:
    """Issue or return certificate for a passed quiz attempt and grant skill/badge."""
    if not attempt.is_passed:
        raise CertificateIssueError("صدور مدرک فقط برای آزمون قبول‌شده امکان‌پذیر است.")

    from apps.lms.certificate import build_certificate_pdf_bytes

    user = attempt.user
    profile = getattr(user, "profile", None)
    full_name = getattr(user, "full_name", "") or f"{user.first_name} {user.last_name}".strip()
    national_code = getattr(profile, "national_code", "") if profile else ""
    gender = getattr(profile, "gender", "") if profile else ""

    certificate, created = Certificate.objects.get_or_create(
        user=user,
        course=attempt.course,
        defaults={
            "enrollment": attempt.enrollment,
            "quiz_attempt": attempt,
            "status": CertificateStatus.ISSUED,
            "full_name_snapshot": full_name,
            "gender_snapshot": gender,
            "national_code_snapshot": national_code,
            "course_title_snapshot": attempt.course.title,
            "instructor_name_snapshot": attempt.course.instructor_name,
            "score_out_of_20": attempt.score_out_of_20,
        },
    )
    if created and not certificate.pdf_file:
        certificate.pdf_file.save(
            f"certificate-{certificate.certificate_code}.pdf",
            ContentFile(build_certificate_pdf_bytes(certificate)),
            save=True,
        )

    create_skill_for_certificate(certificate=certificate)
    if attempt.enrollment.status != EnrollmentStatus.COMPLETED:
        attempt.enrollment.status = EnrollmentStatus.COMPLETED
        attempt.enrollment.completed_at = timezone.now()
        attempt.enrollment.save(update_fields=["status", "completed_at", "updated_at"])
        sync_course_counters(course=attempt.course)
    return certificate


@transaction.atomic
def revoke_certificate(*, certificate: Certificate, revoked_by: Any, reason: str) -> Certificate:
    """Revoke a certificate and hide derived skill from active profile views."""
    certificate.status = CertificateStatus.REVOKED
    certificate.revoked_by = revoked_by
    certificate.revoked_at = timezone.now()
    certificate.revocation_reason = reason
    certificate.save(update_fields=["status", "revoked_by", "revoked_at", "revocation_reason", "updated_at"])
    if hasattr(certificate, "skill"):
        certificate.skill.soft_delete()
    return certificate

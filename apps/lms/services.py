"""Business services for LMS mutations.

All LMS state changes go through this module so views stay orchestration-only and
state transitions remain auditable, transactional, and testable.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from django.db import transaction
from django.db.models import Count, Sum
from django.utils import timezone

from apps.lms.choices import BadgeLevel, CourseStatus, EnrollmentStatus
from apps.lms.models import Course, Enrollment, Lesson, LessonProgress, LMSCategory, LMSUserSkill


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
    skill, _created = LMSUserSkill.objects.get_or_create(
        user=certificate.user,
        course=certificate.course,
        defaults={
            "certificate": certificate,
            "title": certificate.course_title_snapshot,
            "badge_level": badge_level_for_score(certificate.score_out_of_20),
        },
    )
    return skill


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

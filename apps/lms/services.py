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
from apps.lms.models import Course, Enrollment, Lesson, LMSCategory, LMSUserSkill


class LMSServiceError(Exception):
    """Base service-layer exception for LMS domain errors."""


class LMSProfileIncompleteError(LMSServiceError):
    """Raised when a user profile misses required enrollment fields."""


class CourseNotEnrollabeError(LMSServiceError):
    """Raised when a course cannot accept enrollments."""


class CourseInvalidStateError(LMSServiceError):
    """Raised when a course lifecycle transition is not valid."""


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

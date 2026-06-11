"""
Selector layer for LMS read-side queries.

All read queries for public, user, and admin scopes pass through this module so
query optimization and visibility rules stay centralized.
"""

from __future__ import annotations

from django.db.models import Count, Prefetch, QuerySet

from apps.lms.models import Course, Enrollment, Lesson, LMSCategory, LMSUserSkill


def get_public_categories() -> QuerySet[LMSCategory]:
    """Return active LMS categories for public navigation."""
    return LMSCategory.objects.active().order_by("order", "title")


def get_public_category_by_slug(slug: str) -> LMSCategory | None:
    """Return one active category by slug."""
    return get_public_categories().filter(slug=slug).first()


def get_admin_categories() -> QuerySet[LMSCategory]:
    """Return all categories for admin management."""
    return LMSCategory.all_objects.annotate(courses_count=Count("courses")).order_by("order", "title")


def get_admin_category_by_id(category_id: int) -> LMSCategory | None:
    """Return one category for admin scope."""
    return LMSCategory.all_objects.filter(pk=category_id).first()


def get_public_courses() -> QuerySet[Course]:
    """Return published courses with category and active lessons prefetched."""
    return (
        Course.objects.published()
        .with_category()
        .prefetch_related(Prefetch("lessons", queryset=Lesson.objects.active().ordered()))
    )


def get_public_course_by_slug(slug: str) -> Course | None:
    """Return one published course by slug or None."""
    return get_public_courses().filter(slug=slug).first()


def get_admin_courses() -> QuerySet[Course]:
    """Return all courses for admin scope."""
    return Course.all_objects.with_category().prefetch_related("lessons").order_by("-created_at")


def get_admin_course_by_id(course_id: int) -> Course | None:
    """Return one course by id for admin scope."""
    return get_admin_courses().filter(pk=course_id).first()


def get_course_lessons(*, course: Course, public_only: bool = True) -> QuerySet[Lesson]:
    """Return lessons for a course in display order."""
    queryset = Lesson.objects if public_only else Lesson.all_objects
    queryset = queryset.filter(course=course)
    if public_only:
        queryset = queryset.active()
    return queryset.ordered()


def get_lesson_by_slug(*, course: Course, lesson_slug: str, public_only: bool = True) -> Lesson | None:
    """Return one lesson by course and slug."""
    return get_course_lessons(course=course, public_only=public_only).filter(slug=lesson_slug).first()


def get_admin_lesson_by_id(*, lesson_id: int) -> Lesson | None:
    """Return one lesson for admin scope."""
    return Lesson.all_objects.select_related("course").filter(pk=lesson_id).first()


def get_user_enrollments(*, user_id: int) -> QuerySet[Enrollment]:
    """Return enrollments owned by a user."""
    return (
        Enrollment.objects.select_related("course", "course__category", "last_accessed_lesson")
        .prefetch_related("lesson_progress__lesson")
        .filter(user_id=user_id)
    )


def get_user_enrollment_by_id(*, user_id: int, enrollment_id: int) -> Enrollment | None:
    """Return one enrollment with IDOR protection."""
    return get_user_enrollments(user_id=user_id).filter(pk=enrollment_id).first()


def get_user_skills(*, user_id: int) -> QuerySet[LMSUserSkill]:
    """Return skills visible on a user's profile."""
    return LMSUserSkill.objects.filter(user_id=user_id).select_related("course", "certificate")


def get_course_report_queryset(*, course_id: int) -> QuerySet[Enrollment]:
    """Return enrollment rows for admin course report."""
    return (
        Enrollment.objects.filter(course_id=course_id)
        .select_related("user", "course", "certificate")
        .order_by("-enrolled_at")
    )


def get_user_enrollment_for_course(*, user_id: int, course_id: int) -> Enrollment | None:
    """Return the user's enrollment for a course, if any."""
    return get_user_enrollments(user_id=user_id).filter(course_id=course_id).first()


def get_lesson_for_progress(*, lesson_id: int) -> Lesson | None:
    """Return an active lesson with course for progress updates."""
    return Lesson.objects.select_related("course").filter(pk=lesson_id, is_active=True).first()

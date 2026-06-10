"""
Selector layer for LMS read-side queries.

All read queries for public, user, and admin scopes pass through this module so
query optimization and visibility rules stay centralized.
"""

from __future__ import annotations

from django.db.models import Prefetch, QuerySet

from apps.lms.models import Course, Enrollment, Lesson, LMSCategory


def get_public_categories() -> QuerySet[LMSCategory]:
    """Return active LMS categories for public navigation."""
    return LMSCategory.objects.active().order_by("order", "title")


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


def get_user_enrollments(*, user_id: int) -> QuerySet[Enrollment]:
    """Return enrollments owned by a user."""
    return Enrollment.objects.select_related("course", "course__category").filter(user_id=user_id)

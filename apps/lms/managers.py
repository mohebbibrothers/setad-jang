"""
Managers and querysets for the LMS application.

The LMS domain has public scopes (published/active records), admin scopes
(including inactive/draft records), and user-owned scopes. Reusable querysets live
here to keep selectors concise and consistent.
"""

from __future__ import annotations

from django.db import models

from apps.lms.choices import CourseStatus


class LMSCategoryQuerySet(models.QuerySet):
    """QuerySet helpers for dynamic LMS categories."""

    def active(self) -> LMSCategoryQuerySet:
        """Return only active categories."""
        return self.filter(is_active=True)


class CourseQuerySet(models.QuerySet):
    """QuerySet helpers for courses."""

    def published(self) -> CourseQuerySet:
        """Return public courses that can be listed for users."""
        return self.filter(is_active=True, status=CourseStatus.PUBLISHED)

    def with_category(self) -> CourseQuerySet:
        """Apply category select_related for list/detail rendering."""
        return self.select_related("category")


class LessonQuerySet(models.QuerySet):
    """QuerySet helpers for lessons."""

    def active(self) -> LessonQuerySet:
        """Return only active lessons."""
        return self.filter(is_active=True)

    def ordered(self) -> LessonQuerySet:
        """Return lessons in course order."""
        return self.order_by("order", "id")


LMSCategoryManager = models.Manager.from_queryset(LMSCategoryQuerySet)
CourseManager = models.Manager.from_queryset(CourseQuerySet)
LessonManager = models.Manager.from_queryset(LessonQuerySet)

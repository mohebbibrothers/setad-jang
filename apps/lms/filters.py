"""
django-filter filtersets for LMS endpoints.

Filters are intentionally read-side only; authorization and business rules remain
in permissions/services.
"""

import django_filters
from django.db.models import Q

from apps.lms.choices import CourseLevel, CourseStatus
from apps.lms.models import Course, Enrollment, LMSCategory


class CoursePublicFilter(django_filters.FilterSet):
    """Filters for public course listing."""

    category = django_filters.CharFilter(field_name="category__slug", lookup_expr="iexact")
    level = django_filters.ChoiceFilter(choices=CourseLevel.choices)
    search = django_filters.CharFilter(method="filter_search")

    class Meta:
        model = Course
        fields: list[str] = []

    def filter_search(self, queryset, name, value):
        """Search course title, subtitle, description, and instructor."""
        return queryset.filter(
            Q(title__icontains=value)
            | Q(subtitle__icontains=value)
            | Q(short_description__icontains=value)
            | Q(description__icontains=value)
            | Q(instructor_name__icontains=value)
        )


class CourseAdminFilter(CoursePublicFilter):
    """Admin filters for all courses."""

    status = django_filters.ChoiceFilter(choices=CourseStatus.choices)
    is_active = django_filters.BooleanFilter()


class LMSCategoryAdminFilter(django_filters.FilterSet):
    """Admin filters for dynamic LMS categories."""

    is_active = django_filters.BooleanFilter()
    search = django_filters.CharFilter(field_name="title", lookup_expr="icontains")

    class Meta:
        model = LMSCategory
        fields: list[str] = []


class CourseReportEnrollmentFilter(django_filters.FilterSet):
    """Filters for admin course report enrollment rows."""

    status = django_filters.CharFilter(field_name="status", lookup_expr="exact")
    passed = django_filters.BooleanFilter(method="filter_passed")

    class Meta:
        model = Enrollment
        fields: list[str] = []

    def filter_passed(self, queryset, name, value):
        """Filter enrollments by certificate existence."""
        return queryset.filter(certificate__isnull=not value)

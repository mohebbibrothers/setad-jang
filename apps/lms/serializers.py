"""
DRF serializers for the LMS application.

API phases will expand this module. Phase 1 includes read serializers used by
admin previews and model-level tests.
"""

from rest_framework import serializers

from apps.lms.models import Course, Lesson, LMSCategory


class LMSCategorySerializer(serializers.ModelSerializer):
    """Public/admin category representation."""

    class Meta:
        model = LMSCategory
        fields = ("id", "title", "slug", "description", "order", "is_active")
        read_only_fields = ("id", "slug")


class LessonSummarySerializer(serializers.ModelSerializer):
    """Compact lesson representation for course detail pages."""

    class Meta:
        model = Lesson
        fields = ("id", "title", "slug", "order", "duration_seconds", "is_preview")
        read_only_fields = fields


class CourseSummarySerializer(serializers.ModelSerializer):
    """Compact course representation for course lists."""

    category = LMSCategorySerializer(read_only=True)

    class Meta:
        model = Course
        fields = (
            "id",
            "category",
            "title",
            "slug",
            "short_description",
            "instructor_name",
            "level",
            "status",
            "lessons_count",
            "estimated_duration_seconds",
            "enrollments_count",
            "graduates_count",
        )
        read_only_fields = fields

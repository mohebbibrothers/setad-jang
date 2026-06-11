"""DRF serializers for LMS catalog, admin management, enrollments, and reports."""

from rest_framework import serializers

from apps.lms.choices import DiscussionReportStatus, DiscussionStatus
from apps.lms.models import (
    Course,
    Enrollment,
    Lesson,
    LessonAnswer,
    LessonDiscussionReport,
    LessonProgress,
    LessonQuestion,
    LMSCategory,
    LMSUserSkill,
)


class LMSCategorySerializer(serializers.ModelSerializer):
    """Public/admin category representation."""

    class Meta:
        model = LMSCategory
        fields = ("id", "title", "slug", "description", "icon", "cover_image", "order", "is_active")
        read_only_fields = ("id", "slug")


class LMSCategoryCreateUpdateSerializer(serializers.Serializer):
    """Input serializer for category create/update."""

    title = serializers.CharField(max_length=150, required=False)
    description = serializers.CharField(required=False, allow_blank=True)
    icon = serializers.CharField(max_length=80, required=False, allow_blank=True)
    order = serializers.IntegerField(required=False, min_value=0)
    is_active = serializers.BooleanField(required=False)


class LessonSummarySerializer(serializers.ModelSerializer):
    """Compact lesson representation for course detail pages."""

    class Meta:
        model = Lesson
        fields = (
            "id",
            "title",
            "slug",
            "description",
            "order",
            "video_provider",
            "video_url",
            "embed_url",
            "duration_seconds",
            "summary",
            "attachment_title",
            "attachment_file",
            "is_preview",
        )
        read_only_fields = fields


class LessonCreateUpdateSerializer(serializers.Serializer):
    """Input serializer for lesson create/update."""

    title = serializers.CharField(max_length=255, required=False)
    description = serializers.CharField(required=False, allow_blank=True)
    order = serializers.IntegerField(required=False, min_value=1)
    video_provider = serializers.CharField(required=False)
    video_url = serializers.URLField(required=False, allow_blank=True)
    embed_url = serializers.URLField(required=False, allow_blank=True)
    video_file = serializers.FileField(required=False, allow_null=True)
    duration_seconds = serializers.IntegerField(required=False, min_value=0)
    transcript = serializers.CharField(required=False, allow_blank=True)
    summary = serializers.CharField(required=False, allow_blank=True)
    homework = serializers.CharField(required=False, allow_blank=True)
    attachment_file = serializers.FileField(required=False, allow_null=True)
    attachment_title = serializers.CharField(required=False, allow_blank=True)
    is_preview = serializers.BooleanField(required=False)
    is_active = serializers.BooleanField(required=False)


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
            "subtitle",
            "short_description",
            "instructor_name",
            "level",
            "status",
            "is_featured",
            "cover_image",
            "lessons_count",
            "estimated_duration_seconds",
            "enrollments_count",
            "graduates_count",
            "published_at",
        )
        read_only_fields = fields


class CourseDetailSerializer(CourseSummarySerializer):
    """Detailed course representation including active lessons."""

    lessons = LessonSummarySerializer(many=True, read_only=True)

    class Meta(CourseSummarySerializer.Meta):
        fields = (
            *CourseSummarySerializer.Meta.fields,
            "description",
            "instructor_bio",
            "instructor_avatar",
            "intro_video_url",
            "lessons",
        )


class CourseCreateUpdateSerializer(serializers.Serializer):
    """Input serializer for course create/update."""

    category_id = serializers.PrimaryKeyRelatedField(
        queryset=LMSCategory.objects.all(),
        source="category",
        required=False,
    )
    title = serializers.CharField(max_length=255, required=False)
    subtitle = serializers.CharField(max_length=300, required=False, allow_blank=True)
    short_description = serializers.CharField(max_length=500, required=False, allow_blank=True)
    description = serializers.CharField(required=False)
    cover_image = serializers.ImageField(required=False, allow_null=True)
    instructor_name = serializers.CharField(max_length=180, required=False)
    instructor_bio = serializers.CharField(required=False, allow_blank=True)
    instructor_avatar = serializers.ImageField(required=False, allow_null=True)
    level = serializers.CharField(required=False)
    language = serializers.CharField(max_length=30, required=False)
    is_featured = serializers.BooleanField(required=False)
    intro_video_url = serializers.URLField(required=False, allow_blank=True)
    is_active = serializers.BooleanField(required=False)


class EnrollmentSerializer(serializers.ModelSerializer):
    """User enrollment representation."""

    course = CourseSummarySerializer(read_only=True)

    class Meta:
        model = Enrollment
        fields = (
            "id",
            "course",
            "status",
            "enrolled_at",
            "completed_at",
            "progress_percent",
            "watched_seconds",
            "total_seconds_snapshot",
        )
        read_only_fields = fields


class CourseReportEnrollmentSerializer(serializers.ModelSerializer):
    """Admin report row for one course participant."""

    user_email = serializers.EmailField(source="user.email", read_only=True)
    full_name = serializers.CharField(source="user.full_name", read_only=True)
    certificate_code = serializers.CharField(source="certificate.certificate_code", read_only=True, allow_null=True)

    class Meta:
        model = Enrollment
        fields = (
            "id",
            "user_id",
            "user_email",
            "full_name",
            "status",
            "progress_percent",
            "watched_seconds",
            "total_seconds_snapshot",
            "certificate_code",
            "enrolled_at",
            "completed_at",
        )
        read_only_fields = fields


class CourseReportSerializer(serializers.Serializer):
    """Admin detailed course report serializer."""

    course = CourseSummarySerializer()
    summary = serializers.DictField()
    enrollments = CourseReportEnrollmentSerializer(many=True)


class LMSUserSkillSerializer(serializers.ModelSerializer):
    """Serializer for profile-visible LMS skills and badges."""

    course_title = serializers.CharField(source="course.title", read_only=True)
    certificate_code = serializers.CharField(source="certificate.certificate_code", read_only=True)

    class Meta:
        model = LMSUserSkill
        fields = ("id", "title", "slug", "badge_level", "course_title", "certificate_code", "issued_at")
        read_only_fields = fields


class LessonProgressUpdateSerializer(serializers.Serializer):
    """Input serializer for lesson progress updates."""

    watched_seconds = serializers.IntegerField(min_value=0)
    last_position_seconds = serializers.IntegerField(required=False, min_value=0)


class LessonProgressSerializer(serializers.ModelSerializer):
    """Output serializer for lesson progress state."""

    lesson = LessonSummarySerializer(read_only=True)

    class Meta:
        model = LessonProgress
        fields = (
            "id",
            "lesson",
            "watched_seconds",
            "duration_seconds_snapshot",
            "progress_percent",
            "is_completed",
            "last_position_seconds",
            "first_watched_at",
            "last_watched_at",
            "completed_at",
        )
        read_only_fields = fields


class EnrollmentDetailSerializer(EnrollmentSerializer):
    """Detailed enrollment serializer including lesson progress records."""

    lesson_progress = LessonProgressSerializer(many=True, read_only=True)

    class Meta(EnrollmentSerializer.Meta):
        fields = (*EnrollmentSerializer.Meta.fields, "last_accessed_lesson_id", "lesson_progress")


class LessonAnswerSerializer(serializers.ModelSerializer):
    """Output serializer for lesson answers."""

    user_id = serializers.IntegerField(read_only=True)
    user_display = serializers.SerializerMethodField()

    class Meta:
        model = LessonAnswer
        fields = (
            "id",
            "user_id",
            "user_display",
            "body",
            "status",
            "is_instructor_answer",
            "is_accepted",
            "created_at",
            "updated_at",
        )
        read_only_fields = fields

    def get_user_display(self, obj) -> str:
        """Return safe display name for answer author."""
        return getattr(obj.user, "full_name", "") or getattr(obj.user, "email", "کاربر")


class LessonQuestionSerializer(serializers.ModelSerializer):
    """Output serializer for lesson questions with nested visible answers."""

    user_id = serializers.IntegerField(read_only=True)
    user_display = serializers.SerializerMethodField()
    answers = LessonAnswerSerializer(many=True, read_only=True)

    class Meta:
        model = LessonQuestion
        fields = (
            "id",
            "lesson_id",
            "user_id",
            "user_display",
            "title",
            "body",
            "status",
            "is_pinned",
            "is_answered",
            "answer_count",
            "last_activity_at",
            "answers",
            "created_at",
        )
        read_only_fields = fields

    def get_user_display(self, obj) -> str:
        """Return safe display name for question author."""
        return getattr(obj.user, "full_name", "") or getattr(obj.user, "email", "کاربر")


class LessonQuestionCreateSerializer(serializers.Serializer):
    """Input serializer for creating a lesson question."""

    title = serializers.CharField(max_length=255)
    body = serializers.CharField()

    def validate_title(self, value: str) -> str:
        """Require meaningful question title."""
        value = value.strip()
        if len(value) < 5:
            raise serializers.ValidationError("عنوان سؤال باید حداقل ۵ کاراکتر باشد.")
        return value

    def validate_body(self, value: str) -> str:
        """Require meaningful question body."""
        value = value.strip()
        if len(value) < 10:
            raise serializers.ValidationError("متن سؤال باید حداقل ۱۰ کاراکتر باشد.")
        return value


class LessonAnswerCreateSerializer(serializers.Serializer):
    """Input serializer for creating a lesson answer."""

    body = serializers.CharField()

    def validate_body(self, value: str) -> str:
        """Require meaningful answer body."""
        value = value.strip()
        if len(value) < 5:
            raise serializers.ValidationError("متن پاسخ باید حداقل ۵ کاراکتر باشد.")
        return value


class DiscussionReportCreateSerializer(serializers.Serializer):
    """Input serializer for reporting a question or answer."""

    reason = serializers.CharField(max_length=150)
    description = serializers.CharField(required=False, allow_blank=True, default="")


class DiscussionModerationSerializer(serializers.Serializer):
    """Input serializer for admin discussion moderation."""

    status = serializers.ChoiceField(choices=DiscussionStatus.choices)
    is_pinned = serializers.BooleanField(required=False)
    is_accepted = serializers.BooleanField(required=False)


class DiscussionReportReviewSerializer(serializers.Serializer):
    """Input serializer for admin report review."""

    status = serializers.ChoiceField(choices=DiscussionReportStatus.choices)


class DiscussionReportSerializer(serializers.ModelSerializer):
    """Output serializer for discussion reports."""

    class Meta:
        model = LessonDiscussionReport
        fields = (
            "id",
            "question_id",
            "answer_id",
            "reported_by_id",
            "reason",
            "description",
            "status",
            "reviewed_by_id",
            "reviewed_at",
            "created_at",
        )
        read_only_fields = fields

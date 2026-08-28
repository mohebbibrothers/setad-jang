"""
Django admin configuration for LMS.

Admin is designed for safe content management and reporting. Financial-like and
certificate records are read-focused where mutation must happen through services.
"""

from django.contrib import admin

from apps.lms.models import (
    Certificate,
    Course,
    Enrollment,
    LearningActivityStatement,
    Lesson,
    LessonAnswer,
    LessonDiscussionReport,
    LessonProgress,
    LessonQuestion,
    LessonVideoProcessingJob,
    LMSCategory,
    LMSUserSkill,
    Quiz,
    QuizAnswer,
    QuizAttempt,
    QuizOption,
    QuizQuestion,
    QuizUnlock,
)


class LessonInline(admin.TabularInline):
    """Inline lesson management inside course admin."""

    model = Lesson
    extra = 0
    fields = ("order", "title", "duration_seconds", "is_preview", "is_active")


@admin.register(LMSCategory)
class LMSCategoryAdmin(admin.ModelAdmin):
    """Admin CRUD for dynamic LMS categories."""

    list_display = ("title", "slug", "order", "is_active", "created_at")
    list_filter = ("is_active",)
    search_fields = ("title", "slug", "description")
    readonly_fields = ("slug", "created_at", "updated_at")
    ordering = ("order", "title")


@admin.register(Course)
class CourseAdmin(admin.ModelAdmin):
    """Admin management and reporting entrypoint for courses."""

    list_display = (
        "title",
        "category",
        "status",
        "instructor_name",
        "lessons_count",
        "enrollments_count",
        "graduates_count",
        "published_at",
    )
    list_filter = ("status", "level", "category", "is_featured", "is_active")
    search_fields = ("title", "slug", "instructor_name", "description")
    readonly_fields = (
        "slug",
        "lessons_count",
        "estimated_duration_seconds",
        "enrollments_count",
        "graduates_count",
        "average_rating",
        "published_at",
        "archived_at",
        "created_at",
        "updated_at",
    )
    inlines = [LessonInline]
    ordering = ("-created_at",)


@admin.register(Lesson)
class LessonAdmin(admin.ModelAdmin):
    """Admin management for course lessons."""

    list_display = ("title", "course", "order", "duration_seconds", "is_preview", "is_active")
    list_filter = ("is_active", "is_preview", "course")
    search_fields = ("title", "course__title", "description")
    readonly_fields = ("slug", "created_at", "updated_at")
    ordering = ("course", "order")


@admin.register(Enrollment)
class EnrollmentAdmin(admin.ModelAdmin):
    """Read-focused admin report for course participants."""

    list_display = (
        "id",
        "course",
        "user",
        "status",
        "progress_percent",
        "enrolled_at",
        "completed_at",
    )
    list_filter = ("status", "course")
    search_fields = ("course__title", "user__email", "user__phone_number")
    readonly_fields = (
        "course",
        "user",
        "status",
        "enrolled_at",
        "completed_at",
        "progress_percent",
        "watched_seconds",
        "total_seconds_snapshot",
        "last_accessed_lesson",
        "created_at",
        "updated_at",
    )

    def has_add_permission(self, request) -> bool:
        """Enrollments are created through service/API only."""
        return False

    def has_change_permission(self, request, obj=None) -> bool:
        """Enrollment state is service-controlled."""
        return False

    def has_delete_permission(self, request, obj=None) -> bool:
        """Deleting enrollments would break progress/certificate auditability."""
        return False


@admin.register(LessonProgress)
class LessonProgressAdmin(admin.ModelAdmin):
    """Read-only progress report per lesson."""

    list_display = ("enrollment", "lesson", "progress_percent", "watched_seconds", "is_completed")
    list_filter = ("is_completed", "lesson__course")
    search_fields = ("enrollment__user__email", "lesson__title")
    readonly_fields = [field.name for field in LessonProgress._meta.fields]

    def has_add_permission(self, request) -> bool:
        """Progress is written by service/API only."""
        return False

    def has_change_permission(self, request, obj=None) -> bool:
        """Progress mutation is service-controlled."""
        return False

    def has_delete_permission(self, request, obj=None) -> bool:
        """Progress history should not be deleted from admin."""
        return False


@admin.register(LessonQuestion)
class LessonQuestionAdmin(admin.ModelAdmin):
    """Admin moderation for lesson questions."""

    list_display = ("title", "lesson", "user", "status", "is_pinned", "is_answered", "answer_count")
    list_filter = ("status", "is_pinned", "is_answered", "lesson__course")
    search_fields = ("title", "body", "user__email", "lesson__title")


@admin.register(LessonAnswer)
class LessonAnswerAdmin(admin.ModelAdmin):
    """Admin moderation for lesson answers."""

    list_display = (
        "question",
        "user",
        "status",
        "is_instructor_answer",
        "is_accepted",
        "created_at",
    )
    list_filter = ("status", "is_instructor_answer", "is_accepted")
    search_fields = ("body", "user__email", "question__title")


@admin.register(LessonDiscussionReport)
class LessonDiscussionReportAdmin(admin.ModelAdmin):
    """Admin queue for reported Q&A content."""

    list_display = ("id", "reported_by", "reason", "status", "created_at", "reviewed_at")
    list_filter = ("status", "reason")
    search_fields = ("reason", "description", "reported_by__email")


class QuizQuestionInline(admin.TabularInline):
    """Inline quiz question admin preview."""

    model = QuizQuestion
    extra = 0
    fields = ("order", "text", "weight", "is_active")


@admin.register(Quiz)
class QuizAdmin(admin.ModelAdmin):
    """Admin configuration for course quizzes."""

    list_display = (
        "title",
        "course",
        "status",
        "passing_score",
        "max_attempts",
        "time_limit_minutes",
    )
    list_filter = ("status", "course")
    search_fields = ("title", "course__title")
    readonly_fields = ("published_at", "created_at", "updated_at")
    inlines = [QuizQuestionInline]


@admin.register(QuizQuestion)
class QuizQuestionAdmin(admin.ModelAdmin):
    """Admin configuration for quiz questions."""

    list_display = ("quiz", "order", "weight", "is_active")
    list_filter = ("quiz", "is_active")
    search_fields = ("text", "quiz__title", "quiz__course__title")


@admin.register(QuizOption)
class QuizOptionAdmin(admin.ModelAdmin):
    """Admin configuration for quiz options."""

    list_display = ("question", "order", "text", "is_correct", "is_active")
    list_filter = ("is_correct", "question__quiz")
    search_fields = ("text", "question__text")


@admin.register(QuizAttempt)
class QuizAttemptAdmin(admin.ModelAdmin):
    """Read-only quiz attempt report."""

    list_display = (
        "id",
        "quiz",
        "user",
        "attempt_number",
        "status",
        "score_out_of_20",
        "is_passed",
    )
    list_filter = ("status", "is_passed", "quiz")
    search_fields = ("user__email", "quiz__title", "course__title")
    readonly_fields = [field.name for field in QuizAttempt._meta.fields]

    def has_add_permission(self, request) -> bool:
        """Attempts start through service/API only."""
        return False

    def has_change_permission(self, request, obj=None) -> bool:
        """Attempt scoring is immutable after submission."""
        return False

    def has_delete_permission(self, request, obj=None) -> bool:
        """Attempt history must be preserved."""
        return False


@admin.register(QuizAnswer)
class QuizAnswerAdmin(admin.ModelAdmin):
    """Read-only quiz answer report."""

    list_display = ("attempt", "question", "selected_option", "is_correct", "score_awarded")
    list_filter = ("is_correct", "attempt__quiz")
    readonly_fields = [field.name for field in QuizAnswer._meta.fields]

    def has_add_permission(self, request) -> bool:
        """Answers are submitted through service/API only."""
        return False

    def has_change_permission(self, request, obj=None) -> bool:
        """Answers are immutable scoring evidence."""
        return False

    def has_delete_permission(self, request, obj=None) -> bool:
        """Answer history must be preserved."""
        return False


@admin.register(QuizUnlock)
class QuizUnlockAdmin(admin.ModelAdmin):
    """Admin-managed manual quiz unlocks."""

    list_display = ("quiz", "user", "unlocked_by", "extra_attempts", "valid_until", "created_at")
    list_filter = ("quiz", "valid_until")
    search_fields = ("user__email", "quiz__title", "reason")
    readonly_fields = ("created_at", "updated_at")


@admin.register(Certificate)
class CertificateAdmin(admin.ModelAdmin):
    """Read-focused certificate administration and verification support."""

    list_display = ("certificate_code", "user", "course", "status", "score_out_of_20", "issued_at")
    list_filter = ("status", "course")
    search_fields = ("certificate_code", "verification_slug", "user__email", "full_name_snapshot")
    readonly_fields = [field.name for field in Certificate._meta.fields]

    def has_add_permission(self, request) -> bool:
        """Certificates are issued by graduation service only."""
        return False

    def has_change_permission(self, request, obj=None) -> bool:
        """Certificate changes/revocations must go through service logic."""
        return False

    def has_delete_permission(self, request, obj=None) -> bool:
        """Certificates must remain verifiable or explicitly revoked."""
        return False


@admin.register(LMSUserSkill)
class LMSUserSkillAdmin(admin.ModelAdmin):
    """Read-only skill/badge report."""

    list_display = ("user", "course", "title", "badge_level", "issued_at")
    list_filter = ("badge_level", "course")
    search_fields = ("user__email", "title", "course__title")
    readonly_fields = [field.name for field in LMSUserSkill._meta.fields]

    def has_add_permission(self, request) -> bool:
        """Skills are awarded by certificate service only."""
        return False

    def has_change_permission(self, request, obj=None) -> bool:
        """Skill records are derived from certificates."""
        return False

    def has_delete_permission(self, request, obj=None) -> bool:
        """Skill history should be preserved."""
        return False


@admin.register(LessonVideoProcessingJob)
class LessonVideoProcessingJobAdmin(admin.ModelAdmin):
    """Read-oriented admin for LMS video processing jobs."""

    list_display = (
        "id",
        "lesson",
        "status",
        "provider",
        "requested_by",
        "created_at",
        "completed_at",
    )
    list_filter = ("status", "provider")
    search_fields = ("lesson__title", "lesson__course__title", "source_file_name")
    readonly_fields = [field.name for field in LessonVideoProcessingJob._meta.fields]
    raw_id_fields = ("lesson", "requested_by")
    ordering = ("-created_at",)

    def has_add_permission(self, request) -> bool:
        """Video processing jobs are created by audited API/service workflows."""
        return False

    def has_change_permission(self, request, obj=None) -> bool:
        """Video processing job state is service/task controlled."""
        return False

    def has_delete_permission(self, request, obj=None) -> bool:
        """Video processing evidence must remain available for audit."""
        return False


@admin.register(LearningActivityStatement)
class LearningActivityStatementAdmin(admin.ModelAdmin):
    """Read-only admin for xAPI-like learning activity statements."""

    list_display = ("statement_id", "actor", "course", "verb", "object_type", "occurred_at")
    list_filter = ("verb", "object_type", "course")
    search_fields = ("statement_id", "actor__email", "course__title", "object_id")
    readonly_fields = [field.name for field in LearningActivityStatement._meta.fields]
    raw_id_fields = ("actor", "course", "lesson", "enrollment", "quiz_attempt", "certificate")
    ordering = ("-occurred_at",)

    def has_add_permission(self, request) -> bool:
        """Statements are generated by LMS services only."""
        return False

    def has_change_permission(self, request, obj=None) -> bool:
        """Learning statements are immutable."""
        return False

    def has_delete_permission(self, request, obj=None) -> bool:
        """Learning statements must remain available for analytics."""
        return False

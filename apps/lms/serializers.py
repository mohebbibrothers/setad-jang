"""DRF serializers for LMS catalog, admin management, enrollments, and reports."""

from rest_framework import serializers

from apps.lms.choices import DiscussionReportStatus, DiscussionStatus
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
    QuizAttempt,
    QuizOption,
    QuizQuestion,
    QuizUnlock,
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


class LessonMediaAccessSerializer(serializers.Serializer):
    """Signed/CDN-ready lesson media access payload."""

    media_kind = serializers.CharField()
    provider = serializers.CharField()
    url = serializers.CharField()
    expires_in_seconds = serializers.IntegerField(allow_null=True, required=False)
    lesson_id = serializers.IntegerField()
    course_id = serializers.IntegerField()
    title = serializers.CharField(required=False, allow_blank=True)


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
    certificate_code = serializers.CharField(
        source="certificate.certificate_code", read_only=True, allow_null=True
    )

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
        fields = (
            "id",
            "title",
            "slug",
            "badge_level",
            "course_title",
            "certificate_code",
            "issued_at",
        )
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


class QuizOptionAdminSerializer(serializers.ModelSerializer):
    """Admin serializer exposing correct option flags."""

    class Meta:
        model = QuizOption
        fields = ("id", "text", "is_correct", "order", "is_active")
        read_only_fields = ("id",)


class QuizQuestionAdminSerializer(serializers.ModelSerializer):
    """Admin serializer for quiz questions and options."""

    options = QuizOptionAdminSerializer(many=True, read_only=True)

    class Meta:
        model = QuizQuestion
        fields = ("id", "text", "explanation", "order", "weight", "is_active", "options")
        read_only_fields = ("id",)


class QuizAdminSerializer(serializers.ModelSerializer):
    """Admin serializer for full quiz configuration."""

    questions = QuizQuestionAdminSerializer(many=True, read_only=True)

    class Meta:
        model = Quiz
        fields = (
            "id",
            "course_id",
            "title",
            "description",
            "status",
            "time_limit_minutes",
            "passing_score",
            "max_attempts",
            "retake_delay_days",
            "shuffle_questions",
            "shuffle_options",
            "show_result_immediately",
            "show_correct_answers_after_pass",
            "is_required_for_certificate",
            "published_at",
            "questions",
        )
        read_only_fields = ("id", "course_id", "published_at")


class QuizCreateUpdateSerializer(serializers.Serializer):
    """Input serializer for admin quiz create/update."""

    title = serializers.CharField(max_length=255, required=False)
    description = serializers.CharField(required=False, allow_blank=True)
    time_limit_minutes = serializers.IntegerField(required=False, min_value=1)
    passing_score = serializers.DecimalField(
        required=False, max_digits=4, decimal_places=2, min_value=0, max_value=20
    )
    max_attempts = serializers.IntegerField(required=False, min_value=1, max_value=10)
    retake_delay_days = serializers.IntegerField(required=False, min_value=0, max_value=365)
    shuffle_questions = serializers.BooleanField(required=False)
    shuffle_options = serializers.BooleanField(required=False)
    show_result_immediately = serializers.BooleanField(required=False)
    show_correct_answers_after_pass = serializers.BooleanField(required=False)
    is_required_for_certificate = serializers.BooleanField(required=False)


class QuizQuestionCreateSerializer(serializers.Serializer):
    """Input serializer for admin quiz question creation."""

    text = serializers.CharField()
    explanation = serializers.CharField(required=False, allow_blank=True, default="")
    order = serializers.IntegerField(required=False, min_value=1, default=1)
    weight = serializers.DecimalField(
        required=False, max_digits=6, decimal_places=2, min_value=0, default="1.00"
    )


class QuizOptionCreateSerializer(serializers.Serializer):
    """Input serializer for admin quiz option creation."""

    text = serializers.CharField(max_length=500)
    is_correct = serializers.BooleanField(required=False, default=False)
    order = serializers.IntegerField(required=False, min_value=1, default=1)


class QuizPublicSerializer(serializers.ModelSerializer):
    """User-visible quiz metadata without answers."""

    questions_count = serializers.IntegerField(source="questions.count", read_only=True)

    class Meta:
        model = Quiz
        fields = (
            "id",
            "course_id",
            "title",
            "description",
            "time_limit_minutes",
            "passing_score",
            "max_attempts",
            "retake_delay_days",
            "questions_count",
        )
        read_only_fields = fields


class QuizAttemptQuestionOptionSerializer(serializers.ModelSerializer):
    """User-visible option in an active attempt; never exposes correctness."""

    class Meta:
        model = QuizOption
        fields = ("id", "text", "order")
        read_only_fields = fields


class QuizAttemptQuestionSerializer(serializers.ModelSerializer):
    """User-visible question in an active attempt."""

    options = serializers.SerializerMethodField()

    class Meta:
        model = QuizQuestion
        fields = ("id", "text", "weight", "options")
        read_only_fields = fields

    def get_options(self, obj: QuizQuestion) -> list[dict]:
        """Return options in attempt snapshot order without correct flags."""
        option_order = self.context.get("option_order", {})
        ordered_ids = option_order.get(str(obj.pk), [])
        options_by_id = {option.pk: option for option in obj.options.all()}
        ordered_options = [
            options_by_id[option_id] for option_id in ordered_ids if option_id in options_by_id
        ]
        return QuizAttemptQuestionOptionSerializer(ordered_options, many=True).data


class QuizAttemptDetailSerializer(serializers.ModelSerializer):
    """Attempt detail serializer hiding correct answers unless attempt is passed."""

    questions = serializers.SerializerMethodField()
    answers = serializers.SerializerMethodField()

    class Meta:
        model = QuizAttempt
        fields = (
            "id",
            "quiz_id",
            "course_id",
            "attempt_number",
            "status",
            "started_at",
            "submitted_at",
            "expires_at",
            "score_percent",
            "score_out_of_20",
            "is_passed",
            "questions",
            "answers",
        )
        read_only_fields = fields

    def get_questions(self, obj: QuizAttempt) -> list[dict]:
        """Return questions in snapshot order."""
        questions = list(
            QuizQuestion.objects.filter(pk__in=obj.question_snapshot).prefetch_related("options")
        )
        by_id = {question.pk: question for question in questions}
        ordered = [by_id[qid] for qid in obj.question_snapshot if qid in by_id]
        return QuizAttemptQuestionSerializer(
            ordered,
            many=True,
            context={"option_order": obj.option_order_snapshot},
        ).data

    def get_answers(self, obj: QuizAttempt) -> list[dict]:
        """Return submitted answers; correct answers only after passing."""
        reveal_correct = bool(obj.is_passed and obj.quiz.show_correct_answers_after_pass)
        payload = []
        for answer in obj.answers.select_related("question", "selected_option").all():
            item = {
                "question_id": answer.question_id,
                "selected_option_id": answer.selected_option_id,
                "is_correct": answer.is_correct if obj.submitted_at else None,
                "score_awarded": str(answer.score_awarded),
            }
            if reveal_correct:
                correct = answer.question.options.filter(is_correct=True).first()
                item["correct_option_id"] = correct.pk if correct else None
                item["explanation"] = answer.question.explanation
            payload.append(item)
        return payload


class QuizAttemptSubmitSerializer(serializers.Serializer):
    """Input serializer for submitting a quiz attempt."""

    answers = serializers.ListField(
        child=serializers.DictField(child=serializers.IntegerField(min_value=1)),
        allow_empty=False,
    )

    def validate_answers(self, value: list[dict]) -> list[dict]:
        """Validate each answer object has required keys."""
        for item in value:
            if "question_id" not in item or "selected_option_id" not in item:
                raise serializers.ValidationError(
                    "هر پاسخ باید question_id و selected_option_id داشته باشد."
                )
        return value


class QuizUnlockCreateSerializer(serializers.Serializer):
    """Input serializer for admin manual quiz unlock."""

    user_id = serializers.IntegerField(min_value=1)
    reason = serializers.CharField()
    extra_attempts = serializers.IntegerField(required=False, min_value=1, max_value=10, default=1)
    valid_until = serializers.DateTimeField(required=False, allow_null=True)


class QuizUnlockSerializer(serializers.ModelSerializer):
    """Output serializer for quiz unlock records."""

    class Meta:
        model = QuizUnlock
        fields = (
            "id",
            "quiz_id",
            "course_id",
            "user_id",
            "unlocked_by_id",
            "reason",
            "extra_attempts",
            "valid_until",
            "created_at",
        )
        read_only_fields = fields


class CertificateSerializer(serializers.ModelSerializer):
    """User/admin certificate representation."""

    course_title = serializers.CharField(source="course.title", read_only=True)
    statement = serializers.SerializerMethodField()
    verification_url = serializers.SerializerMethodField()

    class Meta:
        model = Certificate
        fields = (
            "id",
            "certificate_code",
            "verification_slug",
            "status",
            "course_id",
            "course_title",
            "full_name_snapshot",
            "gender_snapshot",
            "national_code_snapshot",
            "course_title_snapshot",
            "instructor_name_snapshot",
            "score_out_of_20",
            "issued_at",
            "revoked_at",
            "revocation_reason",
            "pdf_file",
            "statement",
            "verification_url",
        )
        read_only_fields = fields

    def get_statement(self, obj: Certificate) -> str:
        """Return official certificate statement."""
        from apps.lms.certificate import build_certificate_text

        return build_certificate_text(obj)

    def get_verification_url(self, obj: Certificate) -> str:
        """Return absolute verification URL when request is available."""
        request = self.context.get("request")
        path = f"/api/v1/lms/certificates/verify/{obj.verification_slug}/"
        return request.build_absolute_uri(path) if request else path


class CertificateVerifySerializer(CertificateSerializer):
    """Public certificate verification serializer."""

    class Meta(CertificateSerializer.Meta):
        fields = (
            "certificate_code",
            "status",
            "full_name_snapshot",
            "gender_snapshot",
            "national_code_snapshot",
            "course_title_snapshot",
            "instructor_name_snapshot",
            "score_out_of_20",
            "issued_at",
            "statement",
        )


class CertificateRevokeSerializer(serializers.Serializer):
    """Input serializer for admin certificate revocation."""

    reason = serializers.CharField()


class CourseAnalyticsSerializer(serializers.Serializer):
    """Admin analytics summary for a course."""

    participants_count = serializers.IntegerField()
    active_count = serializers.IntegerField()
    completed_count = serializers.IntegerField()
    graduates_count = serializers.IntegerField()
    average_progress_percent = serializers.FloatField()
    quiz_attempts_count = serializers.IntegerField()
    quiz_passed_count = serializers.IntegerField()
    quiz_failed_count = serializers.IntegerField()
    average_score_out_of_20 = serializers.FloatField(allow_null=True)


class CourseLeaderboardItemSerializer(serializers.Serializer):
    """Leaderboard row for top LMS learners in a course."""

    user_id = serializers.IntegerField()
    full_name = serializers.CharField()
    email = serializers.EmailField(allow_blank=True)
    progress_percent = serializers.FloatField()
    best_score_out_of_20 = serializers.FloatField(allow_null=True)
    badge_level = serializers.CharField(allow_blank=True)
    certificate_code = serializers.CharField(allow_blank=True)


class LessonVideoProcessingJobSerializer(serializers.ModelSerializer):
    """Read serializer for lesson video processing jobs."""

    lesson_title = serializers.CharField(source="lesson.title", read_only=True)
    status_display = serializers.CharField(source="get_status_display", read_only=True)

    class Meta:
        model = LessonVideoProcessingJob
        fields = (
            "id",
            "lesson",
            "lesson_title",
            "requested_by",
            "status",
            "status_display",
            "provider",
            "source_file_name",
            "output_video_url",
            "thumbnail_url",
            "duration_seconds",
            "metadata",
            "error_message",
            "started_at",
            "completed_at",
            "created_at",
            "updated_at",
        )
        read_only_fields = fields


class LearningRecommendationItemSerializer(serializers.Serializer):
    """One learner course recommendation with explanation."""

    course = CourseSummarySerializer(read_only=True)
    score = serializers.IntegerField(read_only=True)
    reason_codes = serializers.ListField(child=serializers.CharField(), read_only=True)


class LearningRecommendationOverviewSerializer(serializers.Serializer):
    """Admin overview of recommendation readiness."""

    published_courses = serializers.IntegerField(read_only=True)
    featured_courses = serializers.IntegerField(read_only=True)
    cold_start_courses = serializers.IntegerField(read_only=True)
    top_recommendable_courses = serializers.ListField(child=serializers.DictField(), read_only=True)


class LearningActivityStatementSerializer(serializers.ModelSerializer):
    """Read serializer for xAPI-like learning activity statements."""

    actor_email = serializers.EmailField(source="actor.email", read_only=True, allow_null=True)
    course_title = serializers.CharField(source="course.title", read_only=True)
    lesson_title = serializers.CharField(
        source="lesson.title", read_only=True, allow_blank=True, allow_null=True
    )
    verb_display = serializers.CharField(source="get_verb_display", read_only=True)

    class Meta:
        model = LearningActivityStatement
        fields = (
            "id",
            "statement_id",
            "idempotency_key",
            "actor",
            "actor_email",
            "course",
            "course_title",
            "lesson",
            "lesson_title",
            "enrollment",
            "quiz_attempt",
            "certificate",
            "verb",
            "verb_display",
            "object_type",
            "object_id",
            "actor_snapshot",
            "object_snapshot",
            "result",
            "context",
            "occurred_at",
            "created_at",
        )
        read_only_fields = fields

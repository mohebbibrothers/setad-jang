"""
Database models for the LMS application.

The LMS domain is designed as a complete education platform: dynamic categories,
courses, lessons, enrollments, progress tracking, Q&A, professional quiz attempts,
certificates, and skill badges.

Design principles:
- dynamic admin-managed categories, not hard-coded choices
- soft-delete where business records may be hidden
- immutable snapshots for quiz attempts/certificates
- denormalized counters for fast public/admin dashboards
- service layer owns all state transitions and mutations
"""

from __future__ import annotations

import uuid
from typing import Any

from django.conf import settings
from django.db import models
from django.utils import timezone
from django.utils.text import slugify

from apps.core.models import BaseModel
from apps.lms.choices import (
    BadgeLevel,
    CertificateStatus,
    CourseLevel,
    CourseStatus,
    DiscussionReportStatus,
    DiscussionStatus,
    EnrollmentStatus,
    QuizAttemptStatus,
    QuizStatus,
    VideoProvider,
)
from apps.lms.managers import CourseManager, LessonManager, LMSCategoryManager
from apps.lms.validators import (
    validate_duration_seconds,
    validate_lesson_file_size,
    validate_lesson_video_file_size,
    validate_positive_weight,
    validate_quiz_passing_score,
)

# ---------------------------------------------------------------------------
# Upload path helpers
# ---------------------------------------------------------------------------


def category_cover_upload_path(instance: LMSCategory, filename: str) -> str:
    """Return upload path for category cover images."""
    return f"lms/categories/{instance.pk or 'new'}/cover/{filename}"


def course_cover_upload_path(instance: Course, filename: str) -> str:
    """Return upload path for course cover images."""
    return f"lms/courses/{instance.pk or 'new'}/cover/{filename}"


def instructor_avatar_upload_path(instance: Course, filename: str) -> str:
    """Return upload path for instructor avatar images."""
    return f"lms/courses/{instance.pk or 'new'}/instructor/{filename}"


def lesson_video_upload_path(instance: Lesson, filename: str) -> str:
    """Return upload path for uploaded lesson videos."""
    return f"lms/courses/{instance.course_id}/lessons/{instance.pk or 'new'}/video/{filename}"


def lesson_attachment_upload_path(instance: Lesson, filename: str) -> str:
    """Return upload path for lesson handout files."""
    return f"lms/courses/{instance.course_id}/lessons/{instance.pk or 'new'}/attachments/{filename}"


def certificate_pdf_upload_path(instance: Certificate, filename: str) -> str:
    """Return upload path for generated certificate PDFs."""
    return f"lms/certificates/{instance.certificate_code}/{filename}"


# ---------------------------------------------------------------------------
# Category / Course / Lesson
# ---------------------------------------------------------------------------


class LMSCategory(BaseModel):
    """Admin-managed dynamic category for LMS courses."""

    title = models.CharField(max_length=150, unique=True, verbose_name="عنوان دسته‌بندی")
    slug = models.SlugField(max_length=180, unique=True, allow_unicode=True, blank=True)
    description = models.TextField(blank=True, verbose_name="توضیحات")
    icon = models.CharField(max_length=80, blank=True, verbose_name="آیکن")
    cover_image = models.ImageField(
        upload_to=category_cover_upload_path,
        blank=True,
        null=True,
        verbose_name="تصویر کاور",
    )
    order = models.PositiveIntegerField(default=0, verbose_name="ترتیب نمایش")

    objects = LMSCategoryManager()
    all_objects = LMSCategoryManager()

    class Meta:
        verbose_name = "دسته‌بندی آموزش"
        verbose_name_plural = "دسته‌بندی‌های آموزش"
        ordering = ["order", "title"]
        indexes = [models.Index(fields=["is_active", "order", "title"])]

    def __str__(self) -> str:
        return self.title

    def save(self, *args: Any, **kwargs: Any) -> None:
        """Generate a collision-safe slug if needed."""
        if not self.slug:
            self.slug = _generate_unique_slug(
                model=LMSCategory,
                base_value=self.title,
                max_length=180,
            )
        super().save(*args, **kwargs)


class Course(BaseModel):
    """A free LMS class/course published by admins."""

    category = models.ForeignKey(
        LMSCategory,
        on_delete=models.PROTECT,
        related_name="courses",
        verbose_name="دسته‌بندی",
    )
    title = models.CharField(max_length=255, verbose_name="عنوان کلاس")
    slug = models.SlugField(max_length=300, unique=True, allow_unicode=True, blank=True)
    subtitle = models.CharField(max_length=300, blank=True, verbose_name="زیرعنوان")
    short_description = models.CharField(max_length=500, blank=True, verbose_name="توضیح کوتاه")
    description = models.TextField(verbose_name="توضیحات کامل")
    cover_image = models.ImageField(
        upload_to=course_cover_upload_path,
        blank=True,
        null=True,
        verbose_name="تصویر کاور",
    )

    instructor_name = models.CharField(max_length=180, verbose_name="نام استاد")
    instructor_bio = models.TextField(blank=True, verbose_name="معرفی استاد")
    instructor_avatar = models.ImageField(
        upload_to=instructor_avatar_upload_path,
        blank=True,
        null=True,
        verbose_name="تصویر استاد",
    )

    level = models.CharField(max_length=20, choices=CourseLevel.choices, default=CourseLevel.BEGINNER)
    status = models.CharField(max_length=20, choices=CourseStatus.choices, default=CourseStatus.DRAFT)
    language = models.CharField(max_length=30, default="fa", verbose_name="زبان")
    is_featured = models.BooleanField(default=False, verbose_name="ویژه")

    intro_video_url = models.URLField(max_length=1024, blank=True, verbose_name="ویدئوی معرفی")
    estimated_duration_seconds = models.PositiveIntegerField(default=0)
    lessons_count = models.PositiveIntegerField(default=0)
    enrollments_count = models.PositiveIntegerField(default=0)
    graduates_count = models.PositiveIntegerField(default=0)
    average_rating = models.DecimalField(max_digits=3, decimal_places=2, default=0)

    published_at = models.DateTimeField(null=True, blank=True)
    archived_at = models.DateTimeField(null=True, blank=True)

    objects = CourseManager()
    all_objects = CourseManager()

    class Meta:
        verbose_name = "کلاس آموزشی"
        verbose_name_plural = "کلاس‌های آموزشی"
        ordering = ["-published_at", "-created_at"]
        indexes = [
            models.Index(fields=["slug"]),
            models.Index(fields=["category", "status", "is_active"]),
            models.Index(fields=["status", "is_featured", "-published_at"]),
            models.Index(fields=["instructor_name"]),
        ]

    def __str__(self) -> str:
        return self.title

    def save(self, *args: Any, **kwargs: Any) -> None:
        """Generate a collision-safe course slug if needed."""
        if not self.slug:
            self.slug = _generate_unique_slug(model=Course, base_value=self.title, max_length=300)
        super().save(*args, **kwargs)

    @property
    def is_published(self) -> bool:
        """Return whether this course is public."""
        return self.is_active and self.status == CourseStatus.PUBLISHED


class Lesson(BaseModel):
    """A single ordered session inside a course."""

    course = models.ForeignKey(Course, on_delete=models.CASCADE, related_name="lessons")
    title = models.CharField(max_length=255)
    slug = models.SlugField(max_length=300, allow_unicode=True, blank=True)
    description = models.TextField(blank=True)
    order = models.PositiveIntegerField(default=1)

    video_provider = models.CharField(
        max_length=20,
        choices=VideoProvider.choices,
        default=VideoProvider.HYBRID,
    )
    video_url = models.URLField(max_length=1024, blank=True)
    embed_url = models.URLField(max_length=1024, blank=True)
    video_file = models.FileField(
        upload_to=lesson_video_upload_path,
        blank=True,
        null=True,
        validators=[validate_lesson_video_file_size],
    )
    duration_seconds = models.PositiveIntegerField(default=0, validators=[validate_duration_seconds])

    transcript = models.TextField(blank=True)
    summary = models.TextField(blank=True)
    homework = models.TextField(blank=True)
    attachment_file = models.FileField(
        upload_to=lesson_attachment_upload_path,
        blank=True,
        null=True,
        validators=[validate_lesson_file_size],
    )
    attachment_title = models.CharField(max_length=255, blank=True)
    is_preview = models.BooleanField(default=False)
    published_at = models.DateTimeField(null=True, blank=True)

    objects = LessonManager()
    all_objects = LessonManager()

    class Meta:
        verbose_name = "جلسه آموزشی"
        verbose_name_plural = "جلسات آموزشی"
        ordering = ["course_id", "order", "id"]
        indexes = [
            models.Index(fields=["course", "order"]),
            models.Index(fields=["course", "is_active", "order"]),
        ]
        constraints = [
            models.UniqueConstraint(fields=["course", "order"], name="uniq_lms_lesson_order_per_course"),
            models.UniqueConstraint(fields=["course", "slug"], name="uniq_lms_lesson_slug_per_course"),
        ]

    def __str__(self) -> str:
        return f"{self.course.title} — {self.title}"

    def save(self, *args: Any, **kwargs: Any) -> None:
        """Generate a lesson slug scoped to course."""
        if not self.slug:
            self.slug = slugify(self.title, allow_unicode=True)[:300] or f"lesson-{self.order}"
        super().save(*args, **kwargs)


# ---------------------------------------------------------------------------
# Enrollment / Progress
# ---------------------------------------------------------------------------


class Enrollment(BaseModel):
    """A user's free registration in a course."""

    course = models.ForeignKey(Course, on_delete=models.PROTECT, related_name="enrollments")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="lms_enrollments")
    status = models.CharField(max_length=20, choices=EnrollmentStatus.choices, default=EnrollmentStatus.ACTIVE)
    enrolled_at = models.DateTimeField(default=timezone.now)
    completed_at = models.DateTimeField(null=True, blank=True)
    last_accessed_lesson = models.ForeignKey(
        Lesson,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="last_access_enrollments",
    )
    progress_percent = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    watched_seconds = models.PositiveIntegerField(default=0)
    total_seconds_snapshot = models.PositiveIntegerField(default=0)

    class Meta:
        verbose_name = "ثبت‌نام LMS"
        verbose_name_plural = "ثبت‌نام‌های LMS"
        ordering = ["-enrolled_at"]
        indexes = [
            models.Index(fields=["user", "status", "-enrolled_at"]),
            models.Index(fields=["course", "status", "-enrolled_at"]),
        ]
        constraints = [
            models.UniqueConstraint(fields=["course", "user"], name="uniq_lms_enrollment_user_course"),
        ]

    def __str__(self) -> str:
        return f"Enrollment user={self.user_id} course={self.course_id}"


class LessonProgress(BaseModel):
    """Per-lesson progress for an enrollment."""

    enrollment = models.ForeignKey(Enrollment, on_delete=models.CASCADE, related_name="lesson_progress")
    lesson = models.ForeignKey(Lesson, on_delete=models.PROTECT, related_name="progress_records")
    watched_seconds = models.PositiveIntegerField(default=0)
    duration_seconds_snapshot = models.PositiveIntegerField(default=0)
    progress_percent = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    is_completed = models.BooleanField(default=False)
    last_position_seconds = models.PositiveIntegerField(default=0)
    first_watched_at = models.DateTimeField(null=True, blank=True)
    last_watched_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = "پیشرفت جلسه"
        verbose_name_plural = "پیشرفت جلسات"
        indexes = [models.Index(fields=["enrollment", "lesson"])]
        constraints = [
            models.UniqueConstraint(fields=["enrollment", "lesson"], name="uniq_lms_progress_enrollment_lesson"),
        ]


# ---------------------------------------------------------------------------
# Q&A / Discussion
# ---------------------------------------------------------------------------


class LessonQuestion(BaseModel):
    """A user question under a lesson."""

    lesson = models.ForeignKey(Lesson, on_delete=models.CASCADE, related_name="questions")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="lms_questions")
    title = models.CharField(max_length=255)
    body = models.TextField()
    status = models.CharField(max_length=20, choices=DiscussionStatus.choices, default=DiscussionStatus.VISIBLE)
    is_pinned = models.BooleanField(default=False)
    is_answered = models.BooleanField(default=False)
    answer_count = models.PositiveIntegerField(default=0)
    last_activity_at = models.DateTimeField(default=timezone.now)

    class Meta:
        verbose_name = "سؤال جلسه"
        verbose_name_plural = "سؤالات جلسات"
        ordering = ["-is_pinned", "-last_activity_at"]
        indexes = [
            models.Index(fields=["lesson", "status", "-last_activity_at"]),
            models.Index(fields=["user", "status", "-created_at"]),
        ]


class LessonAnswer(BaseModel):
    """A threaded answer for a lesson question."""

    question = models.ForeignKey(LessonQuestion, on_delete=models.CASCADE, related_name="answers")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="lms_answers")
    body = models.TextField()
    status = models.CharField(max_length=20, choices=DiscussionStatus.choices, default=DiscussionStatus.VISIBLE)
    is_instructor_answer = models.BooleanField(default=False)
    is_accepted = models.BooleanField(default=False)

    class Meta:
        verbose_name = "پاسخ سؤال"
        verbose_name_plural = "پاسخ‌های سؤالات"
        ordering = ["created_at"]
        indexes = [models.Index(fields=["question", "status", "created_at"])]


class LessonDiscussionReport(BaseModel):
    """A moderation report against a lesson question or answer."""

    question = models.ForeignKey(
        LessonQuestion,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="reports",
    )
    answer = models.ForeignKey(
        LessonAnswer,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="reports",
    )
    reported_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    reason = models.CharField(max_length=150)
    description = models.TextField(blank=True)
    status = models.CharField(
        max_length=20,
        choices=DiscussionReportStatus.choices,
        default=DiscussionReportStatus.PENDING,
    )
    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="lms_reviewed_discussion_reports",
    )
    reviewed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = "گزارش تخلف گفتگو"
        verbose_name_plural = "گزارش‌های تخلف گفتگو"
        indexes = [models.Index(fields=["status", "-created_at"])]
        constraints = [
            models.CheckConstraint(
                condition=(
                    models.Q(question__isnull=False, answer__isnull=True)
                    | models.Q(question__isnull=True, answer__isnull=False)
                ),
                name="lms_discussion_report_one_target",
            )
        ]


# ---------------------------------------------------------------------------
# Quiz
# ---------------------------------------------------------------------------


class Quiz(BaseModel):
    """Professional weighted quiz attached to a course."""

    course = models.OneToOneField(Course, on_delete=models.CASCADE, related_name="quiz")
    title = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    status = models.CharField(max_length=20, choices=QuizStatus.choices, default=QuizStatus.DRAFT)
    time_limit_minutes = models.PositiveIntegerField(default=30)
    passing_score = models.DecimalField(
        max_digits=4,
        decimal_places=2,
        default=12,
        validators=[validate_quiz_passing_score],
    )
    max_attempts = models.PositiveSmallIntegerField(default=2)
    retake_delay_days = models.PositiveSmallIntegerField(default=14)
    shuffle_questions = models.BooleanField(default=True)
    shuffle_options = models.BooleanField(default=True)
    show_result_immediately = models.BooleanField(default=True)
    show_correct_answers_after_pass = models.BooleanField(default=True)
    is_required_for_certificate = models.BooleanField(default=True)
    published_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = "آزمون دوره"
        verbose_name_plural = "آزمون‌های دوره"
        indexes = [models.Index(fields=["status", "published_at"])]


class QuizQuestion(BaseModel):
    """A weighted single-choice question in a quiz."""

    quiz = models.ForeignKey(Quiz, on_delete=models.CASCADE, related_name="questions")
    text = models.TextField()
    explanation = models.TextField(blank=True)
    order = models.PositiveIntegerField(default=1)
    weight = models.DecimalField(
        max_digits=6,
        decimal_places=2,
        default=1,
        validators=[validate_positive_weight],
    )

    class Meta:
        verbose_name = "سؤال آزمون"
        verbose_name_plural = "سؤالات آزمون"
        ordering = ["order", "id"]
        constraints = [models.UniqueConstraint(fields=["quiz", "order"], name="uniq_lms_quiz_question_order")]


class QuizOption(BaseModel):
    """One option for a quiz question."""

    question = models.ForeignKey(QuizQuestion, on_delete=models.CASCADE, related_name="options")
    text = models.CharField(max_length=500)
    is_correct = models.BooleanField(default=False)
    order = models.PositiveIntegerField(default=1)

    class Meta:
        verbose_name = "گزینه آزمون"
        verbose_name_plural = "گزینه‌های آزمون"
        ordering = ["order", "id"]
        constraints = [models.UniqueConstraint(fields=["question", "order"], name="uniq_lms_quiz_option_order")]


class QuizAttempt(BaseModel):
    """A user's quiz attempt with immutable question/option snapshots."""

    quiz = models.ForeignKey(Quiz, on_delete=models.PROTECT, related_name="attempts")
    course = models.ForeignKey(Course, on_delete=models.PROTECT, related_name="quiz_attempts")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="lms_quiz_attempts")
    enrollment = models.ForeignKey(Enrollment, on_delete=models.PROTECT, related_name="quiz_attempts")
    attempt_number = models.PositiveSmallIntegerField(default=1)
    status = models.CharField(max_length=20, choices=QuizAttemptStatus.choices, default=QuizAttemptStatus.IN_PROGRESS)
    started_at = models.DateTimeField(default=timezone.now)
    submitted_at = models.DateTimeField(null=True, blank=True)
    expires_at = models.DateTimeField(null=True, blank=True)
    score_raw = models.DecimalField(max_digits=8, decimal_places=2, default=0)
    score_percent = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    score_out_of_20 = models.DecimalField(max_digits=4, decimal_places=2, default=0)
    is_passed = models.BooleanField(default=False)
    locked_reason = models.CharField(max_length=255, blank=True)
    question_snapshot = models.JSONField(default=list, blank=True)
    option_order_snapshot = models.JSONField(default=dict, blank=True)

    class Meta:
        verbose_name = "تلاش آزمون"
        verbose_name_plural = "تلاش‌های آزمون"
        ordering = ["-started_at"]
        indexes = [
            models.Index(fields=["user", "quiz", "-started_at"]),
            models.Index(fields=["enrollment", "status"]),
        ]
        constraints = [
            models.UniqueConstraint(fields=["quiz", "user", "attempt_number"], name="uniq_lms_quiz_user_attempt_number"),
        ]


class QuizAnswer(BaseModel):
    """Answer selected by a user during a quiz attempt."""

    attempt = models.ForeignKey(QuizAttempt, on_delete=models.CASCADE, related_name="answers")
    question = models.ForeignKey(QuizQuestion, on_delete=models.PROTECT)
    selected_option = models.ForeignKey(QuizOption, on_delete=models.PROTECT)
    is_correct = models.BooleanField(default=False)
    weight = models.DecimalField(max_digits=6, decimal_places=2, default=1)
    score_awarded = models.DecimalField(max_digits=6, decimal_places=2, default=0)
    answered_at = models.DateTimeField(default=timezone.now)

    class Meta:
        verbose_name = "پاسخ آزمون"
        verbose_name_plural = "پاسخ‌های آزمون"
        constraints = [models.UniqueConstraint(fields=["attempt", "question"], name="uniq_lms_attempt_question_answer")]


class QuizUnlock(BaseModel):
    """Manual admin unlock for quiz retakes."""

    quiz = models.ForeignKey(Quiz, on_delete=models.PROTECT, related_name="unlocks")
    course = models.ForeignKey(Course, on_delete=models.PROTECT, related_name="quiz_unlocks")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="lms_quiz_unlocks")
    unlocked_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="lms_quiz_unlocks_granted",
    )
    reason = models.TextField()
    extra_attempts = models.PositiveSmallIntegerField(default=1)
    valid_until = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = "بازگشایی آزمون"
        verbose_name_plural = "بازگشایی‌های آزمون"
        indexes = [models.Index(fields=["quiz", "user", "valid_until"])]


# ---------------------------------------------------------------------------
# Certificates / Skills
# ---------------------------------------------------------------------------


class Certificate(BaseModel):
    """Verifiable certificate issued after passing a course quiz."""

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="lms_certificates")
    course = models.ForeignKey(Course, on_delete=models.PROTECT, related_name="certificates")
    enrollment = models.OneToOneField(Enrollment, on_delete=models.PROTECT, related_name="certificate")
    quiz_attempt = models.OneToOneField(QuizAttempt, on_delete=models.PROTECT, related_name="certificate")
    certificate_code = models.CharField(max_length=40, unique=True, blank=True)
    verification_slug = models.SlugField(max_length=80, unique=True, blank=True)
    status = models.CharField(max_length=20, choices=CertificateStatus.choices, default=CertificateStatus.ISSUED)
    full_name_snapshot = models.CharField(max_length=255)
    gender_snapshot = models.CharField(max_length=20, blank=True)
    national_code_snapshot = models.CharField(max_length=20)
    course_title_snapshot = models.CharField(max_length=255)
    instructor_name_snapshot = models.CharField(max_length=180)
    score_out_of_20 = models.DecimalField(max_digits=4, decimal_places=2)
    issued_at = models.DateTimeField(default=timezone.now)
    revoked_at = models.DateTimeField(null=True, blank=True)
    revoked_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="lms_revoked_certificates",
    )
    revocation_reason = models.TextField(blank=True)
    pdf_file = models.FileField(upload_to=certificate_pdf_upload_path, blank=True, null=True)

    class Meta:
        verbose_name = "گواهی LMS"
        verbose_name_plural = "گواهی‌های LMS"
        indexes = [
            models.Index(fields=["certificate_code"]),
            models.Index(fields=["verification_slug"]),
            models.Index(fields=["user", "status", "-issued_at"]),
        ]
        constraints = [
            models.UniqueConstraint(fields=["user", "course"], name="uniq_lms_certificate_user_course"),
        ]

    def save(self, *args: Any, **kwargs: Any) -> None:
        """Generate verification code/slug on first save."""
        if not self.certificate_code:
            self.certificate_code = uuid.uuid4().hex[:24].upper()
        if not self.verification_slug:
            self.verification_slug = self.certificate_code.lower()
        super().save(*args, **kwargs)


class LMSUserSkill(BaseModel):
    """Skill/badge added to user profile after graduation."""

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="lms_skills")
    course = models.ForeignKey(Course, on_delete=models.PROTECT, related_name="awarded_skills")
    certificate = models.OneToOneField(Certificate, on_delete=models.PROTECT, related_name="skill")
    title = models.CharField(max_length=255)
    slug = models.SlugField(max_length=300, allow_unicode=True, blank=True)
    badge_level = models.CharField(max_length=20, choices=BadgeLevel.choices)
    issued_at = models.DateTimeField(default=timezone.now)

    class Meta:
        verbose_name = "مهارت کاربر"
        verbose_name_plural = "مهارت‌های کاربران"
        indexes = [
            models.Index(fields=["user", "badge_level", "-issued_at"]),
            models.Index(fields=["course", "badge_level"]),
        ]
        constraints = [models.UniqueConstraint(fields=["user", "course"], name="uniq_lms_user_skill_course")]

    def save(self, *args: Any, **kwargs: Any) -> None:
        """Generate skill slug if needed."""
        if not self.slug:
            self.slug = slugify(self.title, allow_unicode=True)[:300] or f"skill-{self.course_id}"
        super().save(*args, **kwargs)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _generate_unique_slug(*, model: type[models.Model], base_value: str, max_length: int) -> str:
    """Generate a unique unicode slug for a model with a slug field."""
    base = slugify(base_value, allow_unicode=True)[:max_length] or "item"
    candidate = base
    suffix = 2
    while model.all_objects.filter(slug=candidate).exists() if hasattr(model, "all_objects") else model.objects.filter(slug=candidate).exists():
        suffix_text = f"-{suffix}"
        candidate = f"{base[: max_length - len(suffix_text)]}{suffix_text}"
        suffix += 1
    return candidate

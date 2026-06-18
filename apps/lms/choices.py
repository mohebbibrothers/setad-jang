"""
Enumeration choices for the LMS domain.

All state-machine statuses and fixed domain values live here to avoid duplicated
string literals across models, services, serializers, and tests.
"""

from django.db import models


class CourseLevel(models.TextChoices):
    """Difficulty level for a course."""

    BEGINNER = "beginner", "مقدماتی"
    INTERMEDIATE = "intermediate", "متوسط"
    ADVANCED = "advanced", "پیشرفته"
    PROFESSIONAL = "professional", "حرفه‌ای"


class CourseStatus(models.TextChoices):
    """Publishing lifecycle for a course."""

    DRAFT = "draft", "پیش‌نویس"
    PUBLISHED = "published", "منتشرشده"
    ARCHIVED = "archived", "آرشیوشده"


class EnrollmentStatus(models.TextChoices):
    """Lifecycle of a user's enrollment in a course."""

    ACTIVE = "active", "فعال"
    COMPLETED = "completed", "تکمیل‌شده"
    CANCELED = "canceled", "لغوشده"
    LOCKED = "locked", "قفل‌شده"


class DiscussionStatus(models.TextChoices):
    """Moderation state for lesson questions and answers."""

    VISIBLE = "visible", "قابل نمایش"
    HIDDEN = "hidden", "مخفی"
    DELETED = "deleted", "حذف‌شده"
    FLAGGED = "flagged", "گزارش‌شده"


class DiscussionReportStatus(models.TextChoices):
    """Moderation status for a report against a question/answer."""

    PENDING = "pending", "در انتظار بررسی"
    REVIEWED = "reviewed", "بررسی‌شده"
    REJECTED = "rejected", "رد گزارش"


class QuizStatus(models.TextChoices):
    """Publishing lifecycle for course quizzes."""

    DRAFT = "draft", "پیش‌نویس"
    PUBLISHED = "published", "منتشرشده"
    ARCHIVED = "archived", "آرشیوشده"


class QuizAttemptStatus(models.TextChoices):
    """State machine for a quiz attempt."""

    IN_PROGRESS = "in_progress", "در حال انجام"
    SUBMITTED = "submitted", "ثبت‌شده"
    PASSED = "passed", "قبول‌شده"
    FAILED = "failed", "مردود"
    EXPIRED = "expired", "منقضی‌شده"
    LOCKED = "locked", "قفل‌شده"


class CertificateStatus(models.TextChoices):
    """Lifecycle for issued certificates."""

    ISSUED = "issued", "صادرشده"
    REVOKED = "revoked", "باطل‌شده"


class BadgeLevel(models.TextChoices):
    """Skill badge level derived from quiz score."""

    BRONZE = "bronze", "برنزی"
    SILVER = "silver", "نقره‌ای"
    GOLD = "gold", "طلایی"
    DISTINCTION = "distinction", "نشان ممتاز"


class VideoProvider(models.TextChoices):
    """Supported lesson video source types."""

    DIRECT_URL = "direct_url", "لینک مستقیم"
    EMBED = "embed", "Embed"
    UPLOADED_FILE = "uploaded_file", "فایل آپلودی"
    HYBRID = "hybrid", "ترکیبی"


class VideoProcessingStatus(models.TextChoices):
    """Lifecycle for lesson video processing jobs."""

    QUEUED = "queued", "در صف"
    PROCESSING = "processing", "در حال پردازش"
    COMPLETED = "completed", "تکمیل‌شده"
    FAILED = "failed", "ناموفق"
    CANCELED = "canceled", "لغوشده"


class LearningStatementVerb(models.TextChoices):
    """xAPI-like learning activity verbs captured by the LMS."""

    INITIALIZED = "initialized", "شروع شد"
    PROGRESSED = "progressed", "پیشرفت کرد"
    COMPLETED = "completed", "تکمیل شد"
    PASSED = "passed", "قبول شد"
    FAILED = "failed", "مردود شد"
    CERTIFICATE_ISSUED = "certificate_issued", "مدرک صادر شد"

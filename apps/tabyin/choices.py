"""
Enumeration choices for Tabyin content metadata and submission workflows.
"""

from django.db import models


class MediaType(models.TextChoices):
    """نوع رسانه پیوست."""

    IMAGE = "image", "تصویر"
    VIDEO = "video", "ویدئو"
    AUDIO = "audio", "صوت"
    OTHER = "other", "سایر"


class SyncMode(models.TextChoices):
    """حالت اجرای همگام‌سازی."""

    FULL = "full", "کامل"
    INCREMENTAL = "incremental", "افزایشی"


class ContentOrigin(models.TextChoices):
    """منشأ محتوای تبیین."""

    EXTERNAL = "external", "همگام‌سازی خارجی"
    USER_SUBMITTED = "user_submitted", "ارسالی کاربر"


class SubmissionStatus(models.TextChoices):
    """وضعیت بررسی محتوای ارسال‌شده توسط کاربر."""

    APPROVED = "approved", "تأیید شده"
    PENDING_REVIEW = "pending_review", "در انتظار بررسی"
    REJECTED = "rejected", "رد شده"


class MirrorStatus(models.TextChoices):
    """وضعیت آینه‌سازی پیوست روی استوریج خودمان."""

    NONE = "none", "بدون نیاز (محتوای منبع خارجی)"
    PENDING = "pending", "در انتظار آینه‌سازی"
    MIRRORED = "mirrored", "روی سرور بعثت"
    FAILED = "failed", "آینه‌سازی ناموفق"


SUBMISSION_REVIEWABLE_STATUSES: frozenset[str] = frozenset([SubmissionStatus.PENDING_REVIEW])

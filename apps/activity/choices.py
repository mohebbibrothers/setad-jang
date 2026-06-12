"""Choices for user activity timeline."""

from django.db import models


class ActivityVerb(models.TextChoices):
    """High-level action verbs for user activity."""

    CREATED = "created", "ایجاد کرد"
    SUBMITTED = "submitted", "ارسال کرد"
    UPDATED = "updated", "بروزرسانی کرد"
    APPROVED = "approved", "تأیید شد"
    REJECTED = "rejected", "رد شد"
    REPLIED = "replied", "پاسخ دریافت کرد"
    RESOLVED = "resolved", "حل شد"
    PAID = "paid", "پرداخت کرد"
    ISSUED = "issued", "صادر شد"
    REVEALED = "revealed", "مشاهده شد"
    MATCHED = "matched", "تطبیق یافت"
    NOTIFIED = "notified", "اعلان دریافت کرد"


class ActivityVisibility(models.TextChoices):
    """Visibility levels for timeline activities."""

    PRIVATE = "private", "خصوصی"
    ADMIN = "admin", "ادمین"

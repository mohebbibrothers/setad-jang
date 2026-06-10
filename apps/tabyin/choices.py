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

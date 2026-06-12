"""Choices for the notification engine."""

from django.db import models


class NotificationChannel(models.TextChoices):
    """Supported delivery channels."""

    IN_APP = "in_app", "داخل سامانه"
    EMAIL = "email", "ایمیل"
    SMS = "sms", "پیامک"
    WEBHOOK = "webhook", "وب‌هوک"


class NotificationEventStatus(models.TextChoices):
    """Lifecycle states for notification events."""

    PENDING = "pending", "در انتظار ارسال"
    PROCESSING = "processing", "در حال پردازش"
    SENT = "sent", "ارسال‌شده"
    PARTIAL = "partial", "ارسال ناقص"
    FAILED = "failed", "ناموفق"
    CANCELLED = "cancelled", "لغوشده"


class NotificationDeliveryStatus(models.TextChoices):
    """Delivery states per recipient/channel."""

    PENDING = "pending", "در انتظار"
    SENT = "sent", "ارسال‌شده"
    FAILED = "failed", "ناموفق"
    SKIPPED = "skipped", "ردشده"
    READ = "read", "خوانده‌شده"


class NotificationPriority(models.TextChoices):
    """Notification operational priority."""

    LOW = "low", "کم"
    NORMAL = "normal", "معمولی"
    HIGH = "high", "زیاد"
    URGENT = "urgent", "فوری"

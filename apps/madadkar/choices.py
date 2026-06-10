"""
Enums اپ مددکار.

تمام TextChoices مربوط به وضعیت حرکت، مشارکت و پرداخت.
"""

from django.db import models


class CampaignStatus(models.TextChoices):
    """وضعیت چرخه عمر حرکت."""

    DRAFT = "draft", "پیش‌نویس"
    PUBLISHED = "published", "منتشرشده"
    COMPLETED = "completed", "تکمیل‌شده"
    CLOSED = "closed", "بسته‌شده"


class ParticipationStatus(models.TextChoices):
    """وضعیت مشارکت کاربر در یک حرکت."""

    PENDING_PAYMENT = "pending_payment", "در انتظار پرداخت"
    PAID = "paid", "پرداخت‌شده"
    FAILED = "failed", "ناموفق"
    EXPIRED = "expired", "منقضی‌شده"


class PaymentStatus(models.TextChoices):
    """وضعیت تراکنش پرداخت."""

    PENDING = "pending", "در انتظار"
    SUCCESS = "success", "موفق"
    FAILED = "failed", "ناموفق"

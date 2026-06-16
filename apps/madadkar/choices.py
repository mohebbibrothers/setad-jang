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
    REFUNDED = "refunded", "بازپرداخت‌شده"


class PaymentStatus(models.TextChoices):
    """وضعیت تراکنش پرداخت."""

    PENDING = "pending", "در انتظار"
    SUCCESS = "success", "موفق"
    FAILED = "failed", "ناموفق"


class ReconciliationStatus(models.TextChoices):
    """وضعیت batch تطبیق مالی."""

    DRAFT = "draft", "پیش‌نویس"
    COMPLETED = "completed", "تکمیل‌شده"
    FAILED = "failed", "ناموفق"


class ReconciliationItemStatus(models.TextChoices):
    """وضعیت هر ردیف تطبیق مالی."""

    MATCHED = "matched", "تطبیق موفق"
    MISSING_INTERNAL = "missing_internal", "در سیستم داخلی پیدا نشد"
    AMOUNT_MISMATCH = "amount_mismatch", "عدم تطابق مبلغ"
    STATUS_MISMATCH = "status_mismatch", "عدم تطابق وضعیت"
    DUPLICATE_PROVIDER_REF = "duplicate_provider_ref", "شناسه تکراری در گزارش درگاه"


class PaymentEventKind(models.TextChoices):
    """نوع رویداد ledger پرداخت مددکار."""

    CREATED = "created", "ایجاد پرداخت"
    VERIFY_SUCCESS = "verify_success", "تأیید موفق"
    VERIFY_FAILED = "verify_failed", "تأیید ناموفق"
    AMOUNT_MISMATCH = "amount_mismatch", "عدم تطابق مبلغ"
    EXPIRED = "expired", "انقضای پرداخت"
    REFUND_REQUESTED = "refund_requested", "درخواست بازپرداخت"
    REFUND_APPROVED = "refund_approved", "تأیید بازپرداخت"
    REFUND_REJECTED = "refund_rejected", "رد بازپرداخت"
    REFUND_COMPLETED = "refund_completed", "تکمیل بازپرداخت"
    REFUND_FAILED = "refund_failed", "شکست بازپرداخت"
    ADJUSTMENT_APPLIED = "adjustment_applied", "اعمال اصلاح مالی"


class RefundStatus(models.TextChoices):
    """وضعیت workflow بازپرداخت مددکار."""

    PENDING_REVIEW = "pending_review", "در انتظار بررسی"
    APPROVED = "approved", "تأییدشده"
    REJECTED = "rejected", "ردشده"
    COMPLETED = "completed", "تکمیل‌شده"
    FAILED = "failed", "ناموفق"


class RefundReason(models.TextChoices):
    """دلیل استاندارد درخواست بازپرداخت."""

    DUPLICATE_PAYMENT = "duplicate_payment", "پرداخت تکراری"
    USER_REQUEST = "user_request", "درخواست کاربر"
    CAMPAIGN_CANCELED = "campaign_canceled", "لغو حرکت"
    PROVIDER_REVERSAL = "provider_reversal", "برگشت از سمت درگاه"
    ADMIN_CORRECTION = "admin_correction", "اصلاح ادمین"
    OTHER = "other", "سایر"


class FinancialAdjustmentType(models.TextChoices):
    """نوع اصلاح مالی کمپین."""

    CREDIT = "credit", "افزایش مبلغ مؤثر"
    DEBIT = "debit", "کاهش مبلغ مؤثر"


class FinancialAdjustmentStatus(models.TextChoices):
    """وضعیت workflow اصلاح مالی."""

    PENDING_REVIEW = "pending_review", "در انتظار بررسی"
    APPROVED = "approved", "تأییدشده"
    REJECTED = "rejected", "ردشده"
    APPLIED = "applied", "اعمال‌شده"

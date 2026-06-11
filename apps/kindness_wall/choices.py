"""Enumeration choices for Kindness Wall domain."""

from django.db import models


class ListingType(models.TextChoices):
    """The two fixed kinds of listings in Kindness Wall."""

    NEED_HELP = "need_help", "نیاز به کمک دارم"
    OFFER_HELP = "offer_help", "می‌خواهم کمک کنم"


class ListingStatus(models.TextChoices):
    """Lifecycle state for a Kindness Wall listing."""

    DRAFT = "draft", "پیش‌نویس"
    PENDING_REVIEW = "pending_review", "در انتظار بررسی"
    PUBLISHED = "published", "منتشرشده"
    REJECTED = "rejected", "ردشده"
    NEEDS_EDIT = "needs_edit", "نیازمند ویرایش"
    SUSPENDED = "suspended", "تعلیق‌شده"
    CLOSED = "closed", "بسته‌شده"
    EXPIRED = "expired", "منقضی‌شده"
    DELETED = "deleted", "حذف‌شده"


class ListingImageKind(models.TextChoices):
    """Image role in listing gallery."""

    COVER = "cover", "کاور"
    GALLERY = "gallery", "گالری"


class TagSource(models.TextChoices):
    """Source of a listing tag."""

    MANUAL = "manual", "دستی"
    AUTO_TITLE = "auto_title", "استخراج از عنوان"
    AUTO_DESCRIPTION = "auto_description", "استخراج از توضیحات"
    ADMIN = "admin", "ادمین"


class MatchStatus(models.TextChoices):
    """Lifecycle of a generated match."""

    ACTIVE = "active", "فعال"
    DISMISSED = "dismissed", "نادیده‌گرفته‌شده"
    CONTACTED = "contacted", "تماس گرفته‌شده"
    STALE = "stale", "قدیمی"
    EXPIRED = "expired", "منقضی‌شده"


class ReportReason(models.TextChoices):
    """Reason for reporting a listing."""

    SPAM = "spam", "اسپم"
    FRAUD = "fraud", "مشکوک به سوءاستفاده"
    WRONG_CATEGORY = "wrong_category", "دسته‌بندی اشتباه"
    INAPPROPRIATE = "inappropriate", "محتوای نامناسب"
    DUPLICATE = "duplicate", "تکراری"
    EXPIRED = "expired", "منقضی‌شده"
    CONTACT_INVALID = "contact_invalid", "شماره تماس نامعتبر"
    OTHER = "other", "سایر"


class ReportStatus(models.TextChoices):
    """Review state for listing reports."""

    PENDING = "pending", "در انتظار بررسی"
    REVIEWED = "reviewed", "بررسی‌شده"
    REJECTED = "rejected", "رد گزارش"


class DuplicateStatus(models.TextChoices):
    """Review state for duplicate candidates."""

    ACTIVE = "active", "فعال"
    DISMISSED = "dismissed", "نادیده‌گرفته‌شده"
    CONFIRMED = "confirmed", "تأیید تکراری بودن"

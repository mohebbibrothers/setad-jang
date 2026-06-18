# apps/r4j/choices.py
"""
R4J — Reward for Justice: Enumeration choices.

تمام انتخاب‌های ممکن برای فیلدهای مدل در این فایل تعریف می‌شوند
تا از تکرار string literal در سراسر پروژه جلوگیری شود.
"""

from __future__ import annotations

from django.db import models

# ============================================================
# Criminal — Personal
# ============================================================


class Gender(models.TextChoices):
    """جنسیت مجرم."""

    MALE = "male", "مرد"
    FEMALE = "female", "زن"
    UNKNOWN = "unknown", "نامشخص"


# ============================================================
# Criminal — Social Media Platforms
# ============================================================


class SocialPlatform(models.TextChoices):
    """پلتفرم‌های شبکه اجتماعی پشتیبانی‌شده."""

    TELEGRAM = "telegram", "تلگرام"
    TWITTER_X = "twitter_x", "توییتر / ایکس"
    INSTAGRAM = "instagram", "اینستاگرام"
    LINKEDIN = "linkedin", "لینکدین"
    FACEBOOK = "facebook", "فیسبوک"
    TIKTOK = "tiktok", "تیک‌تاک"
    TRUTH_SOCIAL = "truth_social", "تروث سوشال"
    YOUTUBE = "youtube", "یوتیوب"
    WEBSITE = "website", "وب‌سایت"
    OTHER = "other", "سایر"


# ============================================================
# Criminal — Attachment kinds
# ============================================================


class CriminalAttachmentKind(models.TextChoices):
    """نوع پیوست رسمی مجرم (آپلودشده توسط ادمین)."""

    IMAGE = "image", "تصویر"
    DOCUMENT = "document", "سند"
    VIDEO = "video", "ویدئو"
    AUDIO = "audio", "صدا"
    OTHER = "other", "سایر"


class EvidenceCustodyEventType(models.TextChoices):
    """Chain-of-custody event types for R4J evidence files."""

    UPLOADED = "uploaded", "آپلود شد"
    HASHED = "hashed", "هش شد"
    REVIEWED = "reviewed", "بررسی شد"
    TRANSFERRED = "transferred", "منتقل شد"
    REJECTED = "rejected", "رد شد"
    DELETED = "deleted", "حذف شد"


# ============================================================
# Investigation Case — Operational Workflow
# ============================================================


class InvestigationCaseStatus(models.TextChoices):
    """Operational lifecycle for R4J investigation cases."""

    NEW = "new", "جدید"
    TRIAGED = "triaged", "تریاژ شده"
    ASSIGNED = "assigned", "ارجاع شده"
    INVESTIGATING = "investigating", "در حال بررسی"
    WAITING_FOR_EVIDENCE = "waiting_for_evidence", "در انتظار مدرک"
    ESCALATED = "escalated", "ارجاع فوری"
    RESOLVED = "resolved", "حل شده"
    REJECTED = "rejected", "رد شده"
    CLOSED = "closed", "بسته شده"


class InvestigationCasePriority(models.TextChoices):
    """Operational priority for case queues and SLA calculations."""

    LOW = "low", "کم"
    MEDIUM = "medium", "متوسط"
    HIGH = "high", "زیاد"
    CRITICAL = "critical", "بحرانی"


class InvestigationCaseSeverity(models.TextChoices):
    """Impact severity of an R4J investigation case."""

    LOW = "low", "کم"
    MEDIUM = "medium", "متوسط"
    HIGH = "high", "زیاد"
    CRITICAL = "critical", "بحرانی"


class InvestigationCaseEventType(models.TextChoices):
    """Immutable timeline event types for R4J investigation cases."""

    CREATED = "created", "ایجاد شد"
    TRIAGED = "triaged", "تریاژ شد"
    ASSIGNED = "assigned", "ارجاع شد"
    PRIORITY_CHANGED = "priority_changed", "اولویت تغییر کرد"
    EVIDENCE_REQUESTED = "evidence_requested", "مدرک بیشتر درخواست شد"
    ESCALATED = "escalated", "ارجاع فوری شد"
    RESOLVED = "resolved", "حل شد"
    REJECTED = "rejected", "رد شد"
    CLOSED = "closed", "بسته شد"
    REOPENED = "reopened", "بازگشایی شد"


INVESTIGATION_CASE_TERMINAL_STATUSES: frozenset[str] = frozenset(
    [
        InvestigationCaseStatus.RESOLVED,
        InvestigationCaseStatus.REJECTED,
        InvestigationCaseStatus.CLOSED,
    ]
)


# ============================================================
# Report — Status (state machine)
# ============================================================


class ReportStatus(models.TextChoices):
    """
    وضعیت گزارش کاربر.

    State machine:
        PENDING
            ├── [admin review] → APPROVED
            ├── [admin review] → PARTIALLY_APPROVED
            ├── [admin review] → REJECTED
            └── [user request] → CANCEL_REQUESTED
        CANCEL_REQUESTED
            ├── [admin approve] → CANCELED
            └── [admin reject]  → PENDING
    """

    PENDING = "pending", "در انتظار بررسی"
    APPROVED = "approved", "تأیید شده"
    PARTIALLY_APPROVED = "partially_approved", "تأیید جزئی"
    REJECTED = "rejected", "رد شده"
    CANCEL_REQUESTED = "cancel_requested", "درخواست لغو"
    CANCELED = "canceled", "لغو شده"


# ── Transitions allowed for cancel request ──────────────────
#: از این وضعیت‌ها می‌توان درخواست لغو فرستاد.
REPORT_CANCELABLE_STATUSES: frozenset[str] = frozenset(
    [ReportStatus.PENDING]
)

#: وضعیت‌های نهایی — دیگر قابل تغییر نیستند (توسط کاربر).
REPORT_TERMINAL_STATUSES: frozenset[str] = frozenset(
    [
        ReportStatus.APPROVED,
        ReportStatus.PARTIALLY_APPROVED,
        ReportStatus.REJECTED,
        ReportStatus.CANCELED,
    ]
)


# ============================================================
# Report — Field Change Status (per-field approval)
# ============================================================


class ReportFieldChangeStatus(models.TextChoices):
    """
    وضعیت تک‌تک تغییرات پیشنهادی در یک گزارش.

    ادمین می‌تواند برای هر فیلد به‌صورت مستقل تصمیم بگیرد.
    """

    PENDING = "pending", "در انتظار بررسی"
    APPROVED = "approved", "تأیید شده"
    REJECTED = "rejected", "رد شده"


# ============================================================
# Bounty — Status (state machine)
# ============================================================


class BountyStatus(models.TextChoices):
    """
    وضعیت جایزه اعلامی کاربر.

    State machine:
        ACTIVE
            └── [user request] → CANCEL_REQUESTED
        CANCEL_REQUESTED
            ├── [admin approve] → CANCELED
            └── [admin reject]  → ACTIVE
    """

    ACTIVE = "active", "فعال"
    CANCEL_REQUESTED = "cancel_requested", "درخواست لغو"
    CANCELED = "canceled", "لغو شده"


#: وضعیت‌هایی که در محاسبه total bounty در نظر گرفته می‌شوند.
BOUNTY_ACTIVE_STATUSES: frozenset[str] = frozenset(
    [BountyStatus.ACTIVE, BountyStatus.CANCEL_REQUESTED]
)

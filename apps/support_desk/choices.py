"""Enumeration choices for the Support Desk domain."""

from django.db import models


class TicketStatus(models.TextChoices):
    """Workflow states for support tickets."""

    DRAFT = "draft", "پیش‌نویس"
    SUBMITTED = "submitted", "ثبت‌شده"
    OPEN = "open", "باز"
    IN_PROGRESS = "in_progress", "در حال بررسی"
    WAITING_FOR_USER = "waiting_for_user", "منتظر پاسخ کاربر"
    WAITING_FOR_ADMIN = "waiting_for_admin", "منتظر پاسخ ادمین"
    RESOLVED = "resolved", "حل‌شده"
    CLOSED = "closed", "بسته‌شده"
    REOPENED = "reopened", "بازگشایی‌شده"
    ESCALATED = "escalated", "ارجاع/فوری‌شده"
    SPAM = "spam", "اسپم"
    ARCHIVED = "archived", "آرشیوشده"


class TicketPriority(models.TextChoices):
    """Operational priority for support tickets."""

    LOW = "low", "کم"
    NORMAL = "normal", "معمولی"
    HIGH = "high", "زیاد"
    URGENT = "urgent", "فوری"


class TicketSeverity(models.TextChoices):
    """Impact severity for support tickets."""

    MINOR = "minor", "جزئی"
    MAJOR = "major", "مهم"
    CRITICAL = "critical", "بحرانی"
    BLOCKER = "blocker", "مسدودکننده"


class TicketChannel(models.TextChoices):
    """Ticket creation channel."""

    WEB = "web", "وب‌سایت"
    ADMIN = "admin", "ادمین"
    SYSTEM = "system", "سیستم"
    IMPORT = "import", "ورودی/ایمپورت"


class TicketMessageType(models.TextChoices):
    """Timeline message and event types."""

    USER_MESSAGE = "user_message", "پیام کاربر"
    ADMIN_REPLY = "admin_reply", "پاسخ ادمین"
    INTERNAL_NOTE = "internal_note", "یادداشت داخلی"
    SYSTEM_EVENT = "system_event", "رویداد سیستمی"
    STATUS_CHANGE = "status_change", "تغییر وضعیت"
    ASSIGNMENT_CHANGE = "assignment_change", "تغییر مسئول"
    SLA_EVENT = "sla_event", "رویداد SLA"


class AttachmentKind(models.TextChoices):
    """Attachment semantic kind."""

    SCREENSHOT = "screenshot", "اسکرین‌شات"
    IMAGE = "image", "تصویر"
    DOCUMENT = "document", "سند"
    RECEIPT = "receipt", "رسید"
    OTHER = "other", "سایر"


class AttachmentVisibility(models.TextChoices):
    """Attachment visibility boundary."""

    PUBLIC = "public", "قابل مشاهده برای کاربر و ادمین"
    INTERNAL_ONLY = "internal_only", "فقط داخلی"


class TagSource(models.TextChoices):
    """Source of a tag assigned to a ticket."""

    USER = "user", "کاربر"
    ADMIN = "admin", "ادمین"
    AUTO_TRIAGE = "auto_triage", "تریاژ هوشمند"
    SYSTEM = "system", "سیستم"


class SLAEventType(models.TextChoices):
    """SLA lifecycle events."""

    POLICY_APPLIED = "policy_applied", "اعمال SLA"
    PAUSED = "paused", "توقف SLA"
    RESUMED = "resumed", "ادامه SLA"
    FIRST_RESPONSE_BREACHED = "first_response_breached", "نقض زمان اولین پاسخ"
    RESOLUTION_BREACHED = "resolution_breached", "نقض زمان حل"
    ESCALATED = "escalated", "ارجاع به سطح بالاتر"


class DuplicateReviewStatus(models.TextChoices):
    """Review states for duplicate ticket candidates."""

    ACTIVE = "active", "فعال"
    DISMISSED = "dismissed", "نادیده‌گرفته‌شده"
    CONFIRMED = "confirmed", "تأیید تکراری بودن"


class KnowledgeArticleStatus(models.TextChoices):
    """Publication lifecycle for support knowledge base articles."""

    DRAFT = "draft", "پیش‌نویس"
    PUBLISHED = "published", "منتشرشده"
    ARCHIVED = "archived", "آرشیوشده"

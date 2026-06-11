"""
Database models for the Support Desk domain.

The app is designed as an enterprise-grade help desk, not a simple contact form:
dynamic departments, fully tree-based categories, admin-managed ticket types,
SLA policies, auditable conversation timeline, attachments, tags, assignment and
status histories, satisfaction ratings, and duplicate detection foundations.
"""

from __future__ import annotations

import secrets
import uuid
from typing import Any

from django.conf import settings
from django.db import models
from django.utils import timezone
from django.utils.text import slugify

from apps.core.models import BaseModel
from apps.support_desk.choices import (
    AttachmentKind,
    AttachmentVisibility,
    DuplicateReviewStatus,
    SLAEventType,
    TagSource,
    TicketChannel,
    TicketMessageType,
    TicketPriority,
    TicketSeverity,
    TicketStatus,
)
from apps.support_desk.managers import (
    SupportCategoryAllManager,
    SupportCategoryManager,
    SupportTicketAllManager,
    SupportTicketManager,
)
from apps.support_desk.validators import (
    validate_attachment_extension,
    validate_attachment_size,
    validate_duplicate_score,
)


def support_attachment_upload_path(instance: SupportTicketAttachment, filename: str) -> str:
    """Build upload path for support ticket attachments."""
    return f"support_desk/tickets/{instance.ticket_id}/attachments/{filename}"


def _unique_slug(*, model: type[models.Model], value: str, max_length: int, exclude_pk: int | None = None) -> str:
    """Generate collision-safe unicode slug for a model."""
    base = slugify(value, allow_unicode=True)[:max_length] or uuid.uuid4().hex[:12]
    candidate = base
    suffix = 2
    manager = getattr(model, "all_objects", model.objects)
    while manager.filter(slug=candidate).exclude(pk=exclude_pk).exists():
        suffix_text = f"-{suffix}"
        candidate = f"{base[: max_length - len(suffix_text)]}{suffix_text}"
        suffix += 1
    return candidate


def _normalize_text(value: str) -> str:
    """Normalize Persian/Arabic text for tags and search documents."""
    replacements = {"ي": "ی", "ك": "ک", "ۀ": "ه", "ة": "ه", "آ": "ا", "أ": "ا", "إ": "ا", "‌": " "}
    value = (value or "").strip().lower()
    for source, target in replacements.items():
        value = value.replace(source, target)
    return " ".join(value.split())


def _build_ticket_number() -> str:
    """Build a user-friendly, low-guessability support ticket number."""
    now = timezone.now()
    prefix = f"SUP-{now:%Y%m}"
    sequence = SupportTicket.all_objects.filter(created_at__year=now.year, created_at__month=now.month).count() + 1
    for _attempt in range(20):
        random_part = secrets.token_hex(2).upper()
        candidate = f"{prefix}-{sequence:04d}-{random_part}"
        if not SupportTicket.all_objects.filter(ticket_number=candidate).exists():
            return candidate
        sequence += 1
    return f"{prefix}-{uuid.uuid4().hex[:8].upper()}"


class SupportDepartment(BaseModel):
    """Admin-managed operational department/queue for support tickets."""

    uuid = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    title = models.CharField(max_length=180, unique=True)
    slug = models.SlugField(max_length=220, unique=True, allow_unicode=True, blank=True)
    description = models.TextField(blank=True)
    default_assignee = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="support_default_departments",
    )
    order = models.PositiveIntegerField(default=0)

    class Meta:
        verbose_name = "دپارتمان پشتیبانی"
        verbose_name_plural = "دپارتمان‌های پشتیبانی"
        ordering = ["order", "title"]
        indexes = [models.Index(fields=["is_active", "order"])]

    def __str__(self) -> str:
        return self.title

    def save(self, *args: Any, **kwargs: Any) -> None:
        """Generate stable unique slug."""
        if not self.slug:
            self.slug = _unique_slug(model=SupportDepartment, value=self.title, max_length=220, exclude_pk=self.pk)
        super().save(*args, **kwargs)


class SupportCategory(BaseModel):
    """Fully dynamic admin-managed tree category for support tickets."""

    parent = models.ForeignKey(
        "self",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="children",
    )
    department = models.ForeignKey(SupportDepartment, on_delete=models.PROTECT, related_name="categories")
    title = models.CharField(max_length=180)
    slug = models.SlugField(max_length=220, unique=True, allow_unicode=True, blank=True)
    path = models.CharField(max_length=700, unique=True, blank=True, db_index=True)
    depth = models.PositiveSmallIntegerField(default=0)
    description = models.TextField(blank=True)
    icon = models.CharField(max_length=80, blank=True)
    order = models.PositiveIntegerField(default=0)
    tickets_count = models.PositiveIntegerField(default=0)
    open_tickets_count = models.PositiveIntegerField(default=0)

    objects = SupportCategoryManager()
    all_objects = SupportCategoryAllManager()

    class Meta:
        verbose_name = "دسته‌بندی پشتیبانی"
        verbose_name_plural = "دسته‌بندی‌های پشتیبانی"
        ordering = ["depth", "order", "title"]
        indexes = [
            models.Index(fields=["department", "parent", "is_active", "order"]),
            models.Index(fields=["path"]),
        ]
        constraints = [
            models.UniqueConstraint(fields=["parent", "department", "title"], name="uniq_support_category_parent_department_title"),
            models.UniqueConstraint(
                fields=["department", "title"],
                condition=models.Q(parent__isnull=True),
                name="uniq_support_root_category_department_title",
            ),
        ]

    def __str__(self) -> str:
        return self.title

    def save(self, *args: Any, **kwargs: Any) -> None:
        """Generate slug/path/depth consistently for the support category tree."""
        if not self.slug:
            self.slug = _unique_slug(model=SupportCategory, value=self.title, max_length=220, exclude_pk=self.pk)
        if self.parent_id:
            parent = self.parent
            self.depth = parent.depth + 1
            self.path = f"{parent.path.rstrip('/')}/{self.slug}/"
        else:
            self.depth = 0
            self.path = f"/{self.slug}/"
        super().save(*args, **kwargs)


class SupportSLAPolicy(BaseModel):
    """Admin-managed SLA policy used to calculate ticket deadlines."""

    title = models.CharField(max_length=180, unique=True)
    slug = models.SlugField(max_length=220, unique=True, allow_unicode=True, blank=True)
    department = models.ForeignKey(SupportDepartment, on_delete=models.PROTECT, null=True, blank=True, related_name="sla_policies")
    priority = models.CharField(max_length=20, choices=TicketPriority.choices, default=TicketPriority.NORMAL)
    severity = models.CharField(max_length=20, choices=TicketSeverity.choices, default=TicketSeverity.MINOR)
    first_response_minutes = models.PositiveIntegerField(default=24 * 60)
    resolution_minutes = models.PositiveIntegerField(default=72 * 60)
    business_hours_only = models.BooleanField(default=False)
    pause_when_waiting_for_user = models.BooleanField(default=True)
    escalate_on_breach = models.BooleanField(default=True)
    order = models.PositiveIntegerField(default=0)

    class Meta:
        verbose_name = "سیاست SLA پشتیبانی"
        verbose_name_plural = "سیاست‌های SLA پشتیبانی"
        ordering = ["order", "title"]
        indexes = [models.Index(fields=["department", "priority", "severity", "is_active"])]

    def __str__(self) -> str:
        return self.title

    def save(self, *args: Any, **kwargs: Any) -> None:
        """Generate stable unique slug."""
        if not self.slug:
            self.slug = _unique_slug(model=SupportSLAPolicy, value=self.title, max_length=220, exclude_pk=self.pk)
        super().save(*args, **kwargs)


class SupportTicketType(BaseModel):
    """Admin-managed dynamic ticket reason/type with default routing hints."""

    code = models.SlugField(max_length=80, unique=True, allow_unicode=False)
    title = models.CharField(max_length=180, unique=True)
    description = models.TextField(blank=True)
    default_department = models.ForeignKey(SupportDepartment, on_delete=models.PROTECT, null=True, blank=True, related_name="default_ticket_types")
    default_category = models.ForeignKey(SupportCategory, on_delete=models.PROTECT, null=True, blank=True, related_name="default_ticket_types")
    default_priority = models.CharField(max_length=20, choices=TicketPriority.choices, default=TicketPriority.NORMAL)
    default_severity = models.CharField(max_length=20, choices=TicketSeverity.choices, default=TicketSeverity.MINOR)
    default_sla_policy = models.ForeignKey(SupportSLAPolicy, on_delete=models.PROTECT, null=True, blank=True, related_name="ticket_types")
    order = models.PositiveIntegerField(default=0)

    class Meta:
        verbose_name = "نوع تیکت پشتیبانی"
        verbose_name_plural = "انواع تیکت پشتیبانی"
        ordering = ["order", "title"]
        indexes = [models.Index(fields=["is_active", "order"])]

    def __str__(self) -> str:
        return self.title


class SupportTicket(BaseModel):
    """Main support ticket record with SLA and operational counters."""

    uuid = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    ticket_number = models.CharField(max_length=40, unique=True, blank=True, db_index=True)
    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="support_tickets")
    department = models.ForeignKey(SupportDepartment, on_delete=models.PROTECT, related_name="tickets")
    category = models.ForeignKey(SupportCategory, on_delete=models.PROTECT, related_name="tickets")
    ticket_type = models.ForeignKey(SupportTicketType, on_delete=models.PROTECT, related_name="tickets")
    subject = models.CharField(max_length=260)
    description_snapshot = models.TextField()
    status = models.CharField(max_length=30, choices=TicketStatus.choices, default=TicketStatus.DRAFT, db_index=True)
    priority = models.CharField(max_length=20, choices=TicketPriority.choices, default=TicketPriority.NORMAL, db_index=True)
    severity = models.CharField(max_length=20, choices=TicketSeverity.choices, default=TicketSeverity.MINOR, db_index=True)
    channel = models.CharField(max_length=20, choices=TicketChannel.choices, default=TicketChannel.WEB)
    assigned_to = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="assigned_support_tickets")

    submitted_at = models.DateTimeField(null=True, blank=True)
    first_admin_response_at = models.DateTimeField(null=True, blank=True)
    last_user_message_at = models.DateTimeField(null=True, blank=True)
    last_admin_message_at = models.DateTimeField(null=True, blank=True)
    last_activity_at = models.DateTimeField(default=timezone.now, db_index=True)
    resolved_at = models.DateTimeField(null=True, blank=True)
    closed_at = models.DateTimeField(null=True, blank=True)
    reopened_at = models.DateTimeField(null=True, blank=True)
    escalated_at = models.DateTimeField(null=True, blank=True)
    escalated_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="escalated_support_tickets")
    escalation_reason = models.TextField(blank=True)

    applied_sla_policy = models.ForeignKey(SupportSLAPolicy, on_delete=models.SET_NULL, null=True, blank=True, related_name="tickets")
    first_response_due_at = models.DateTimeField(null=True, blank=True)
    resolution_due_at = models.DateTimeField(null=True, blank=True)
    sla_breached_at = models.DateTimeField(null=True, blank=True, db_index=True)
    sla_paused_at = models.DateTimeField(null=True, blank=True)
    sla_total_paused_seconds = models.PositiveIntegerField(default=0)

    message_count = models.PositiveIntegerField(default=0)
    attachment_count = models.PositiveIntegerField(default=0)
    internal_note_count = models.PositiveIntegerField(default=0)
    reopen_count = models.PositiveIntegerField(default=0)
    satisfaction_rating_snapshot = models.PositiveSmallIntegerField(null=True, blank=True)
    search_document = models.TextField(blank=True, default="")

    objects = SupportTicketManager()
    all_objects = SupportTicketAllManager()

    class Meta:
        verbose_name = "تیکت پشتیبانی"
        verbose_name_plural = "تیکت‌های پشتیبانی"
        ordering = ["-last_activity_at", "-created_at"]
        indexes = [
            models.Index(fields=["owner", "status", "-last_activity_at"]),
            models.Index(fields=["department", "status", "priority", "-last_activity_at"]),
            models.Index(fields=["assigned_to", "status", "-last_activity_at"]),
            models.Index(fields=["category", "status"]),
            models.Index(fields=["ticket_type", "status"]),
            models.Index(fields=["first_response_due_at"]),
            models.Index(fields=["resolution_due_at"]),
        ]

    def __str__(self) -> str:
        return f"{self.ticket_number or 'SUP'} — {self.subject}"

    def save(self, *args: Any, **kwargs: Any) -> None:
        """Generate ticket number and search document."""
        if not self.ticket_number:
            self.ticket_number = _build_ticket_number()
        self.search_document = " ".join(
            [
                self.ticket_number,
                self.subject,
                self.description_snapshot,
                self.department.title if self.department_id else "",
                self.category.title if self.category_id else "",
                self.ticket_type.title if self.ticket_type_id else "",
            ]
        ).strip()
        super().save(*args, **kwargs)

    @property
    def is_reopenable(self) -> bool:
        """Return whether a closed/resolved ticket can be reopened by policy."""
        if self.status not in {TicketStatus.RESOLVED, TicketStatus.CLOSED}:
            return False
        reference = self.closed_at or self.resolved_at
        return bool(reference and reference + timezone.timedelta(days=7) > timezone.now())


class SupportTicketMessage(BaseModel):
    """A public or internal timeline entry for a support ticket."""

    ticket = models.ForeignKey(SupportTicket, on_delete=models.CASCADE, related_name="messages")
    author = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="support_messages")
    message_type = models.CharField(max_length=30, choices=TicketMessageType.choices)
    body = models.TextField()
    is_internal = models.BooleanField(default=False)
    is_from_staff = models.BooleanField(default=False)
    edited_at = models.DateTimeField(null=True, blank=True)
    deleted_at = models.DateTimeField(null=True, blank=True)
    metadata = models.JSONField(default=dict, blank=True)

    class Meta:
        verbose_name = "پیام تیکت پشتیبانی"
        verbose_name_plural = "پیام‌های تیکت پشتیبانی"
        ordering = ["created_at", "id"]
        indexes = [models.Index(fields=["ticket", "created_at"]), models.Index(fields=["ticket", "is_internal", "created_at"])]

    def __str__(self) -> str:
        return f"{self.ticket.ticket_number} — {self.get_message_type_display()}"


class SupportTicketAttachment(BaseModel):
    """Validated attachment connected to a ticket/message."""

    ticket = models.ForeignKey(SupportTicket, on_delete=models.CASCADE, related_name="attachments")
    message = models.ForeignKey(SupportTicketMessage, on_delete=models.CASCADE, null=True, blank=True, related_name="attachments")
    uploaded_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="support_attachments")
    file = models.FileField(upload_to=support_attachment_upload_path, validators=[validate_attachment_extension, validate_attachment_size])
    original_filename = models.CharField(max_length=260)
    content_type = models.CharField(max_length=120, blank=True)
    file_size = models.PositiveIntegerField(default=0)
    attachment_kind = models.CharField(max_length=30, choices=AttachmentKind.choices, default=AttachmentKind.OTHER)
    visibility = models.CharField(max_length=30, choices=AttachmentVisibility.choices, default=AttachmentVisibility.PUBLIC)

    class Meta:
        verbose_name = "ضمیمه تیکت پشتیبانی"
        verbose_name_plural = "ضمیمه‌های تیکت پشتیبانی"
        ordering = ["created_at"]
        indexes = [models.Index(fields=["ticket", "visibility", "created_at"])]

    def __str__(self) -> str:
        return self.original_filename


class SupportTag(BaseModel):
    """Global normalized support tag dictionary."""

    name = models.CharField(max_length=120, unique=True)
    slug = models.SlugField(max_length=160, unique=True, allow_unicode=True, blank=True)
    normalized_name = models.CharField(max_length=160, unique=True, db_index=True)
    usage_count = models.PositiveIntegerField(default=0)

    class Meta:
        verbose_name = "تگ پشتیبانی"
        verbose_name_plural = "تگ‌های پشتیبانی"
        ordering = ["normalized_name"]

    def __str__(self) -> str:
        return self.name

    def save(self, *args: Any, **kwargs: Any) -> None:
        """Generate slug and normalized tag name."""
        if not self.normalized_name:
            self.normalized_name = _normalize_text(self.name)
        if not self.slug:
            self.slug = _unique_slug(model=SupportTag, value=self.normalized_name, max_length=160, exclude_pk=self.pk)
        super().save(*args, **kwargs)


class SupportTicketTag(BaseModel):
    """Tag assignment for a support ticket."""

    ticket = models.ForeignKey(SupportTicket, on_delete=models.CASCADE, related_name="ticket_tags")
    tag = models.ForeignKey(SupportTag, on_delete=models.PROTECT, related_name="ticket_tags")
    source = models.CharField(max_length=30, choices=TagSource.choices, default=TagSource.ADMIN)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["ticket", "tag"], name="uniq_support_ticket_tag")]
        indexes = [models.Index(fields=["tag", "source"]), models.Index(fields=["ticket", "source"])]

    def __str__(self) -> str:
        return f"{self.ticket.ticket_number} — {self.tag.name}"


class SupportCannedResponse(BaseModel):
    """Admin-managed reusable response macro."""

    department = models.ForeignKey(SupportDepartment, on_delete=models.PROTECT, null=True, blank=True, related_name="canned_responses")
    category = models.ForeignKey(SupportCategory, on_delete=models.PROTECT, null=True, blank=True, related_name="canned_responses")
    title = models.CharField(max_length=180, unique=True)
    body = models.TextField()
    usage_count = models.PositiveIntegerField(default=0)

    class Meta:
        verbose_name = "پاسخ آماده پشتیبانی"
        verbose_name_plural = "پاسخ‌های آماده پشتیبانی"
        ordering = ["title"]
        indexes = [models.Index(fields=["department", "category", "is_active"])]

    def __str__(self) -> str:
        return self.title


class SupportTicketAssignment(BaseModel):
    """Immutable-ish assignment history for support tickets."""

    ticket = models.ForeignKey(SupportTicket, on_delete=models.CASCADE, related_name="assignment_history")
    assigned_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="support_assignments_made")
    from_assignee = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="support_assignments_from")
    assigned_to = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="support_assignments_to")
    department = models.ForeignKey(SupportDepartment, on_delete=models.PROTECT, null=True, blank=True, related_name="assignment_history")
    reason = models.TextField(blank=True)

    class Meta:
        indexes = [models.Index(fields=["ticket", "-created_at"]), models.Index(fields=["assigned_to", "-created_at"])]


class SupportTicketStatusHistory(BaseModel):
    """Status transition history for support tickets."""

    ticket = models.ForeignKey(SupportTicket, on_delete=models.CASCADE, related_name="status_history")
    changed_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True, related_name="support_status_changes")
    from_status = models.CharField(max_length=30, choices=TicketStatus.choices, blank=True)
    to_status = models.CharField(max_length=30, choices=TicketStatus.choices)
    reason = models.TextField(blank=True)

    class Meta:
        indexes = [models.Index(fields=["ticket", "-created_at"]), models.Index(fields=["to_status", "-created_at"])]


class SupportSLAEvent(BaseModel):
    """SLA lifecycle event for audit and analytics."""

    ticket = models.ForeignKey(SupportTicket, on_delete=models.CASCADE, related_name="sla_events")
    event_type = models.CharField(max_length=40, choices=SLAEventType.choices)
    occurred_at = models.DateTimeField(default=timezone.now)
    metadata = models.JSONField(default=dict, blank=True)

    class Meta:
        indexes = [models.Index(fields=["ticket", "occurred_at"]), models.Index(fields=["event_type", "occurred_at"])]


class SupportTicketSatisfaction(BaseModel):
    """User-submitted satisfaction rating after ticket resolution."""

    ticket = models.OneToOneField(SupportTicket, on_delete=models.CASCADE, related_name="satisfaction")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="support_satisfaction_ratings")
    rating = models.PositiveSmallIntegerField()
    comment = models.TextField(blank=True)

    class Meta:
        constraints = [models.CheckConstraint(name="support_satisfaction_rating_1_5", condition=models.Q(rating__gte=1, rating__lte=5))]
        indexes = [models.Index(fields=["rating", "-created_at"])]

    def __str__(self) -> str:
        return f"{self.ticket.ticket_number} — {self.rating}"


class SupportDuplicateCandidate(BaseModel):
    """Potential duplicate ticket relation surfaced by smart triage."""

    ticket = models.ForeignKey(SupportTicket, on_delete=models.CASCADE, related_name="duplicate_candidates")
    candidate_ticket = models.ForeignKey(SupportTicket, on_delete=models.CASCADE, related_name="duplicate_of_candidates")
    score = models.PositiveSmallIntegerField(validators=[validate_duplicate_score])
    reason = models.TextField(blank=True)
    status = models.CharField(max_length=20, choices=DuplicateReviewStatus.choices, default=DuplicateReviewStatus.ACTIVE)
    reviewed_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="support_duplicate_reviews")
    reviewed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["ticket", "candidate_ticket"], name="uniq_support_duplicate_candidate"),
            models.CheckConstraint(name="support_duplicate_not_self", condition=~models.Q(ticket=models.F("candidate_ticket"))),
        ]
        indexes = [models.Index(fields=["ticket", "status", "-score"]), models.Index(fields=["status", "-created_at"])]

    def __str__(self) -> str:
        return f"{self.ticket.ticket_number} ~ {self.candidate_ticket.ticket_number} ({self.score})"

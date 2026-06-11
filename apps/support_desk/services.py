"""Business services for Support Desk workflows and mutations."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from django.db import transaction
from django.db.models import Count
from django.utils import timezone

from apps.support_desk.choices import (
    DuplicateReviewStatus,
    SLAEventType,
    TicketMessageType,
    TicketPriority,
    TicketSeverity,
    TicketStatus,
)
from apps.support_desk.models import (
    SupportCategory,
    SupportDepartment,
    SupportDuplicateCandidate,
    SupportSLAEvent,
    SupportSLAPolicy,
    SupportTag,
    SupportTicket,
    SupportTicketAssignment,
    SupportTicketAttachment,
    SupportTicketMessage,
    SupportTicketSatisfaction,
    SupportTicketStatusHistory,
    SupportTicketTag,
    SupportTicketType,
)


class SupportDeskServiceError(Exception):
    """Base service-layer exception for Support Desk."""


class SupportPermissionError(SupportDeskServiceError):
    """Raised when a support permission boundary is violated."""


class SupportTicketStateError(SupportDeskServiceError):
    """Raised when an invalid ticket workflow transition is requested."""


class SupportTaxonomyTreeError(SupportDeskServiceError):
    """Raised when taxonomy tree invariants would be violated."""


@dataclass(frozen=True)
class SupportTriageSuggestion:
    """Smart triage suggestion output."""

    department: SupportDepartment | None
    category: SupportCategory | None
    ticket_type: SupportTicketType | None
    priority: str
    severity: str
    sla_policy: SupportSLAPolicy | None
    duplicate_warning: bool
    similar_ticket_ids: list[int]
    reason_codes: list[str]
    score: int


_OPEN_STATUSES = {
    TicketStatus.SUBMITTED,
    TicketStatus.OPEN,
    TicketStatus.IN_PROGRESS,
    TicketStatus.WAITING_FOR_USER,
    TicketStatus.WAITING_FOR_ADMIN,
    TicketStatus.REOPENED,
    TicketStatus.ESCALATED,
}
_USER_REPLY_ALLOWED_STATUSES = {
    TicketStatus.SUBMITTED,
    TicketStatus.OPEN,
    TicketStatus.IN_PROGRESS,
    TicketStatus.WAITING_FOR_USER,
    TicketStatus.REOPENED,
    TicketStatus.ESCALATED,
}
_ADMIN_REPLY_ALLOWED_STATUSES = {
    TicketStatus.SUBMITTED,
    TicketStatus.OPEN,
    TicketStatus.IN_PROGRESS,
    TicketStatus.WAITING_FOR_ADMIN,
    TicketStatus.REOPENED,
    TicketStatus.ESCALATED,
}
_TERMINAL_STATUSES = {TicketStatus.CLOSED, TicketStatus.ARCHIVED, TicketStatus.SPAM}


# ---------------------------------------------------------------------------
# Taxonomy services
# ---------------------------------------------------------------------------


@transaction.atomic
def create_department(*, title: str, description: str = "", default_assignee: Any | None = None, order: int = 0) -> SupportDepartment:
    """Create an admin-managed support department."""
    return SupportDepartment.objects.create(title=title.strip(), description=description.strip(), default_assignee=default_assignee, order=order)


@transaction.atomic
def update_department(*, department: SupportDepartment, **fields: Any) -> SupportDepartment:
    """Update support department metadata through service layer."""
    allowed = {"title", "description", "default_assignee", "order", "is_active"}
    update_fields: list[str] = []
    for field, value in fields.items():
        if field not in allowed:
            continue
        if isinstance(value, str):
            value = value.strip()
        if getattr(department, field) != value:
            setattr(department, field, value)
            update_fields.append(field)
    if update_fields:
        update_fields.append("updated_at")
        department.save(update_fields=list(set(update_fields)))
    return department


@transaction.atomic
def deactivate_department(*, department: SupportDepartment) -> SupportDepartment:
    """Deactivate a department only when it has no open tickets."""
    if SupportTicket.objects.open_queue().filter(department=department).exists():
        raise SupportDeskServiceError("دپارتمانی که تیکت باز دارد قابل غیرفعال‌سازی نیست.")
    department.is_active = False
    department.save(update_fields=["is_active", "updated_at"])
    return department


def _assert_valid_category_parent(*, category: SupportCategory | None = None, parent: SupportCategory | None = None, department: SupportDepartment | None = None) -> None:
    """Prevent self-parenting, cross-department moves and tree cycles."""
    if parent is None:
        return
    if department is not None and parent.department_id != department.pk:
        raise SupportTaxonomyTreeError("دسته والد باید متعلق به همان دپارتمان باشد.")
    if category is None:
        return
    if parent.pk == category.pk:
        raise SupportTaxonomyTreeError("دسته‌بندی نمی‌تواند والد خودش باشد.")
    if parent.path.startswith(category.path):
        raise SupportTaxonomyTreeError("انتقال دسته‌بندی به یکی از زیرشاخه‌های خودش مجاز نیست.")


@transaction.atomic
def create_category(*, department: SupportDepartment, title: str, parent: SupportCategory | None = None, description: str = "", icon: str = "", order: int = 0) -> SupportCategory:
    """Create an admin-managed support category with tree safety checks."""
    _assert_valid_category_parent(parent=parent, department=department)
    return SupportCategory.all_objects.create(
        department=department,
        parent=parent,
        title=title.strip(),
        description=description.strip(),
        icon=icon.strip(),
        order=order,
    )


def _refresh_descendant_paths(*, category: SupportCategory) -> None:
    """Re-save descendants so path/depth remain correct after moving a category."""
    for child in SupportCategory.all_objects.filter(parent=category).order_by("order", "title"):
        child.save(update_fields=["depth", "path", "updated_at"])
        _refresh_descendant_paths(category=child)


@transaction.atomic
def update_category(*, category: SupportCategory, **fields: Any) -> SupportCategory:
    """Update a category while keeping tree invariants intact."""
    parent = fields.get("parent", category.parent)
    department = fields.get("department", category.department)
    _assert_valid_category_parent(category=category, parent=parent, department=department)
    allowed = {"department", "parent", "title", "description", "icon", "order", "is_active"}
    update_fields: list[str] = []
    for field, value in fields.items():
        if field not in allowed:
            continue
        if isinstance(value, str):
            value = value.strip()
        if getattr(category, field) != value:
            setattr(category, field, value)
            update_fields.append(field)
    if update_fields:
        update_fields.extend(["depth", "path", "updated_at"])
        category.save(update_fields=list(set(update_fields)))
        _refresh_descendant_paths(category=category)
    return category


@transaction.atomic
def deactivate_category(*, category: SupportCategory) -> SupportCategory:
    """Deactivate a category only when no active child/open ticket depends on it."""
    if SupportCategory.all_objects.filter(parent=category, is_active=True).exists():
        raise SupportTaxonomyTreeError("برای غیرفعال‌سازی این دسته ابتدا زیرشاخه‌های فعال آن را غیرفعال کنید.")
    if SupportTicket.objects.open_queue().filter(category=category).exists():
        raise SupportTaxonomyTreeError("دسته‌ای که تیکت باز دارد قابل غیرفعال‌سازی نیست.")
    category.is_active = False
    category.save(update_fields=["is_active", "updated_at"])
    return category


# ---------------------------------------------------------------------------
# Ticket creation and SLA
# ---------------------------------------------------------------------------


def resolve_sla_policy(*, department: SupportDepartment | None, ticket_type: SupportTicketType | None, priority: str, severity: str) -> SupportSLAPolicy | None:
    """Resolve the best active SLA policy for department/type/priority/severity."""
    if ticket_type and ticket_type.default_sla_policy_id:
        return ticket_type.default_sla_policy
    candidates = SupportSLAPolicy.objects.filter(priority=priority, severity=severity)
    if department is not None:
        department_policy = candidates.filter(department=department).order_by("order", "title").first()
        if department_policy is not None:
            return department_policy
    return candidates.filter(department__isnull=True).order_by("order", "title").first() or SupportSLAPolicy.objects.order_by("order", "title").first()


def _apply_sla(*, ticket: SupportTicket, policy: SupportSLAPolicy | None, now=None) -> None:
    """Apply SLA deadlines to a ticket and write an SLA event."""
    now = now or timezone.now()
    if policy is None:
        return
    ticket.applied_sla_policy = policy
    ticket.first_response_due_at = now + timezone.timedelta(minutes=policy.first_response_minutes)
    ticket.resolution_due_at = now + timezone.timedelta(minutes=policy.resolution_minutes)
    ticket.save(update_fields=["applied_sla_policy", "first_response_due_at", "resolution_due_at", "updated_at"])
    SupportSLAEvent.objects.create(
        ticket=ticket,
        event_type=SLAEventType.POLICY_APPLIED,
        occurred_at=now,
        metadata={"policy_id": policy.pk, "first_response_minutes": policy.first_response_minutes, "resolution_minutes": policy.resolution_minutes},
    )


@transaction.atomic
def create_sla_policy(
    *,
    title: str,
    department: SupportDepartment | None = None,
    priority: str = TicketPriority.NORMAL,
    severity: str = TicketSeverity.MINOR,
    first_response_minutes: int = 24 * 60,
    resolution_minutes: int = 72 * 60,
    business_hours_only: bool = False,
    pause_when_waiting_for_user: bool = True,
    escalate_on_breach: bool = True,
    order: int = 0,
) -> SupportSLAPolicy:
    """Create an admin-managed SLA policy."""
    return SupportSLAPolicy.objects.create(
        title=title.strip(),
        department=department,
        priority=priority,
        severity=severity,
        first_response_minutes=first_response_minutes,
        resolution_minutes=resolution_minutes,
        business_hours_only=business_hours_only,
        pause_when_waiting_for_user=pause_when_waiting_for_user,
        escalate_on_breach=escalate_on_breach,
        order=order,
    )


@transaction.atomic
def update_sla_policy(*, policy: SupportSLAPolicy, **fields: Any) -> SupportSLAPolicy:
    """Update an SLA policy through the service layer."""
    allowed = {"title", "department", "priority", "severity", "first_response_minutes", "resolution_minutes", "business_hours_only", "pause_when_waiting_for_user", "escalate_on_breach", "order", "is_active"}
    update_fields: list[str] = []
    for field, value in fields.items():
        if field not in allowed:
            continue
        if isinstance(value, str) and field == "title":
            value = value.strip()
        if getattr(policy, field) != value:
            setattr(policy, field, value)
            update_fields.append(field)
    if update_fields:
        update_fields.append("updated_at")
        policy.save(update_fields=list(set(update_fields)))
    return policy


@transaction.atomic
def create_ticket_type(
    *,
    code: str,
    title: str,
    description: str = "",
    default_department: SupportDepartment | None = None,
    default_category: SupportCategory | None = None,
    default_priority: str = TicketPriority.NORMAL,
    default_severity: str = TicketSeverity.MINOR,
    default_sla_policy: SupportSLAPolicy | None = None,
    order: int = 0,
) -> SupportTicketType:
    """Create an admin-managed dynamic ticket type."""
    if default_category is not None and default_department is not None and default_category.department_id != default_department.pk:
        raise SupportDeskServiceError("دسته پیش‌فرض باید متعلق به دپارتمان پیش‌فرض باشد.")
    return SupportTicketType.objects.create(
        code=code.strip(),
        title=title.strip(),
        description=description.strip(),
        default_department=default_department,
        default_category=default_category,
        default_priority=default_priority,
        default_severity=default_severity,
        default_sla_policy=default_sla_policy,
        order=order,
    )


@transaction.atomic
def update_ticket_type(*, ticket_type: SupportTicketType, **fields: Any) -> SupportTicketType:
    """Update a dynamic ticket type through service layer."""
    allowed = {"code", "title", "description", "default_department", "default_category", "default_priority", "default_severity", "default_sla_policy", "order", "is_active"}
    next_department = fields.get("default_department", ticket_type.default_department)
    next_category = fields.get("default_category", ticket_type.default_category)
    if next_category is not None and next_department is not None and next_category.department_id != next_department.pk:
        raise SupportDeskServiceError("دسته پیش‌فرض باید متعلق به دپارتمان پیش‌فرض باشد.")
    update_fields: list[str] = []
    for field, value in fields.items():
        if field not in allowed:
            continue
        if isinstance(value, str) and field in {"code", "title", "description"}:
            value = value.strip()
        if getattr(ticket_type, field) != value:
            setattr(ticket_type, field, value)
            update_fields.append(field)
    if update_fields:
        update_fields.append("updated_at")
        ticket_type.save(update_fields=list(set(update_fields)))
    return ticket_type


@transaction.atomic
def create_canned_response(*, title: str, body: str, department: SupportDepartment | None = None, category: SupportCategory | None = None) -> Any:
    """Create an admin-managed canned response."""
    if category is not None and department is not None and category.department_id != department.pk:
        raise SupportDeskServiceError("دسته پاسخ آماده باید متعلق به همان دپارتمان باشد.")
    from apps.support_desk.models import SupportCannedResponse

    return SupportCannedResponse.objects.create(title=title.strip(), body=body.strip(), department=department, category=category)


@transaction.atomic
def update_canned_response(*, canned_response: Any, **fields: Any) -> Any:
    """Update a canned response through service layer."""
    allowed = {"title", "body", "department", "category", "is_active"}
    next_department = fields.get("department", canned_response.department)
    next_category = fields.get("category", canned_response.category)
    if next_category is not None and next_department is not None and next_category.department_id != next_department.pk:
        raise SupportDeskServiceError("دسته پاسخ آماده باید متعلق به همان دپارتمان باشد.")
    update_fields: list[str] = []
    for field, value in fields.items():
        if field not in allowed:
            continue
        if isinstance(value, str):
            value = value.strip()
        if getattr(canned_response, field) != value:
            setattr(canned_response, field, value)
            update_fields.append(field)
    if update_fields:
        update_fields.append("updated_at")
        canned_response.save(update_fields=list(set(update_fields)))
    return canned_response


@transaction.atomic
def use_canned_response(*, canned_response: Any) -> Any:
    """Increment canned response usage counter."""
    canned_response.usage_count += 1
    canned_response.save(update_fields=["usage_count", "updated_at"])
    return canned_response


@transaction.atomic
def create_ticket(
    *,
    owner: Any,
    ticket_type: SupportTicketType,
    subject: str,
    description: str,
    department: SupportDepartment | None = None,
    category: SupportCategory | None = None,
    priority: str | None = None,
    severity: str | None = None,
) -> SupportTicket:
    """Create a draft ticket with dynamic routing defaults and first user message."""
    if not getattr(owner, "is_authenticated", False):
        raise SupportPermissionError("برای ثبت تیکت باید وارد حساب کاربری شوید.")
    department = department or ticket_type.default_department
    category = category or ticket_type.default_category
    if department is None or category is None:
        raise SupportDeskServiceError("نوع تیکت باید دپارتمان و دسته‌بندی پیش‌فرض یا ورودی معتبر داشته باشد.")
    if category.department_id != department.pk:
        raise SupportDeskServiceError("دسته‌بندی انتخاب‌شده متعلق به دپارتمان تیکت نیست.")
    priority = priority or ticket_type.default_priority or TicketPriority.NORMAL
    severity = severity or ticket_type.default_severity or TicketSeverity.MINOR
    ticket = SupportTicket.objects.create(
        owner=owner,
        department=department,
        category=category,
        ticket_type=ticket_type,
        subject=subject.strip(),
        description_snapshot=description.strip(),
        priority=priority,
        severity=severity,
        assigned_to=department.default_assignee,
        last_activity_at=timezone.now(),
    )
    message = SupportTicketMessage.objects.create(
        ticket=ticket,
        author=owner,
        message_type=TicketMessageType.USER_MESSAGE,
        body=description.strip(),
        is_internal=False,
        is_from_staff=False,
    )
    sync_ticket_counters(ticket=ticket)
    sync_category_counters(category=category)
    SupportTicketStatusHistory.objects.create(ticket=ticket, changed_by=owner, from_status="", to_status=TicketStatus.DRAFT, reason="ساخت پیش‌نویس تیکت")
    if ticket.assigned_to_id:
        SupportTicketAssignment.objects.create(ticket=ticket, assigned_by=owner, from_assignee=None, assigned_to=ticket.assigned_to, department=department, reason="ارجاع خودکار بر اساس دپارتمان")
    _auto_tag_ticket(ticket=ticket, text=f"{ticket.subject} {message.body}")
    detect_duplicate_candidates(ticket=ticket)
    return ticket


@transaction.atomic
def update_draft_ticket(
    *,
    ticket: SupportTicket,
    user: Any,
    ticket_type: SupportTicketType | None = None,
    department: SupportDepartment | None = None,
    category: SupportCategory | None = None,
    subject: str | None = None,
    description: str | None = None,
) -> SupportTicket:
    """Update an owner draft ticket before submission."""
    if ticket.owner_id != user.pk:
        raise SupportPermissionError("فقط مالک تیکت می‌تواند آن را ویرایش کند.")
    if ticket.status != TicketStatus.DRAFT:
        raise SupportTicketStateError("فقط تیکت پیش‌نویس قبل از ارسال قابل ویرایش است.")
    if ticket_type is not None:
        ticket.ticket_type = ticket_type
        ticket.department = department or ticket_type.default_department or ticket.department
        ticket.category = category or ticket_type.default_category or ticket.category
        ticket.priority = ticket_type.default_priority or ticket.priority
        ticket.severity = ticket_type.default_severity or ticket.severity
    if department is not None:
        ticket.department = department
    if category is not None:
        ticket.category = category
    if ticket.category.department_id != ticket.department_id:
        raise SupportDeskServiceError("دسته‌بندی انتخاب‌شده متعلق به دپارتمان تیکت نیست.")
    if subject is not None:
        ticket.subject = subject.strip()
    if description is not None:
        ticket.description_snapshot = description.strip()
    ticket.last_activity_at = timezone.now()
    ticket.save()
    _auto_tag_ticket(ticket=ticket, text=f"{ticket.subject} {ticket.description_snapshot}")
    detect_duplicate_candidates(ticket=ticket)
    sync_category_counters(category=ticket.category)
    return ticket


@transaction.atomic
def submit_ticket(*, ticket: SupportTicket, user: Any, now=None) -> SupportTicket:
    """Submit a draft ticket and calculate SLA deadlines."""
    if ticket.owner_id != user.pk:
        raise SupportPermissionError("فقط مالک تیکت می‌تواند آن را ارسال کند.")
    if ticket.status != TicketStatus.DRAFT:
        raise SupportTicketStateError("فقط تیکت پیش‌نویس قابل ارسال است.")
    now = now or timezone.now()
    _change_status(ticket=ticket, actor=user, to_status=TicketStatus.SUBMITTED, reason="ارسال تیکت برای بررسی", now=now)
    ticket.submitted_at = now
    ticket.last_user_message_at = ticket.last_user_message_at or now
    ticket.last_activity_at = now
    ticket.save(update_fields=["submitted_at", "last_user_message_at", "last_activity_at", "updated_at"])
    policy = resolve_sla_policy(department=ticket.department, ticket_type=ticket.ticket_type, priority=ticket.priority, severity=ticket.severity)
    _apply_sla(ticket=ticket, policy=policy, now=now)
    return ticket


# ---------------------------------------------------------------------------
# Conversation and workflow
# ---------------------------------------------------------------------------


def _change_status(*, ticket: SupportTicket, actor: Any | None, to_status: str, reason: str = "", now=None) -> SupportTicket:
    """Persist a ticket status transition with history and timeline event."""
    now = now or timezone.now()
    from_status = ticket.status
    if from_status == to_status:
        return ticket
    ticket.status = to_status
    update_fields = ["status", "updated_at"]
    if to_status == TicketStatus.RESOLVED:
        ticket.resolved_at = now
        update_fields.append("resolved_at")
    if to_status == TicketStatus.CLOSED:
        ticket.closed_at = now
        update_fields.append("closed_at")
    if to_status == TicketStatus.REOPENED:
        ticket.reopened_at = now
        ticket.reopen_count += 1
        update_fields.extend(["reopened_at", "reopen_count"])
    ticket.last_activity_at = now
    update_fields.append("last_activity_at")
    ticket.save(update_fields=update_fields)
    SupportTicketStatusHistory.objects.create(ticket=ticket, changed_by=actor if getattr(actor, "pk", None) else None, from_status=from_status, to_status=to_status, reason=reason)
    if actor is not None:
        SupportTicketMessage.objects.create(
            ticket=ticket,
            author=actor,
            message_type=TicketMessageType.STATUS_CHANGE,
            body=reason or f"وضعیت تیکت از {from_status} به {to_status} تغییر کرد.",
            is_internal=True,
            is_from_staff=getattr(actor, "is_staff", False) or getattr(actor, "is_superuser", False),
            metadata={"from_status": from_status, "to_status": to_status},
        )
        sync_ticket_counters(ticket=ticket)
    return ticket


def _pause_sla_if_needed(*, ticket: SupportTicket, now=None) -> None:
    """Pause SLA clock when waiting for user if policy allows it."""
    now = now or timezone.now()
    policy = ticket.applied_sla_policy
    if not policy or not policy.pause_when_waiting_for_user or ticket.sla_paused_at:
        return
    ticket.sla_paused_at = now
    ticket.save(update_fields=["sla_paused_at", "updated_at"])
    SupportSLAEvent.objects.create(ticket=ticket, event_type=SLAEventType.PAUSED, occurred_at=now)


def _resume_sla_if_needed(*, ticket: SupportTicket, now=None) -> None:
    """Resume SLA clock and extend deadlines by the paused duration."""
    now = now or timezone.now()
    if ticket.sla_paused_at is None:
        return
    paused_seconds = int((now - ticket.sla_paused_at).total_seconds())
    ticket.sla_total_paused_seconds += max(paused_seconds, 0)
    if ticket.first_response_due_at:
        ticket.first_response_due_at += timezone.timedelta(seconds=max(paused_seconds, 0))
    if ticket.resolution_due_at:
        ticket.resolution_due_at += timezone.timedelta(seconds=max(paused_seconds, 0))
    ticket.sla_paused_at = None
    ticket.save(update_fields=["sla_total_paused_seconds", "first_response_due_at", "resolution_due_at", "sla_paused_at", "updated_at"])
    SupportSLAEvent.objects.create(ticket=ticket, event_type=SLAEventType.RESUMED, occurred_at=now, metadata={"paused_seconds": paused_seconds})


@transaction.atomic
def add_user_reply(*, ticket: SupportTicket, user: Any, body: str, now=None) -> SupportTicketMessage:
    """Add a public user reply and move the ticket to waiting-for-admin."""
    if ticket.owner_id != user.pk:
        raise SupportPermissionError("فقط مالک تیکت می‌تواند روی آن پاسخ ارسال کند.")
    if ticket.status not in _USER_REPLY_ALLOWED_STATUSES:
        raise SupportTicketStateError("در وضعیت فعلی امکان ارسال پاسخ کاربر وجود ندارد.")
    now = now or timezone.now()
    _resume_sla_if_needed(ticket=ticket, now=now)
    message = SupportTicketMessage.objects.create(ticket=ticket, author=user, message_type=TicketMessageType.USER_MESSAGE, body=body.strip(), is_internal=False, is_from_staff=False)
    ticket.last_user_message_at = now
    ticket.last_activity_at = now
    ticket.save(update_fields=["last_user_message_at", "last_activity_at", "updated_at"])
    _change_status(ticket=ticket, actor=user, to_status=TicketStatus.WAITING_FOR_ADMIN, reason="پاسخ جدید کاربر", now=now)
    sync_ticket_counters(ticket=ticket)
    _auto_tag_ticket(ticket=ticket, text=body)
    return message


@transaction.atomic
def add_admin_reply(*, ticket: SupportTicket, admin: Any, body: str, now=None) -> SupportTicketMessage:
    """Add a public admin reply and move the ticket to waiting-for-user."""
    if not _is_admin(admin):
        raise SupportPermissionError("برای پاسخ ادمین باید دسترسی پشتیبانی داشته باشید.")
    if ticket.status not in _ADMIN_REPLY_ALLOWED_STATUSES:
        raise SupportTicketStateError("در وضعیت فعلی امکان پاسخ ادمین وجود ندارد.")
    now = now or timezone.now()
    message = SupportTicketMessage.objects.create(ticket=ticket, author=admin, message_type=TicketMessageType.ADMIN_REPLY, body=body.strip(), is_internal=False, is_from_staff=True)
    if ticket.first_admin_response_at is None:
        ticket.first_admin_response_at = now
    ticket.last_admin_message_at = now
    ticket.last_activity_at = now
    ticket.save(update_fields=["first_admin_response_at", "last_admin_message_at", "last_activity_at", "updated_at"])
    _change_status(ticket=ticket, actor=admin, to_status=TicketStatus.WAITING_FOR_USER, reason="پاسخ ادمین ارسال شد", now=now)
    _pause_sla_if_needed(ticket=ticket, now=now)
    sync_ticket_counters(ticket=ticket)
    return message


@transaction.atomic
def add_internal_note(*, ticket: SupportTicket, admin: Any, body: str) -> SupportTicketMessage:
    """Add an admin-only internal note to the ticket timeline."""
    if not _is_admin(admin):
        raise SupportPermissionError("فقط ادمین می‌تواند یادداشت داخلی ثبت کند.")
    message = SupportTicketMessage.objects.create(ticket=ticket, author=admin, message_type=TicketMessageType.INTERNAL_NOTE, body=body.strip(), is_internal=True, is_from_staff=True)
    sync_ticket_counters(ticket=ticket)
    return message


@transaction.atomic
def add_attachment(
    *,
    ticket: SupportTicket,
    user: Any,
    file_obj,
    original_filename: str,
    content_type: str = "",
    attachment_kind: str = "other",
    visibility: str = "public",
    message: SupportTicketMessage | None = None,
) -> SupportTicketAttachment:
    """Attach a validated file to a ticket through the service layer."""
    if ticket.owner_id != user.pk and not _is_admin(user):
        raise SupportPermissionError("فقط مالک تیکت یا ادمین می‌تواند ضمیمه ثبت کند.")
    if visibility == "internal_only" and not _is_admin(user):
        raise SupportPermissionError("ضمیمه داخلی فقط توسط ادمین قابل ثبت است.")
    if ticket.status in _TERMINAL_STATUSES and not _is_admin(user):
        raise SupportTicketStateError("در وضعیت فعلی امکان افزودن ضمیمه توسط کاربر وجود ندارد.")
    attachment = SupportTicketAttachment.objects.create(
        ticket=ticket,
        message=message,
        uploaded_by=user,
        file=file_obj,
        original_filename=original_filename[:260],
        content_type=content_type[:120],
        file_size=getattr(file_obj, "size", 0) or 0,
        attachment_kind=attachment_kind,
        visibility=visibility,
    )
    sync_ticket_counters(ticket=ticket)
    return attachment


@transaction.atomic
def assign_ticket(*, ticket: SupportTicket, admin: Any, assignee: Any | None, department: SupportDepartment | None = None, reason: str = "") -> SupportTicket:
    """Assign or reassign a ticket to an admin user/department."""
    if not _is_admin(admin):
        raise SupportPermissionError("فقط ادمین می‌تواند تیکت را ارجاع دهد.")
    previous = ticket.assigned_to
    if department is not None:
        ticket.department = department
    ticket.assigned_to = assignee
    ticket.last_activity_at = timezone.now()
    ticket.save(update_fields=["department", "assigned_to", "last_activity_at", "updated_at"])
    SupportTicketAssignment.objects.create(ticket=ticket, assigned_by=admin, from_assignee=previous, assigned_to=assignee, department=ticket.department, reason=reason)
    SupportTicketMessage.objects.create(
        ticket=ticket,
        author=admin,
        message_type=TicketMessageType.ASSIGNMENT_CHANGE,
        body=reason or "مسئول تیکت تغییر کرد.",
        is_internal=True,
        is_from_staff=True,
        metadata={"from_assignee_id": previous.pk if previous else None, "assigned_to_id": assignee.pk if assignee else None, "department_id": ticket.department_id},
    )
    sync_ticket_counters(ticket=ticket)
    return ticket


@transaction.atomic
def change_ticket_status(*, ticket: SupportTicket, admin: Any, status: str, reason: str = "") -> SupportTicket:
    """Change ticket status by admin with state and audit history."""
    if not _is_admin(admin):
        raise SupportPermissionError("فقط ادمین می‌تواند وضعیت تیکت را تغییر دهد.")
    if status not in TicketStatus.values:
        raise SupportTicketStateError("وضعیت تیکت نامعتبر است.")
    return _change_status(ticket=ticket, actor=admin, to_status=status, reason=reason)


@transaction.atomic
def resolve_ticket(*, ticket: SupportTicket, admin: Any, reason: str = "") -> SupportTicket:
    """Mark a ticket as resolved by admin."""
    if ticket.status in _TERMINAL_STATUSES:
        raise SupportTicketStateError("تیکت بسته/آرشیو/اسپم قابل حل مجدد نیست.")
    return change_ticket_status(ticket=ticket, admin=admin, status=TicketStatus.RESOLVED, reason=reason or "تیکت حل شد.")


@transaction.atomic
def close_ticket(*, ticket: SupportTicket, actor: Any, reason: str = "") -> SupportTicket:
    """Close a ticket by owner or admin after resolution/operational decision."""
    if ticket.owner_id != actor.pk and not _is_admin(actor):
        raise SupportPermissionError("فقط مالک یا ادمین می‌تواند تیکت را ببندد.")
    if ticket.status not in {TicketStatus.RESOLVED, TicketStatus.WAITING_FOR_USER, TicketStatus.OPEN, TicketStatus.IN_PROGRESS, TicketStatus.REOPENED, TicketStatus.ESCALATED}:
        raise SupportTicketStateError("این تیکت در وضعیت فعلی قابل بستن نیست.")
    return _change_status(ticket=ticket, actor=actor, to_status=TicketStatus.CLOSED, reason=reason or "تیکت بسته شد.")


@transaction.atomic
def reopen_ticket(*, ticket: SupportTicket, user: Any, reason: str = "") -> SupportTicket:
    """Reopen a resolved/closed ticket within the allowed reopen window."""
    if ticket.owner_id != user.pk:
        raise SupportPermissionError("فقط مالک تیکت می‌تواند آن را بازگشایی کند.")
    if not ticket.is_reopenable:
        raise SupportTicketStateError("مهلت بازگشایی این تیکت به پایان رسیده یا وضعیت آن قابل بازگشایی نیست.")
    _resume_sla_if_needed(ticket=ticket)
    return _change_status(ticket=ticket, actor=user, to_status=TicketStatus.REOPENED, reason=reason or "تیکت توسط کاربر بازگشایی شد.")


@transaction.atomic
def escalate_ticket(*, ticket: SupportTicket, admin: Any, reason: str) -> SupportTicket:
    """Escalate a ticket manually by admin."""
    if not _is_admin(admin):
        raise SupportPermissionError("فقط ادمین می‌تواند تیکت را ارجاع فوری کند.")
    ticket.escalated_at = timezone.now()
    ticket.escalated_by = admin
    ticket.escalation_reason = reason
    ticket.save(update_fields=["escalated_at", "escalated_by", "escalation_reason", "updated_at"])
    SupportSLAEvent.objects.create(ticket=ticket, event_type=SLAEventType.ESCALATED, metadata={"reason": reason})
    return _change_status(ticket=ticket, actor=admin, to_status=TicketStatus.ESCALATED, reason=reason)


# ---------------------------------------------------------------------------
# Satisfaction, counters, triage and duplicates
# ---------------------------------------------------------------------------


@transaction.atomic
def submit_satisfaction(*, ticket: SupportTicket, user: Any, rating: int, comment: str = "") -> SupportTicketSatisfaction:
    """Submit a one-time CSAT rating for a resolved/closed ticket."""
    if ticket.owner_id != user.pk:
        raise SupportPermissionError("فقط مالک تیکت می‌تواند رضایت‌سنجی ثبت کند.")
    if ticket.status not in {TicketStatus.RESOLVED, TicketStatus.CLOSED}:
        raise SupportTicketStateError("رضایت‌سنجی فقط پس از حل یا بستن تیکت قابل ثبت است.")
    if rating < 1 or rating > 5:
        raise SupportDeskServiceError("امتیاز رضایت باید بین ۱ تا ۵ باشد.")
    satisfaction = SupportTicketSatisfaction.objects.create(ticket=ticket, user=user, rating=rating, comment=comment.strip())
    ticket.satisfaction_rating_snapshot = rating
    ticket.save(update_fields=["satisfaction_rating_snapshot", "updated_at"])
    return satisfaction


def sync_ticket_counters(*, ticket: SupportTicket) -> SupportTicket:
    """Recalculate message/attachment/internal-note counters."""
    ticket.message_count = ticket.messages.count()
    ticket.attachment_count = ticket.attachments.count()
    ticket.internal_note_count = ticket.messages.filter(is_internal=True, message_type=TicketMessageType.INTERNAL_NOTE).count()
    ticket.save(update_fields=["message_count", "attachment_count", "internal_note_count", "updated_at"])
    return ticket


def sync_category_counters(*, category: SupportCategory) -> SupportCategory:
    """Recalculate category ticket counters."""
    category.tickets_count = SupportTicket.all_objects.filter(category=category).count()
    category.open_tickets_count = SupportTicket.objects.open_queue().filter(category=category).count()
    category.save(update_fields=["tickets_count", "open_tickets_count", "updated_at"])
    return category


def _tokenize(value: str) -> set[str]:
    """Tokenize Persian/English text for lightweight triage and duplicates."""
    from apps.support_desk.models import _normalize_text

    stopwords = {"از", "به", "در", "و", "یا", "برای", "با", "که", "این", "آن", "من", "ما", "مشکل", "سوال", "تیکت"}
    return {token for token in _normalize_text(value).split() if token and token not in stopwords}


def _similarity_score(left: str, right: str, *, max_points: int = 100) -> int:
    """Return token overlap score scaled to max_points."""
    left_tokens = _tokenize(left)
    right_tokens = _tokenize(right)
    if not left_tokens or not right_tokens:
        return 0
    return round((len(left_tokens & right_tokens) / len(left_tokens | right_tokens)) * max_points)


def _auto_tag_ticket(*, ticket: SupportTicket, text: str) -> None:
    """Create simple normalized auto-triage tags from ticket text."""
    for token in sorted(_tokenize(text))[:12]:
        tag, _created = SupportTag.objects.get_or_create(name=token, defaults={"normalized_name": token})
        SupportTicketTag.objects.get_or_create(ticket=ticket, tag=tag, defaults={"source": "auto_triage"})
        tag.usage_count = tag.ticket_tags.count()
        tag.save(update_fields=["usage_count", "updated_at"])


def detect_duplicate_candidates(*, ticket: SupportTicket, threshold: int = 68) -> list[SupportDuplicateCandidate]:
    """Detect likely duplicate tickets for the same user/category/type."""
    candidates = (
        SupportTicket.all_objects.filter(owner=ticket.owner, category=ticket.category, ticket_type=ticket.ticket_type)
        .exclude(pk=ticket.pk)
        .exclude(status__in={TicketStatus.ARCHIVED, TicketStatus.SPAM})
        .order_by("-created_at")[:50]
    )
    duplicates: list[SupportDuplicateCandidate] = []
    source_text = f"{ticket.subject} {ticket.description_snapshot}"
    for candidate in candidates:
        score = _similarity_score(source_text, f"{candidate.subject} {candidate.description_snapshot}")
        if score < threshold:
            continue
        duplicate, _created = SupportDuplicateCandidate.objects.update_or_create(
            ticket=ticket,
            candidate_ticket=candidate,
            defaults={"score": score, "reason": "شباهت بالای عنوان/توضیحات و یکسان بودن مالک، دسته و نوع تیکت"},
        )
        duplicates.append(duplicate)
    return duplicates


def suggest_ticket_triage(*, owner: Any, subject: str, description: str, category: SupportCategory | None = None, ticket_type: SupportTicketType | None = None) -> SupportTriageSuggestion:
    """Suggest department/category/type/priority/SLA and similar tickets before creation."""
    text = f"{subject} {description}"
    reason_codes: list[str] = []
    if ticket_type is None:
        ticket_type = _suggest_ticket_type(text=text)
        if ticket_type:
            reason_codes.append("ticket_type_keyword_match")
    if category is None:
        category = _suggest_category(text=text, ticket_type=ticket_type)
        if category:
            reason_codes.append("category_keyword_match")
    department = category.department if category else (ticket_type.default_department if ticket_type else None)
    priority = ticket_type.default_priority if ticket_type else TicketPriority.NORMAL
    severity = ticket_type.default_severity if ticket_type else TicketSeverity.MINOR
    if "پرداخت" in text or "مالی" in text:
        priority = TicketPriority.HIGH
        severity = TicketSeverity.MAJOR
        reason_codes.append("payment_keyword_priority_boost")
    if "امنیت" in text or "هک" in text or "آسیب" in text:
        priority = TicketPriority.URGENT
        severity = TicketSeverity.CRITICAL
        reason_codes.append("security_keyword_priority_boost")
    policy = resolve_sla_policy(department=department, ticket_type=ticket_type, priority=priority, severity=severity)
    similar_tickets = _find_similar_tickets(owner=owner, text=text, category=category, ticket_type=ticket_type)
    score = min(100, 20 * len(reason_codes) + (30 if similar_tickets else 0))
    return SupportTriageSuggestion(
        department=department,
        category=category,
        ticket_type=ticket_type,
        priority=priority,
        severity=severity,
        sla_policy=policy,
        duplicate_warning=bool(similar_tickets),
        similar_ticket_ids=[ticket.pk for ticket in similar_tickets],
        reason_codes=reason_codes,
        score=score,
    )


def _suggest_ticket_type(*, text: str) -> SupportTicketType | None:
    """Suggest a ticket type from seeded/admin-managed types using keyword matching."""
    normalized = " ".join(_tokenize(text))
    keyword_map = {
        "payment": {"پرداخت", "رسید", "مبلغ", "تراکنش", "مالی"},
        "technical_issue": {"خطا", "کندی", "آپلود", "نمایش", "فنی", "api"},
        "account": {"ورود", "رمز", "otp", "موبایل", "پروفایل", "احراز"},
        "security": {"امنیت", "هک", "آسیب", "حریم", "جعل"},
        "suggestion": {"پیشنهاد", "ایده", "بهبود"},
    }
    for code, keywords in keyword_map.items():
        if keywords & set(normalized.split()):
            ticket_type = SupportTicketType.objects.filter(code=code).first()
            if ticket_type is not None:
                return ticket_type
    return SupportTicketType.objects.filter(code="question").first()


def _suggest_category(*, text: str, ticket_type: SupportTicketType | None) -> SupportCategory | None:
    """Suggest the most text-similar active category."""
    best_category = ticket_type.default_category if ticket_type and ticket_type.default_category_id else None
    best_score = 0
    for category in SupportCategory.objects.select_related("department"):
        score = _similarity_score(text, f"{category.title} {category.description}", max_points=100)
        if score > best_score:
            best_score = score
            best_category = category
    return best_category


def _find_similar_tickets(*, owner: Any, text: str, category: SupportCategory | None, ticket_type: SupportTicketType | None, threshold: int = 60) -> list[SupportTicket]:
    """Find similar recent tickets for duplicate warning."""
    queryset = SupportTicket.all_objects.filter(owner=owner).exclude(status__in={TicketStatus.ARCHIVED, TicketStatus.SPAM}).order_by("-created_at")[:50]
    matches: list[SupportTicket] = []
    for ticket in queryset:
        bonus = 10 if category and ticket.category_id == category.pk else 0
        bonus += 10 if ticket_type and ticket.ticket_type_id == ticket_type.pk else 0
        score = _similarity_score(text, f"{ticket.subject} {ticket.description_snapshot}") + bonus
        if score >= threshold:
            matches.append(ticket)
    return matches[:5]


@transaction.atomic
def review_duplicate_candidate(*, duplicate: SupportDuplicateCandidate, admin: Any, status: str, reason: str = "") -> SupportDuplicateCandidate:
    """Review a duplicate candidate generated by smart triage."""
    if not _is_admin(admin):
        raise SupportPermissionError("فقط ادمین می‌تواند کاندیدای تکراری بودن را بررسی کند.")
    if status not in DuplicateReviewStatus.values:
        raise SupportTicketStateError("وضعیت بررسی تکراری بودن نامعتبر است.")
    duplicate.status = status
    duplicate.reason = reason or duplicate.reason
    duplicate.reviewed_by = admin
    duplicate.reviewed_at = timezone.now()
    duplicate.save(update_fields=["status", "reason", "reviewed_by", "reviewed_at", "updated_at"])
    return duplicate


@transaction.atomic
def mark_sla_breaches(*, now=None) -> int:
    """Mark SLA-breached tickets and optionally escalate them."""
    now = now or timezone.now()
    queryset = SupportTicket.objects.open_queue().filter(sla_breached_at__isnull=True).filter(
        models_Q_first_response_due(now) | models_Q_resolution_due(now)
    )
    updated = 0
    for ticket in queryset.select_related("applied_sla_policy"):
        ticket.sla_breached_at = now
        ticket.save(update_fields=["sla_breached_at", "updated_at"])
        event_type = SLAEventType.FIRST_RESPONSE_BREACHED if ticket.first_admin_response_at is None and ticket.first_response_due_at and ticket.first_response_due_at <= now else SLAEventType.RESOLUTION_BREACHED
        SupportSLAEvent.objects.create(ticket=ticket, event_type=event_type, occurred_at=now)
        if ticket.applied_sla_policy and ticket.applied_sla_policy.escalate_on_breach and ticket.status != TicketStatus.ESCALATED:
            ticket.status = TicketStatus.ESCALATED
            ticket.escalated_at = now
            ticket.escalation_reason = "نقض SLA"
            ticket.save(update_fields=["status", "escalated_at", "escalation_reason", "updated_at"])
            SupportSLAEvent.objects.create(ticket=ticket, event_type=SLAEventType.ESCALATED, occurred_at=now, metadata={"reason": "sla_breach"})
        updated += 1
    return updated


def models_Q_first_response_due(now):
    """Return Q object for breached first response deadline."""
    from django.db.models import Q

    return Q(first_admin_response_at__isnull=True, first_response_due_at__isnull=False, first_response_due_at__lte=now)


def models_Q_resolution_due(now):
    """Return Q object for breached resolution deadline."""
    from django.db.models import Q

    return Q(resolution_due_at__isnull=False, resolution_due_at__lte=now)


def get_admin_analytics_summary() -> dict[str, Any]:
    """Return service-level aggregate counters for support dashboard."""
    tickets = SupportTicket.all_objects.all()
    return {
        "total_tickets": tickets.count(),
        "open_tickets": tickets.exclude(status__in=[TicketStatus.CLOSED, TicketStatus.ARCHIVED, TicketStatus.SPAM]).count(),
        "unassigned_tickets": tickets.filter(assigned_to__isnull=True).count(),
        "sla_breached_tickets": tickets.filter(sla_breached_at__isnull=False).count(),
        "status_distribution": list(tickets.values("status").annotate(count=Count("id")).order_by("-count")),
        "department_distribution": list(tickets.values("department_id", "department__title").annotate(count=Count("id")).order_by("-count")),
        "priority_distribution": list(tickets.values("priority").annotate(count=Count("id")).order_by("-count")),
    }


def _is_admin(user: Any) -> bool:
    """Return whether a user can perform support admin actions."""
    return bool(user and getattr(user, "is_authenticated", False) and (getattr(user, "is_staff", False) or getattr(user, "is_superuser", False) or getattr(user, "role", "") == "admin"))

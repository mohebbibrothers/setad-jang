"""Read-side selectors for Support Desk."""

from django.db.models import Prefetch, QuerySet

from apps.support_desk.models import (
    SupportCategory,
    SupportDepartment,
    SupportTicket,
    SupportTicketAttachment,
    SupportTicketMessage,
    SupportTicketType,
)


def get_active_departments() -> QuerySet[SupportDepartment]:
    """Return active departments ordered for user/admin navigation."""
    return SupportDepartment.objects.order_by("order", "title")


def get_active_category_tree() -> QuerySet[SupportCategory]:
    """Return active category tree with department loaded."""
    return SupportCategory.objects.select_related("department", "parent").order_by("depth", "order", "title")


def get_active_ticket_types() -> QuerySet[SupportTicketType]:
    """Return active dynamic ticket types for user ticket creation."""
    return (
        SupportTicketType.objects.select_related("default_department", "default_category", "default_sla_policy")
        .order_by("order", "title")
    )


def _message_queryset(*, include_internal: bool = False) -> QuerySet[SupportTicketMessage]:
    """Return optimized ticket message queryset."""
    queryset = SupportTicketMessage.objects.select_related("author").order_by("created_at", "id")
    if not include_internal:
        queryset = queryset.filter(is_internal=False)
    return queryset


def _attachment_queryset(*, include_internal: bool = False) -> QuerySet[SupportTicketAttachment]:
    """Return optimized attachment queryset."""
    queryset = SupportTicketAttachment.objects.select_related("uploaded_by").order_by("created_at", "id")
    if not include_internal:
        queryset = queryset.exclude(visibility="internal_only")
    return queryset


def get_user_tickets(*, user_id: int) -> QuerySet[SupportTicket]:
    """Return tickets owned by a user with safe public timeline data."""
    return (
        SupportTicket.objects.filter(owner_id=user_id)
        .select_related("department", "category", "ticket_type", "assigned_to", "applied_sla_policy")
        .prefetch_related(
            Prefetch("messages", queryset=_message_queryset(include_internal=False)),
            Prefetch("attachments", queryset=_attachment_queryset(include_internal=False)),
        )
        .order_by("-last_activity_at", "-created_at")
    )


def get_user_ticket_by_number(*, user_id: int, ticket_number: str) -> SupportTicket | None:
    """Return one user-owned ticket by public ticket number with IDOR protection."""
    return get_user_tickets(user_id=user_id).filter(ticket_number=ticket_number).first()


def get_user_ticket_timeline(*, ticket: SupportTicket) -> QuerySet[SupportTicketMessage]:
    """Return public timeline messages for a user-owned ticket."""
    return _message_queryset(include_internal=False).filter(ticket=ticket)


def get_admin_tickets() -> QuerySet[SupportTicket]:
    """Return admin ticket queue optimized for listing/detail serializers."""
    return (
        SupportTicket.all_objects.select_related("owner", "department", "category", "ticket_type", "assigned_to")
        .prefetch_related(Prefetch("messages", queryset=_message_queryset(include_internal=True)))
        .order_by("-last_activity_at", "-created_at")
    )

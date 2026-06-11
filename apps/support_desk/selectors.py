"""Read-side selectors for Support Desk."""

from django.db.models import Prefetch, QuerySet

from apps.support_desk.models import (
    SupportCannedResponse,
    SupportCategory,
    SupportDepartment,
    SupportDuplicateCandidate,
    SupportSLAPolicy,
    SupportTicket,
    SupportTicketAttachment,
    SupportTicketMessage,
    SupportTicketSatisfaction,
    SupportTicketType,
)


def get_active_departments() -> QuerySet[SupportDepartment]:
    """Return active departments ordered for user/admin navigation."""
    return SupportDepartment.objects.order_by("order", "title")


def get_admin_departments() -> QuerySet[SupportDepartment]:
    """Return all departments for admin taxonomy management."""
    return SupportDepartment.all_objects.select_related("default_assignee").order_by("order", "title")


def get_admin_department_by_id(*, department_id: int) -> SupportDepartment | None:
    """Return one department in admin scope."""
    return get_admin_departments().filter(pk=department_id).first()


def get_active_category_tree() -> QuerySet[SupportCategory]:
    """Return active category tree with department loaded."""
    return SupportCategory.objects.select_related("department", "parent").order_by("depth", "order", "title")


def get_admin_category_tree() -> QuerySet[SupportCategory]:
    """Return all categories for admin tree management."""
    return SupportCategory.all_objects.select_related("department", "parent").order_by("depth", "order", "title")


def get_admin_category_by_id(*, category_id: int) -> SupportCategory | None:
    """Return one category in admin scope."""
    return get_admin_category_tree().filter(pk=category_id).first()


def get_active_ticket_types() -> QuerySet[SupportTicketType]:
    """Return active dynamic ticket types for user ticket creation."""
    return (
        SupportTicketType.objects.select_related("default_department", "default_category", "default_sla_policy")
        .order_by("order", "title")
    )


def get_admin_ticket_types() -> QuerySet[SupportTicketType]:
    """Return all ticket types for admin management."""
    return (
        SupportTicketType.all_objects.select_related("default_department", "default_category", "default_sla_policy")
        .order_by("order", "title")
    )


def get_admin_ticket_type_by_id(*, ticket_type_id: int) -> SupportTicketType | None:
    """Return one ticket type in admin scope."""
    return get_admin_ticket_types().filter(pk=ticket_type_id).first()


def get_admin_sla_policies() -> QuerySet[SupportSLAPolicy]:
    """Return all SLA policies for admin management."""
    return SupportSLAPolicy.all_objects.select_related("department").order_by("order", "title")


def get_admin_sla_policy_by_id(*, policy_id: int) -> SupportSLAPolicy | None:
    """Return one SLA policy in admin scope."""
    return get_admin_sla_policies().filter(pk=policy_id).first()


def get_admin_canned_responses() -> QuerySet[SupportCannedResponse]:
    """Return all canned responses for admin management."""
    return SupportCannedResponse.all_objects.select_related("department", "category").order_by("title")


def get_admin_canned_response_by_id(*, canned_response_id: int) -> SupportCannedResponse | None:
    """Return one canned response in admin scope."""
    return get_admin_canned_responses().filter(pk=canned_response_id).first()


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
        SupportTicket.all_objects.select_related("owner", "department", "category", "ticket_type", "assigned_to", "applied_sla_policy")
        .prefetch_related(
            Prefetch("messages", queryset=_message_queryset(include_internal=True)),
            Prefetch("attachments", queryset=_attachment_queryset(include_internal=True)),
        )
        .order_by("-last_activity_at", "-created_at")
    )


def get_admin_ticket_by_number(*, ticket_number: str) -> SupportTicket | None:
    """Return one ticket in admin scope."""
    return get_admin_tickets().filter(ticket_number=ticket_number).first()


def get_admin_messages() -> QuerySet[SupportTicketMessage]:
    """Return all support timeline messages for admin export."""
    return SupportTicketMessage.objects.select_related("ticket", "author").order_by("-created_at")


def get_admin_satisfaction_ratings() -> QuerySet[SupportTicketSatisfaction]:
    """Return CSAT ratings for admin export."""
    return SupportTicketSatisfaction.objects.select_related("ticket", "user").order_by("-created_at")


def get_admin_sla_tickets() -> QuerySet[SupportTicket]:
    """Return tickets with SLA metadata for SLA reporting/export."""
    return get_admin_tickets().filter(applied_sla_policy__isnull=False)


def get_admin_duplicate_candidates() -> QuerySet[SupportDuplicateCandidate]:
    """Return duplicate candidates for admin review."""
    return (
        SupportDuplicateCandidate.objects.select_related("ticket", "candidate_ticket", "reviewed_by")
        .order_by("-score", "-created_at")
    )


def get_admin_duplicate_candidate_by_id(*, duplicate_id: int) -> SupportDuplicateCandidate | None:
    """Return one duplicate candidate in admin scope."""
    return get_admin_duplicate_candidates().filter(pk=duplicate_id).first()

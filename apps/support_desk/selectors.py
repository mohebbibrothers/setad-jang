"""Read-side selectors for Support Desk."""

from django.db.models import Prefetch, QuerySet

from apps.support_desk.models import (
    SupportCategory,
    SupportDepartment,
    SupportTicket,
    SupportTicketMessage,
)


def get_active_departments() -> QuerySet[SupportDepartment]:
    """Return active departments ordered for user/admin navigation."""
    return SupportDepartment.objects.order_by("order", "title")


def get_active_category_tree() -> QuerySet[SupportCategory]:
    """Return active category tree with department loaded."""
    return SupportCategory.objects.select_related("department", "parent").order_by("depth", "order", "title")


def get_admin_tickets() -> QuerySet[SupportTicket]:
    """Return admin ticket queue optimized for listing/detail serializers."""
    return (
        SupportTicket.all_objects.select_related("owner", "department", "category", "ticket_type", "assigned_to")
        .prefetch_related(Prefetch("messages", queryset=SupportTicketMessage.objects.order_by("created_at", "id")))
        .order_by("-last_activity_at", "-created_at")
    )

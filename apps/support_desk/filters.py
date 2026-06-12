"""django-filter filtersets for Support Desk."""

import django_filters

from apps.core.search import SearchField, apply_smart_search
from apps.support_desk.choices import TicketPriority, TicketSeverity, TicketStatus
from apps.support_desk.models import SupportDuplicateCandidate, SupportTicket


class SupportUserTicketFilter(django_filters.FilterSet):
    """User ticket dashboard filters."""

    status = django_filters.ChoiceFilter(choices=TicketStatus.choices)
    priority = django_filters.ChoiceFilter(choices=TicketPriority.choices)
    severity = django_filters.ChoiceFilter(choices=TicketSeverity.choices)
    department = django_filters.CharFilter(field_name="department__slug")
    category = django_filters.CharFilter(field_name="category__slug")
    ticket_type = django_filters.CharFilter(field_name="ticket_type__code")
    search = django_filters.CharFilter(method="filter_search")

    class Meta:
        model = SupportTicket
        fields: list[str] = []

    def filter_search(self, queryset, name, value):
        """Search tickets with PostgreSQL FTS/trigram and SQLite fallback."""
        return apply_smart_search(
            queryset,
            search_term=value,
            fields=[
                SearchField("ticket_number", "A"),
                SearchField("subject", "A"),
                SearchField("description_snapshot", "B"),
                SearchField("search_document", "C"),
            ],
            trigram_fields=["ticket_number", "subject"],
        )


class SupportAdminTicketFilter(SupportUserTicketFilter):
    """Admin ticket queue filters."""

    owner_id = django_filters.NumberFilter(field_name="owner_id")
    assigned_to_id = django_filters.NumberFilter(field_name="assigned_to_id")
    unassigned = django_filters.BooleanFilter(method="filter_unassigned")
    sla_breached = django_filters.BooleanFilter(method="filter_sla_breached")

    def filter_unassigned(self, queryset, name, value):
        """Filter unassigned/admin-assigned tickets."""
        return queryset.filter(assigned_to__isnull=value)

    def filter_sla_breached(self, queryset, name, value):
        """Filter tickets by SLA breach marker."""
        return queryset.filter(sla_breached_at__isnull=not value)


class SupportDuplicateCandidateAdminFilter(django_filters.FilterSet):
    """Admin duplicate candidate filters."""

    status = django_filters.CharFilter(field_name="status")
    ticket_id = django_filters.NumberFilter(field_name="ticket_id")
    min_score = django_filters.NumberFilter(field_name="score", lookup_expr="gte")

    class Meta:
        model = SupportDuplicateCandidate
        fields: list[str] = []

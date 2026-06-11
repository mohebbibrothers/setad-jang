"""django-filter filtersets for Support Desk."""

import django_filters
from django.db.models import Q

from apps.support_desk.choices import TicketPriority, TicketSeverity, TicketStatus
from apps.support_desk.models import SupportTicket


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
        """Search user tickets by number, subject and search document."""
        return queryset.filter(
            Q(ticket_number__icontains=value)
            | Q(subject__icontains=value)
            | Q(description_snapshot__icontains=value)
            | Q(search_document__icontains=value)
        )

"""Filters for user activity timeline."""

import django_filters

from apps.activity.models import UserActivity


class UserActivityFilter(django_filters.FilterSet):
    """User/admin activity filters."""

    app_label = django_filters.CharFilter(field_name="app_label")
    event_type = django_filters.CharFilter(field_name="event_type")
    aggregate_type = django_filters.CharFilter(field_name="aggregate_type")

    class Meta:
        model = UserActivity
        fields: list[str] = []

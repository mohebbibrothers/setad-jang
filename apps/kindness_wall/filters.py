"""django-filter filtersets for Kindness Wall."""

import django_filters
from django.db.models import Q

from apps.core.search import SearchField, apply_smart_search
from apps.kindness_wall.choices import DuplicateStatus, ListingType, MatchStatus, ReportStatus
from apps.kindness_wall.models import (
    KindnessContactReveal,
    KindnessDuplicateCandidate,
    KindnessListing,
    KindnessListingReport,
    KindnessMatch,
)


class KindnessListingPublicFilter(django_filters.FilterSet):
    """Public listing filters."""

    listing_type = django_filters.ChoiceFilter(choices=ListingType.choices)
    category = django_filters.CharFilter(field_name="category__slug", lookup_expr="exact")
    province = django_filters.CharFilter(field_name="province", lookup_expr="iexact")
    city = django_filters.CharFilter(field_name="city", lookup_expr="iexact")
    search = django_filters.CharFilter(method="filter_search")

    class Meta:
        model = KindnessListing
        fields: list[str] = []

    def filter_search(self, queryset, name, value):
        """Search listings with PostgreSQL FTS/trigram and SQLite fallback."""
        return apply_smart_search(
            queryset,
            search_term=value,
            fields=[
                SearchField("title", "A"),
                SearchField("description", "B"),
                SearchField("search_document", "C"),
            ],
            trigram_fields=["title", "description"],
        )


class KindnessListingAdminFilter(KindnessListingPublicFilter):
    """Admin listing filters including workflow status."""

    status = django_filters.CharFilter(field_name="status", lookup_expr="exact")
    owner_id = django_filters.NumberFilter(field_name="owner_id")


class KindnessReportAdminFilter(django_filters.FilterSet):
    """Admin filters for listing reports."""

    status = django_filters.ChoiceFilter(choices=ReportStatus.choices)
    reason = django_filters.CharFilter(field_name="reason", lookup_expr="exact")
    listing_id = django_filters.NumberFilter(field_name="listing_id")
    reported_by_id = django_filters.NumberFilter(field_name="reported_by_id")

    class Meta:
        model = KindnessListingReport
        fields: list[str] = []


class KindnessMatchAdminFilter(django_filters.FilterSet):
    """Admin filters for materialized matches."""

    status = django_filters.ChoiceFilter(choices=MatchStatus.choices)
    source_listing_id = django_filters.NumberFilter(field_name="source_listing_id")
    target_listing_id = django_filters.NumberFilter(field_name="target_listing_id")
    category = django_filters.CharFilter(method="filter_category")
    min_score = django_filters.NumberFilter(field_name="score", lookup_expr="gte")
    max_score = django_filters.NumberFilter(field_name="score", lookup_expr="lte")

    class Meta:
        model = KindnessMatch
        fields: list[str] = []

    def filter_category(self, queryset, name, value):
        """Filter matches where either side belongs to a category slug."""
        return queryset.filter(
            Q(source_listing__category__slug=value) | Q(target_listing__category__slug=value)
        )


class KindnessContactRevealAdminFilter(django_filters.FilterSet):
    """Admin filters for contact reveal audit rows."""

    listing_id = django_filters.NumberFilter(field_name="listing_id")
    viewer_id = django_filters.NumberFilter(field_name="viewer_id")
    owner_id = django_filters.NumberFilter(field_name="listing_owner_id")
    created_after = django_filters.IsoDateTimeFilter(field_name="created_at", lookup_expr="gte")
    created_before = django_filters.IsoDateTimeFilter(field_name="created_at", lookup_expr="lte")

    class Meta:
        model = KindnessContactReveal
        fields: list[str] = []


class KindnessDuplicateCandidateAdminFilter(django_filters.FilterSet):
    """Admin filters for likely duplicate candidates."""

    status = django_filters.ChoiceFilter(choices=DuplicateStatus.choices)
    listing_id = django_filters.NumberFilter(field_name="listing_id")
    candidate_listing_id = django_filters.NumberFilter(field_name="candidate_listing_id")
    min_score = django_filters.NumberFilter(field_name="score", lookup_expr="gte")

    class Meta:
        model = KindnessDuplicateCandidate
        fields: list[str] = []

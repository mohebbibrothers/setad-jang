"""django-filter filtersets for Kindness Wall."""

import django_filters
from django.db.models import Q

from apps.kindness_wall.choices import ListingType
from apps.kindness_wall.models import KindnessListing


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
        """Search title/description/search document."""
        return queryset.filter(Q(title__icontains=value) | Q(description__icontains=value) | Q(search_document__icontains=value))

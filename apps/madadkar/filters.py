"""
Filters اپ مددکار — django-filter filtersets.

ساختار:
- CampaignPublicFilter: فیلتر برای endpoint عمومی (subset امن)
- CampaignAdminFilter: فیلتر کامل برای ادمین (شامل status و is_visible)
- SponsorAdminFilter: فیلتر مددکاران برای ادمین

اصول:
- فیلترهای عمومی نباید اطلاعات حساس را افشا کنند (مثلاً status=DRAFT).
- فیلترهای ادمین کامل و قابل ترکیب.
- ordering با چند گزینه معتبر.
"""

from __future__ import annotations

from django_filters import rest_framework as filters

from apps.core.search import SearchField, apply_smart_search
from apps.madadkar.choices import CampaignStatus
from apps.madadkar.models import Campaign, Sponsor

# ---------------------------------------------------------------------------
# Public-allowed campaign statuses
# ---------------------------------------------------------------------------

_PUBLIC_STATUS_CHOICES = (
    (CampaignStatus.PUBLISHED, CampaignStatus.PUBLISHED.label),
    (CampaignStatus.COMPLETED, CampaignStatus.COMPLETED.label),
    (CampaignStatus.CLOSED, CampaignStatus.CLOSED.label),
)


# ---------------------------------------------------------------------------
# Campaign — public filter
# ---------------------------------------------------------------------------


class CampaignPublicFilter(filters.FilterSet):
    """
    فیلتر حرکت‌ها در endpoint عمومی.

    فقط فیلترهای امن — هیچ راهی برای دیدن DRAFT یا is_visible=False نیست
    (در selector فیلتر شده‌اند).
    """

    sponsor = filters.NumberFilter(field_name="sponsor_id")
    sponsor_slug = filters.CharFilter(field_name="sponsor__slug")
    status = filters.ChoiceFilter(choices=_PUBLIC_STATUS_CHOICES)
    has_deadline = filters.BooleanFilter()
    is_fully_funded = filters.BooleanFilter(method="filter_is_fully_funded")
    search = filters.CharFilter(method="filter_search")

    ordering = filters.OrderingFilter(
        fields=(
            ("published_at", "published_at"),
            ("created_at", "created_at"),
            ("progress_percent_calc", "progress"),
            ("deadline", "deadline"),
        ),
    )

    class Meta:
        model = Campaign
        fields = ("sponsor", "sponsor_slug", "status", "has_deadline")

    def filter_is_fully_funded(self, queryset, name, value):
        """فیلتر بر اساس fully_funded — مقایسه purchased_shares با total_shares."""
        from django.db.models import F

        if value is True:
            return queryset.filter(purchased_shares__gte=F("total_shares"))
        return queryset.filter(purchased_shares__lt=F("total_shares"))

    def filter_search(self, queryset, name, value):
        """جستجوی متنی production-grade با fallback امن."""
        return apply_smart_search(
            queryset,
            search_term=value,
            fields=[
                SearchField("title", "A"),
                SearchField("description", "B"),
                SearchField("sponsor__name", "C"),
            ],
            trigram_fields=["title", "description", "sponsor__name"],
        )


# ---------------------------------------------------------------------------
# Campaign — admin filter
# ---------------------------------------------------------------------------


class CampaignAdminFilter(filters.FilterSet):
    """
    فیلتر کامل حرکت‌ها برای ادمین.

    شامل تمام وضعیت‌ها (حتی DRAFT) و فیلتر is_visible.
    """

    sponsor = filters.NumberFilter(field_name="sponsor_id")
    sponsor_slug = filters.CharFilter(field_name="sponsor__slug")
    status = filters.ChoiceFilter(choices=CampaignStatus.choices)
    is_visible = filters.BooleanFilter()
    is_active = filters.BooleanFilter()
    has_deadline = filters.BooleanFilter()
    is_fully_funded = filters.BooleanFilter(method="filter_is_fully_funded")

    created_after = filters.DateTimeFilter(
        field_name="created_at",
        lookup_expr="gte",
    )
    created_before = filters.DateTimeFilter(
        field_name="created_at",
        lookup_expr="lte",
    )
    published_after = filters.DateTimeFilter(
        field_name="published_at",
        lookup_expr="gte",
    )
    published_before = filters.DateTimeFilter(
        field_name="published_at",
        lookup_expr="lte",
    )

    min_total_amount = filters.NumberFilter(
        field_name="total_amount",
        lookup_expr="gte",
    )
    max_total_amount = filters.NumberFilter(
        field_name="total_amount",
        lookup_expr="lte",
    )

    search = filters.CharFilter(method="filter_search")

    ordering = filters.OrderingFilter(
        fields=(
            ("created_at", "created_at"),
            ("published_at", "published_at"),
            ("deadline", "deadline"),
            ("total_amount", "total_amount"),
            ("purchased_amount", "purchased_amount"),
            ("participant_count", "participant_count"),
        ),
    )

    class Meta:
        model = Campaign
        fields = (
            "sponsor",
            "sponsor_slug",
            "status",
            "is_visible",
            "is_active",
            "has_deadline",
        )

    def filter_is_fully_funded(self, queryset, name, value):
        """فیلتر بر اساس fully_funded."""
        from django.db.models import F

        if value is True:
            return queryset.filter(purchased_shares__gte=F("total_shares"))
        return queryset.filter(purchased_shares__lt=F("total_shares"))

    def filter_search(self, queryset, name, value):
        """جستجوی متنی production-grade در عنوان، توضیحات و نام مددکار."""
        return apply_smart_search(
            queryset,
            search_term=value,
            fields=[
                SearchField("title", "A"),
                SearchField("description", "B"),
                SearchField("sponsor__name", "C"),
            ],
            trigram_fields=["title", "description", "sponsor__name"],
        )


# ---------------------------------------------------------------------------
# Sponsor — admin filter
# ---------------------------------------------------------------------------


class SponsorAdminFilter(filters.FilterSet):
    """فیلتر مددکاران برای ادمین."""

    is_active = filters.BooleanFilter()
    search = filters.CharFilter(field_name="name", lookup_expr="icontains")

    ordering = filters.OrderingFilter(
        fields=(
            ("name", "name"),
            ("created_at", "created_at"),
        ),
    )

    class Meta:
        model = Sponsor
        fields = ("is_active",)

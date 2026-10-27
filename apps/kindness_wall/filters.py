"""django-filter filtersetهای دیوار مهربانی.

قرارداد سراسری جستجو حفظ شده: فیلتر عمومی ``KindnessListingPublicFilter`` با
پارامتر ``search`` روی کوئری‌ست ورودی ``apply_smart_search`` می‌زند (FTS/trgm
روی PostgreSQL و icontains در fallback) — همان چیزی که تست‌های shared جستجو
از همهٔ اپ‌ها انتظار دارند.
"""

from __future__ import annotations

import django_filters

from apps.core.search import SearchField, apply_smart_search
from apps.kindness_wall.choices import ListingStatus, OfferStatus, Urgency
from apps.kindness_wall.models import KindnessListing, KindnessOffer

#: mapping ورودی کاربر → tuples کامل ترتیب (کلید دوم برای پایداری pageها).
_ORDERING_CHOICES: dict[str, tuple[str, ...]] = {
    "fresh": ("-published_at", "-created_at"),
    "popular": ("-view_count", "-published_at"),
    "urgent": ("urgency", "-published_at"),
    "expiring": ("expires_at", "-published_at"),
}


class KindnessListingPublicFilter(django_filters.FilterSet):
    """فیلترهای تختهٔ عمومی: دسته، جغرا، فوریت، ordering و جستجو."""

    category = django_filters.CharFilter(field_name="category__slug", lookup_expr="exact")
    province = django_filters.CharFilter(field_name="province", lookup_expr="iexact")
    city = django_filters.CharFilter(field_name="city", lookup_expr="iexact")
    urgent = django_filters.BooleanFilter(method="filter_urgent")
    ordering = django_filters.CharFilter(method="filter_ordering")
    search = django_filters.CharFilter(method="filter_search")

    class Meta:
        model = KindnessListing
        fields: list[str] = []

    def filter_urgent(self, queryset, name, value):
        """فیلتر «فقط فوری‌ها»."""
        if not value:
            return queryset
        return queryset.filter(urgency=Urgency.URGENT)

    def filter_ordering(self, queryset, name, value):
        """ترتیب از لیست مجاز؛ ورودی نامعتبر بی‌اثر (بدون خطای ۴۰۰)."""
        mapping = _ORDERING_CHOICES.get((value or "").strip())
        if mapping is None:
            return queryset
        return queryset.order_by(*mapping)

    def filter_search(self, queryset, name, value):
        """جستجوی هوشمند روی عنوان/شرح/سندِ ارجعی + fallback ایندکس‌محور."""
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
    """فیلترهای ادمین: به‌علاوهٔ وضعیت چرخهٔ حیات."""

    status = django_filters.ChoiceFilter(choices=ListingStatus.choices)


class KindnessOfferAdminFilter(django_filters.FilterSet):
    """فیلترهای صف بررسی اعلام‌های آمادگی."""

    status = django_filters.ChoiceFilter(choices=OfferStatus.choices)
    listing_id = django_filters.NumberFilter(field_name="listing_id")
    user_id = django_filters.NumberFilter(field_name="user_id")

    class Meta:
        model = KindnessOffer
        fields: list[str] = []

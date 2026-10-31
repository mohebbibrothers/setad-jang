"""django-filter filtersetهای دیوار مهربانی.

قرارداد سراسری جستجو حفظ شده: فیلتر عمومی ``KindnessListingPublicFilter`` با
پارامتر ``search`` روی کوئری‌ست ورودی ``apply_smart_search`` می‌زند (FTS/trgm
روی PostgreSQL و icontains در fallback) — همان چیزی که تست‌های shared جستجو
از همهٔ اپ‌ها انتظار دارند.
"""

from __future__ import annotations

import django_filters
from django.db.models import Q

from apps.core.geo import normalize_province
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
    province = django_filters.CharFilter(method="filter_province")
    city = django_filters.CharFilter(method="filter_city")
    urgent = django_filters.BooleanFilter(method="filter_urgent")
    ordering = django_filters.CharFilter(method="filter_ordering")
    search = django_filters.CharFilter(method="filter_search")

    class Meta:
        model = KindnessListing
        fields: list[str] = []

    def filter_province(self, queryset, name, value):
        """آگهی‌های همان استان **+ آگهی‌های سراسر کشور**.

        سیاست محصول: آگهیِ «سراسر کشور» یعنی «در هر نقطه از ایران قابلِ
        برآورده‌شدن است»، پس وقتی کاربر استانی را فیلتر می‌کند باید همان‌ها هم
        ببیند؛ در غیر این صورت گران‌ترین نیازها (که عامدانه سراسری ثبت شده‌اند)
        از دیدِ فیلترشده پنهان می‌شوند. استانِ خالی = کلِ سرزمین.
        """
        raw = (value or "").strip()
        if not raw:
            return queryset
        province = normalize_province(raw) or raw
        return queryset.filter(
            Q(province__iexact=province) | Q(province__isnull=True) | Q(province="")
        )

    def filter_city(self, queryset, name, value):
        """آگهی‌های همان شهر + استانِ خالی (سراسر کشور) + شهرِ خالی.

        شهرِ خالی در آگهی یعنی «همهٔ شهرهای آن استان» (یا سراسر کشور)، پس با
        فیلترِ شهرِ کاربر هم باید دیده شود. اگر کاربر شهری را فیلتر کند که در
        دیتاست نیست، همان عبارت به‌صورت iexact و بدونِ خطا اعمال می‌شود.
        """
        raw = (value or "").strip()
        if not raw:
            return queryset
        return queryset.filter(Q(city__iexact=raw) | Q(city__isnull=True) | Q(city=""))

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

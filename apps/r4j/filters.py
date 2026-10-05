"""
Filters اپ R4J.

فیلترهای مورد استفاده در list endpointهای criminals، reports و bounties:

- public criminal:
    search + location + gender

- admin criminal:
    همان موارد + is_published + is_active

- admin report:
    status + criminal + submitted_by + date range

- user report:
    status

- admin bounty:
    status + criminal + user + date range

- user bounty:
    status + criminal + date range

اصول طراحی:
- فیلترها فقط روی read-side اعمال می‌شوند.
- queryset اصلی scope را enforce می‌کند (مثلاً user فقط داده‌های خودش را می‌بیند).
- business permissionها در filter layer پیاده‌سازی نمی‌شوند.
- searchها distinct هستند تا join روی aliases باعث duplicate row نشود.
"""

from __future__ import annotations

import django_filters
from django.db.models import QuerySet

from apps.core.search import SearchField, apply_smart_search

from .choices import BountyStatus, Gender, ReportStatus
from .models import R4JBounty, R4JCriminal, R4JReport

# ============================================================
# Criminal Filters
# ============================================================


class R4JCriminalPublicFilter(django_filters.FilterSet):
    """
    فیلترهای endpoint عمومی لیست criminals.

    فیلدهای پشتیبانی‌شده:
    - search: جستجو در نام، نام خانوادگی، slug و aliases
    - country / province / city: فیلتر مکانی
    - gender: فیلتر جنسیت
    """

    search = django_filters.CharFilter(
        method="filter_search",
        help_text="جستجو در نام، نام خانوادگی، slug و اسامی مستعار",
    )
    country = django_filters.CharFilter(field_name="country", lookup_expr="iexact")
    province = django_filters.CharFilter(field_name="province", lookup_expr="iexact")
    city = django_filters.CharFilter(field_name="city", lookup_expr="iexact")
    gender = django_filters.ChoiceFilter(choices=Gender.choices)
    ordering = django_filters.OrderingFilter(
        fields=(
            ("total_bounty_toman", "total_bounty_toman"),
            ("bounties_count", "bounties_count"),
            ("published_at", "published_at"),
            ("created_at", "created_at"),
            ("first_name", "first_name"),
            ("last_name", "last_name"),
        ),
        help_text=(
            "مرتب‌سازی نتایج — مقادیر مجاز: total_bounty_toman، bounties_count، "
            "published_at، created_at، first_name، last_name "
            "(پیش‌وند «-» برای نزولی، مثل -total_bounty_toman)"
        ),
    )

    class Meta:
        model = R4JCriminal
        fields: list[str] = []

    def filter_search(
        self,
        queryset: QuerySet[R4JCriminal],
        name: str,
        value: str,
    ) -> QuerySet[R4JCriminal]:
        """
        جستجو در نام، نام خانوادگی، slug و اسامی مستعار.

        distinct لازم است چون join روی aliases ممکن است
        duplicate row تولید کند.
        """
        searched = apply_smart_search(
            queryset,
            search_term=value,
            fields=[
                SearchField("first_name", "A"),
                SearchField("last_name", "A"),
                SearchField("slug", "B"),
                SearchField("aliases__alias", "B"),
            ],
            trigram_fields=["first_name", "last_name", "slug", "aliases__alias"],
        )
        return searched.distinct()


class R4JCriminalAdminFilter(R4JCriminalPublicFilter):
    """
    فیلتر admin برای criminals.

    علاوه بر فیلترهای public:
    - is_published
    - is_active

    همچنین search روی national_code هم پشتیبانی می‌شود.
    """

    is_published = django_filters.BooleanFilter(field_name="is_published")
    is_active = django_filters.BooleanFilter(field_name="is_active")

    def filter_search(
        self,
        queryset: QuerySet[R4JCriminal],
        name: str,
        value: str,
    ) -> QuerySet[R4JCriminal]:
        """
        جستجو در نام، نام خانوادگی، slug، کد ملی و aliases.

        این search فقط در admin scope استفاده می‌شود.
        """
        searched = apply_smart_search(
            queryset,
            search_term=value,
            fields=[
                SearchField("first_name", "A"),
                SearchField("last_name", "A"),
                SearchField("slug", "B"),
                SearchField("national_code", "B"),
                SearchField("aliases__alias", "B"),
            ],
            trigram_fields=["first_name", "last_name", "slug", "national_code", "aliases__alias"],
        )
        return searched.distinct()


# ============================================================
# Report Filters
# ============================================================


class R4JReportAdminFilter(django_filters.FilterSet):
    """
    فیلتر لیست گزارشات برای admin.

    فیلدهای قابل فیلتر:
    - status: وضعیت گزارش
    - criminal_id: شناسه مجرم
    - submitted_by_id: شناسه گزارش‌دهنده
    - created_after / created_before: بازه زمانی
    """

    status = django_filters.ChoiceFilter(choices=ReportStatus.choices)
    criminal_id = django_filters.NumberFilter(field_name="criminal_id")
    submitted_by_id = django_filters.NumberFilter(field_name="submitted_by_id")
    created_after = django_filters.DateTimeFilter(
        field_name="created_at",
        lookup_expr="gte",
    )
    created_before = django_filters.DateTimeFilter(
        field_name="created_at",
        lookup_expr="lte",
    )

    class Meta:
        model = R4JReport
        fields: list[str] = []


class R4JReportUserFilter(django_filters.FilterSet):
    """
    فیلتر لیست گزارشات کاربر.

    فقط status قابل فیلتر است چون queryset از قبل
    به user جاری محدود شده است.
    """

    status = django_filters.ChoiceFilter(choices=ReportStatus.choices)

    class Meta:
        model = R4JReport
        fields: list[str] = []


# ============================================================
# Bounty Filters
# ============================================================


class R4JBountyAdminFilter(django_filters.FilterSet):
    """
    فیلتر لیست bountyها برای admin.

    فیلدهای قابل فیلتر:
    - status: وضعیت bounty
    - criminal_id: شناسه مجرم
    - user_id: شناسه کاربر تعیین‌کننده جایزه
    - created_after / created_before: بازه زمانی
    """

    status = django_filters.ChoiceFilter(choices=BountyStatus.choices)
    criminal_id = django_filters.NumberFilter(field_name="criminal_id")
    user_id = django_filters.NumberFilter(field_name="user_id")
    created_after = django_filters.DateTimeFilter(
        field_name="created_at",
        lookup_expr="gte",
    )
    created_before = django_filters.DateTimeFilter(
        field_name="created_at",
        lookup_expr="lte",
    )

    class Meta:
        model = R4JBounty
        fields: list[str] = []


class R4JBountyUserFilter(django_filters.FilterSet):
    """
    فیلتر لیست bountyهای کاربر.

    queryset اصلی از قبل به user جاری محدود شده است؛
    بنابراین user_id اینجا وجود ندارد.

    فیلدهای قابل فیلتر:
    - status
    - criminal_id
    - created_after / created_before
    """

    status = django_filters.ChoiceFilter(choices=BountyStatus.choices)
    criminal_id = django_filters.NumberFilter(field_name="criminal_id")
    created_after = django_filters.DateTimeFilter(
        field_name="created_at",
        lookup_expr="gte",
    )
    created_before = django_filters.DateTimeFilter(
        field_name="created_at",
        lookup_expr="lte",
    )

    class Meta:
        model = R4JBounty
        fields: list[str] = []

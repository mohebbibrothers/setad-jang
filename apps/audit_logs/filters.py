"""
Filters اپ audit_logs.

فیلترهای مورد استفاده در admin audit log list endpoint.

اصول طراحی:
- تمام فیلترها اختیاری هستند.
- date range با created_after و created_before پشتیبانی می‌شود.
- search روی action, resource_type و resource_id اعمال می‌شود.
"""

from __future__ import annotations

import django_filters

from .models import AuditLog


class AuditLogFilter(django_filters.FilterSet):
    """فیلتر audit log برای admin list endpoint."""

    action = django_filters.CharFilter(
        field_name="action",
        lookup_expr="exact",
        help_text="فیلتر بر اساس نوع عملیات (exact match)",
    )
    user_id = django_filters.NumberFilter(
        field_name="user_id",
        lookup_expr="exact",
        help_text="فیلتر بر اساس شناسه کاربر",
    )
    resource_type = django_filters.CharFilter(
        field_name="resource_type",
        lookup_expr="exact",
        help_text="فیلتر بر اساس نوع منبع",
    )
    resource_id = django_filters.CharFilter(
        field_name="resource_id",
        lookup_expr="exact",
        help_text="فیلتر بر اساس شناسه منبع",
    )
    request_id = django_filters.CharFilter(
        field_name="request_id",
        lookup_expr="exact",
        help_text="فیلتر بر اساس شناسه درخواست",
    )
    ip_address = django_filters.CharFilter(
        field_name="ip_address",
        lookup_expr="exact",
        help_text="فیلتر بر اساس آدرس IP",
    )
    created_after = django_filters.IsoDateTimeFilter(
        field_name="created_at",
        lookup_expr="gte",
        help_text="فیلتر از تاریخ (ISO 8601)",
    )
    created_before = django_filters.IsoDateTimeFilter(
        field_name="created_at",
        lookup_expr="lte",
        help_text="فیلتر تا تاریخ (ISO 8601)",
    )
    search = django_filters.CharFilter(
        method="filter_search",
        help_text="جستجو در action, resource_type و resource_id",
    )

    class Meta:
        model = AuditLog
        fields: list[str] = []

    def filter_search(
        self,
        queryset: django_filters.QuerySet,
        name: str,
        value: str,
    ) -> django_filters.QuerySet:
        """جستجوی متنی در فیلدهای کلیدی audit log."""
        from django.db.models import Q

        return queryset.filter(
            Q(action__icontains=value)
            | Q(resource_type__icontains=value)
            | Q(resource_id__icontains=value),
        )

"""فیلترهای محتوای تبیین."""

import django_filters
from django.db.models import Q

from apps.core.search import SearchField, apply_smart_search
from apps.tabyin.choices import MediaType
from apps.tabyin.models import TabyinAttachment, TabyinContent


class PublicTabyinContentFilter(django_filters.FilterSet):
    """فیلتر عمومی محتواهای تبیین."""

    media_type = django_filters.ChoiceFilter(
        choices=MediaType.choices,
        method="filter_by_media_type",
        label="نوع رسانه",
    )
    author = django_filters.CharFilter(
        field_name="author_username",
        lookup_expr="icontains",
        label="نویسنده",
    )
    search = django_filters.CharFilter(
        method="filter_search",
        label="جستجو",
    )

    class Meta:
        model = TabyinContent
        fields = ["media_type", "author"]

    def filter_by_media_type(self, queryset, name, value):
        """فیلتر بر اساس نوع رسانه — ملاک، «پیوستِ واقعی» است.

        برای «سایر» (متن‌محورها) یک استثنای مهم لحاظ می‌شود: نوشته‌های
        متنی که هیچ پیوستی ندارند هم باید در تب «متن» دیده شوند؛ پس
        علاوه بر پیوست‌های other، محتواهای فاقدِ هرگونه پیوست هم در
        این باکت می‌آیند. برای سایر انواع (فیلم/عکس/صوت) صرفاً وجودِ
        پیوستِ همان نوع ملاک است — تا محتوایی که بالادست به‌غلط
        طبقه‌بندی شده، در تب اشتباه دیده نشود.
        """
        content_ids = (
            TabyinAttachment.objects.filter(
                media_type=value,
            )
            .values_list("content_id", flat=True)
            .distinct()
        )
        if value == MediaType.OTHER:
            return queryset.filter(Q(id__in=content_ids) | Q(attachments__isnull=True)).distinct()
        return queryset.filter(id__in=content_ids)

    def filter_search(self, queryset, name, value):
        """جستجو با PostgreSQL FTS/trigram و fallback امن."""
        return apply_smart_search(
            queryset,
            search_term=value,
            fields=[
                SearchField("title", "A"),
                SearchField("description", "B"),
                SearchField("author_username", "C"),
            ],
            trigram_fields=["title", "description"],
        )


class AdminTabyinContentFilter(django_filters.FilterSet):
    """فیلتر ادمین محتواهای تبیین — شامل فیلدهای مدیریتی."""

    media_type = django_filters.ChoiceFilter(
        choices=MediaType.choices,
        method="filter_by_media_type",
        label="نوع رسانه",
    )
    author = django_filters.CharFilter(
        field_name="author_username",
        lookup_expr="icontains",
        label="نویسنده",
    )
    is_active = django_filters.BooleanFilter(
        field_name="is_active",
        label="فعال",
    )
    is_deleted_in_source = django_filters.BooleanFilter(
        field_name="is_deleted_in_source",
        label="حذف‌شده در منبع",
    )
    search = django_filters.CharFilter(
        method="filter_search",
        label="جستجو",
    )

    class Meta:
        model = TabyinContent
        fields = [
            "media_type",
            "author",
            "is_active",
            "is_deleted_in_source",
        ]

    def filter_by_media_type(self, queryset, name, value):
        """فیلتر بر اساس نوع رسانه پیوست‌ها."""
        content_ids = (
            TabyinAttachment.objects.filter(
                media_type=value,
            )
            .values_list("content_id", flat=True)
            .distinct()
        )
        return queryset.filter(id__in=content_ids)

    def filter_search(self, queryset, name, value):
        """جستجو با PostgreSQL FTS/trigram و fallback امن."""
        return apply_smart_search(
            queryset,
            search_term=value,
            fields=[
                SearchField("title", "A"),
                SearchField("description", "B"),
                SearchField("author_username", "C"),
            ],
            trigram_fields=["title", "description"],
        )

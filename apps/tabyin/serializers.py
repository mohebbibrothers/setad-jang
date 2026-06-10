"""
Serializers برای اپ تبیین.

سریالایزرهای جداگانه برای public و admin، شامل:
- نمایش محتوا (public/admin)
- toggle وضعیت محتوا
- اجرای دستی sync (به‌صورت async در background)
- پیگیری وضعیت task پس‌زمینه

اصول طراحی:
- هیچ business logic داخل سریالایزرها نیست.
- خروجی سریالایزرها JSON-friendly و سازگار با response envelope پروژه است.
- سریالایزرهای async dispatch مستقل از Celery طراحی شده‌اند تا از
  وابستگی مستقیم لایه‌ی API به runtime زیرساخت async جلوگیری شود.
"""

from rest_framework import serializers

from apps.tabyin.models import TabyinAttachment, TabyinContent

# ============================================================
# Attachment Serializers
# ============================================================


class TabyinAttachmentSerializer(serializers.ModelSerializer):
    """سریالایزر پیوست — برای هر دو public و admin."""

    media_type_display = serializers.CharField(
        source="get_media_type_display",
        read_only=True,
    )

    class Meta:
        model = TabyinAttachment
        fields = [
            "id",
            "url",
            "media_type",
            "media_type_display",
            "size",
            "duration",
            "file_size",
            "title",
            "order",
        ]


# ============================================================
# Public Serializers
# ============================================================


class PublicTabyinContentListSerializer(serializers.ModelSerializer):
    """
    لیست محتواها — نمایش عمومی.

    فقط فیلدهای ضروری برای نمایش در گالری.
    """

    attachments = TabyinAttachmentSerializer(many=True, read_only=True)
    primary_media_type = serializers.CharField(read_only=True)

    class Meta:
        model = TabyinContent
        fields = [
            "external_id",
            "title",
            "description",
            "author_username",
            "source_created_at",
            "source_url",
            "primary_media_type",
            "attachments",
        ]


class PublicTabyinContentDetailSerializer(serializers.ModelSerializer):
    """
    جزئیات یک محتوا — نمایش عمومی.

    اطلاعات بیشتر نسبت به لیست.
    """

    attachments = TabyinAttachmentSerializer(many=True, read_only=True)
    primary_media_type = serializers.CharField(read_only=True)

    class Meta:
        model = TabyinContent
        fields = [
            "external_id",
            "title",
            "description",
            "author_username",
            "source_entity_id",
            "source_created_at",
            "source_updated_at",
            "source_url",
            "primary_media_type",
            "attachments",
        ]


# ============================================================
# Admin Serializers — Content
# ============================================================


class AdminTabyinContentListSerializer(serializers.ModelSerializer):
    """لیست محتواها — ادمین (شامل فیلدهای مدیریتی)."""

    attachments_count = serializers.IntegerField(
        source="attachments.count",
        read_only=True,
    )

    class Meta:
        model = TabyinContent
        fields = [
            "id",
            "external_id",
            "title",
            "author_username",
            "source_status",
            "source_type",
            "source_created_at",
            "source_updated_at",
            "is_active",
            "is_deleted_in_source",
            "last_synced_at",
            "attachments_count",
            "created_at",
            "updated_at",
        ]


class AdminTabyinContentDetailSerializer(serializers.ModelSerializer):
    """جزئیات محتوا — ادمین (شامل raw_payload)."""

    attachments = TabyinAttachmentSerializer(many=True, read_only=True)

    class Meta:
        model = TabyinContent
        fields = [
            "id",
            "external_id",
            "title",
            "description",
            "author_username",
            "source_entity_id",
            "source_status",
            "source_type",
            "source_created_at",
            "source_updated_at",
            "source_url",
            "content_hash",
            "last_synced_at",
            "is_active",
            "is_deleted_in_source",
            "raw_payload",
            "attachments",
            "created_at",
            "updated_at",
        ]


class AdminTabyinContentToggleSerializer(serializers.Serializer):
    """سریالایزر فعال/غیرفعال کردن محتوا."""

    is_active = serializers.BooleanField(
        required=True,
        help_text="آیا محتوا در سایت عمومی نمایش داده شود؟",
    )


# ============================================================
# Admin Serializers — Sync (Async via Celery)
# ============================================================


class AdminSyncTriggerSerializer(serializers.Serializer):
    """
    سریالایزر درخواست اجرای دستی sync.

    این endpoint اجرای sync را به‌صورت async به Celery می‌سپارد و
    بلافاصله پاسخ می‌دهد. خود ادمین می‌تواند با task_id وضعیت اجرا
    را پیگیری کند.
    """

    mode = serializers.ChoiceField(
        choices=["full", "incremental"],
        default="incremental",
        help_text="حالت همگام‌سازی: full یا incremental",
    )


class AdminSyncTaskDispatchedSerializer(serializers.Serializer):
    """
    سریالایزر پاسخ زمانی که sync با موفقیت در صف Celery قرار گرفت.

    این پاسخ فقط نشان می‌دهد task با موفقیت publish شده است،
    نه اینکه اجرا/تمام شده است.
    """

    task_id = serializers.CharField(
        help_text="شناسه یکتای task برای پیگیری وضعیت.",
    )
    mode = serializers.ChoiceField(
        choices=["full", "incremental"],
        help_text="حالت اجرای sync.",
    )
    status_url = serializers.CharField(
        help_text="مسیری برای پیگیری وضعیت اجرا.",
    )


class SyncStatsSerializer(serializers.Serializer):
    """
    سریالایزر خروجی نهایی sync.

    فیلدها دقیقاً منعکس‌کننده ساختار `SyncStats` در sync engine هستند.
    این سریالایزر هم برای نمایش نتیجه‌ی task موفق استفاده می‌شود،
    هم برای نمایش آمار اجراهای قبلی.
    """

    pages_fetched = serializers.IntegerField()
    items_processed = serializers.IntegerField()
    created = serializers.IntegerField()
    updated = serializers.IntegerField()
    unchanged = serializers.IntegerField()
    soft_deleted = serializers.IntegerField()
    errors = serializers.IntegerField()
    skipped = serializers.IntegerField()
    duration_seconds = serializers.FloatField()
    started_at = serializers.DateTimeField(required=False, allow_null=True)


class AdminSyncTaskStatusSerializer(serializers.Serializer):
    """
    سریالایزر وضعیت یک task پس‌زمینه‌ی sync.

    قراردادها:
    - `state`: یکی از مقادیر استاندارد Celery (PENDING, STARTED, RETRY,
      SUCCESS, FAILURE, REVOKED).
    - `ready`: اگر task به وضعیت نهایی رسیده باشد True است.
    - `successful`: فقط برای taskهای ready مقدار معنادار دارد.
    - `result`: در حالت SUCCESS، آمار sync (همان شکل SyncStats).
    - `error`: در حالت FAILURE پیام/نوع خطا برای ادمین.
    """

    task_id = serializers.CharField()
    state = serializers.CharField()
    ready = serializers.BooleanField()
    successful = serializers.BooleanField(required=False, allow_null=True)
    result = SyncStatsSerializer(required=False, allow_null=True)
    error = serializers.CharField(required=False, allow_null=True)

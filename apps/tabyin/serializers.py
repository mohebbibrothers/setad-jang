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

from urllib.parse import urlparse

from rest_framework import serializers

from apps.tabyin import selectors as tabyin_selectors
from apps.tabyin.choices import MediaType
from apps.tabyin.models import TabyinAttachment, TabyinContent
from apps.tabyin.uploading import is_local_media_url, sniff_media_type_from_url

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
    نام پدیدآورنده برای ارسال‌های کاربران پویا و همیشه به‌روز است.
    """

    attachments = TabyinAttachmentSerializer(many=True, read_only=True)
    primary_media_type = serializers.CharField(read_only=True)
    author_username = serializers.SerializerMethodField()

    def get_author_username(self, obj: TabyinContent) -> str:
        return tabyin_selectors.resolve_author_display(obj)

    class Meta:
        model = TabyinContent
        fields = [
            "external_id",
            "title",
            "description",
            "author_username",
            "origin",
            "source_created_at",
            "source_url",
            "primary_media_type",
            "attachments",
        ]


class PublicTabyinContentDetailSerializer(serializers.ModelSerializer):
    """
    جزئیات یک محتوا — نمایش عمومی.

    اطلاعات بیشتر نسبت به لیست.
    نام پدیدآورنده برای ارسال‌های کاربران پویا و همیشه به‌روز است.
    """

    attachments = TabyinAttachmentSerializer(many=True, read_only=True)
    primary_media_type = serializers.CharField(read_only=True)
    author_username = serializers.SerializerMethodField()

    def get_author_username(self, obj: TabyinContent) -> str:
        return tabyin_selectors.resolve_author_display(obj)

    class Meta:
        model = TabyinContent
        fields = [
            "external_id",
            "title",
            "description",
            "author_username",
            "origin",
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
            "origin",
            "submission_status",
            "submitted_by_id",
            "reviewed_by_id",
            "reviewed_at",
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
            "origin",
            "submission_status",
            "submitted_by_id",
            "reviewed_by_id",
            "reviewed_at",
            "admin_note",
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


# ============================================================
# User Submission Serializers
# ============================================================


class TabyinSubmissionAttachmentInputSerializer(serializers.Serializer):
    """Input serializer for user-submitted content attachment URLs."""

    url = serializers.CharField(max_length=1024, trim_whitespace=True)
    # عمداً default ندارد: «کاربر نوع را انتخاب نکرده» باید از «آگاهانه other
    # را انتخاب کرده» تفکیک شود تا object-level validation بتواند نوعِ واقعی
    # را از پسوندِ نشانی حدس بزند (تک‌نوع‌سازیِ سخت‌گیرانه).
    media_type = serializers.ChoiceField(choices=MediaType.choices, required=False)
    title = serializers.CharField(max_length=512, required=False, allow_blank=True)
    order = serializers.IntegerField(required=False, min_value=0, default=0)

    def validate_url(self, value: str) -> str:
        """
        نشانی پیوست یا مطلقِ http(s) است یا نشانیِ رسانه‌ی داخلیِ سایت
        (نتیجه‌ی «آپلود مستقیم» — مسیر /media/… یا نشانی CDN خودمان).
        """
        if is_local_media_url(value):
            return value
        parsed = urlparse(value)
        if parsed.scheme in ("http", "https") and parsed.netloc:
            return value
        raise serializers.ValidationError(
            "نشانی پیوست معتبر نیست؛ یک نشانی http/https یا نشانیِ رسانه‌ی داخلی سایت بفرست."
        )


HOMOGENEOUS_TYPES_MESSAGE = (
    "هر روایت فقط یک نوع رسانه می‌پذیرد؛ همه‌ی پیوست‌ها باید هم‌نوع "
    "باشند (همه تصویر یا همه ویدئو یا همه صوت یا همه سایر)."
)


def enforce_homogeneous_attachments(attachments: list[dict]) -> list[dict]:
    """
    تک‌نوع‌سازیِ سخت‌گیرانه‌ی پیوست‌ها — سه لایه‌ی دفاعی:

    ۱) **نرمال‌سازیِ نوعِ واقعی:** وقتی کاربر media_type را نفرستاده
       (پیش‌فرضِ خاموش)، نوع از پسوندِ مسیرِ نشانی بویده می‌شود و همان
       مقدارِ نهایی در validated_data می‌نشیند؛ دیگر هر نشانیِ ناشناس
       چترِ پیش‌فرضِ «other» نمی‌شود که مخلوطِ عکس+ویدئو را پنهان کند.
    ۲) **ردِ ناسازگاریِ اعلام/واقعیت:** اگر پسوندِ نشانی قابل‌تشخیص باشد و
       با نوعِ اعلانی نخواند (مثلاً نشانیِ mp4 با اعلامِ «تصویر») رد می‌شود
       تا دورزدنِ دستیِ قانون هم ممکن نباشد؛ نشانیِ بدونِ پسوندِ شناخته‌شده
       (URLهای داینامیک) به اعلامِ کاربر اعتماد می‌کند.
    ۳) **قفلِ نهایی:** اگر بیش از یک نوعِ مؤثر در فهرست دیده شود، همان
       خطای قرارداد (کلید attachments) برمی‌گردد.

    هر دو serializer ساخت و ویرایش از همین تابع استفاده می‌کنند تا قانون
    تک‌نوعی هرگز دو معنا نداشته باشد.
    """
    effective_types: set[str] = set()
    for attachment in attachments:
        declared = attachment.get("media_type")
        sniffed = sniff_media_type_from_url(attachment.get("url", ""))
        if declared and sniffed and declared != sniffed:
            raise serializers.ValidationError(
                {
                    "attachments": (
                        f"نوعِ اعلامیِ پیوست «{MediaType(declared).label}» با پسوندِ "
                        f"نشانی‌اش («{MediaType(sniffed).label}») ناسازگار است؛ نوع را "
                        "همان چیزی انتخاب کن که فایل واقعاً هست."
                    )
                }
            )
        resolved = declared or sniffed or MediaType.OTHER
        attachment["media_type"] = resolved
        effective_types.add(resolved)
    if len(effective_types) > 1:
        raise serializers.ValidationError({"attachments": HOMOGENEOUS_TYPES_MESSAGE})
    return attachments


def validate_attachments_count(value: list[dict]) -> list[dict]:
    """Limit attachment count to keep review workload and payload size bounded."""
    if len(value) > 5:
        raise serializers.ValidationError("حداکثر ۵ پیوست برای هر محتوا مجاز است.")
    return value


class UserTabyinSubmissionCreateSerializer(serializers.Serializer):
    """Input serializer for authenticated user content submissions."""

    title = serializers.CharField(max_length=512)
    description = serializers.CharField()
    attachments = TabyinSubmissionAttachmentInputSerializer(
        many=True,
        required=False,
        allow_empty=True,
    )

    def validate_attachments(self, value: list[dict]) -> list[dict]:
        """سقفِ تعداد پیوست — همان قراردادِ نمایشیِ استودیو."""
        return validate_attachments_count(value)

    def validate(self, attrs: dict) -> dict:
        """هر روایت یک‌نوع است: همه‌ی پیوست‌ها باید هم‌نوع رسانه باشند."""
        enforce_homogeneous_attachments(attrs.get("attachments") or [])
        return attrs


class UserTabyinSubmissionUpdateSerializer(serializers.Serializer):
    """
    ویرایشِ روایتِ خود کاربر (PATCH) — جایگزینیِ نقطه‌ای با ماهیتِ کامل.

    - title / description فقط در صورت ارسال، مقدار قبلی را جایگزین می‌کنند؛
    - attachments اگر ارسال شود فهرستِ کاملِ جدید است (replace-all) و همان
      قوانینِ ساخت — تک‌نوعیِ سخت‌گیرانه و سقفِ ۵ پیوست — را می‌گذراند؛
    - دست‌کم یک فیلد باید ارسال شود تا ویرایشِ تهی معنا نداشته باشد.
    """

    title = serializers.CharField(max_length=512, required=False)
    description = serializers.CharField(required=False)
    attachments = TabyinSubmissionAttachmentInputSerializer(
        many=True,
        required=False,
        allow_empty=True,
    )

    def validate_attachments(self, value: list[dict]) -> list[dict]:
        """سقفِ تعداد پیوست — مشترک با مسیرِ ساخت."""
        return validate_attachments_count(value)

    def validate(self, attrs: dict) -> dict:
        """دست‌کم یک تغییر باید ارسال شود و پیوست‌ها تک‌نوع بمانند."""
        if not attrs:
            raise serializers.ValidationError(
                "چیزی برای ویرایش ارسال نشده؛ دست‌کم یکی از عنوان، شرح یا پیوست‌ها را بفرست."
            )
        attachments = attrs.get("attachments")
        if attachments is not None:
            enforce_homogeneous_attachments(attachments)
        return attrs


class UserTabyinSubmissionAttachmentSerializer(TabyinAttachmentSerializer):
    """
    پیوست در دید «روایت‌های من» و صف بررسی ادمین — علاوه بر فیلدهای عمومی،
    نشانی اصلیِ پیش از آینه‌سازی و وضعیت آن را هم نشان می‌دهد تا مالکِ
    محتوا/ادمین بفهمد فایل کجا میزبانی می‌شود.
    """

    mirror_status_display = serializers.CharField(
        source="get_mirror_status_display",
        read_only=True,
    )

    class Meta(TabyinAttachmentSerializer.Meta):
        fields = [
            *TabyinAttachmentSerializer.Meta.fields,
            "origin_url",
            "mirror_status",
            "mirror_status_display",
            "mime_type",
        ]


# ============================================================
# User Media Upload Serializers
# ============================================================


class TabyinMediaUploadInputSerializer(serializers.Serializer):
    """Input serializer for the direct media-upload endpoint (multipart)."""

    file = serializers.FileField()


class TabyinMediaUploadResultSerializer(serializers.Serializer):
    """نتیجه‌ی آپلود موفق — همان چیزی که استودیو برای ساختِ ردیف پیوست لازم دارد."""

    url = serializers.CharField()
    name = serializers.CharField()
    media_type = serializers.ChoiceField(choices=MediaType.choices)
    mime_type = serializers.CharField(allow_blank=True)
    original_name = serializers.CharField(allow_blank=True)
    size = serializers.CharField(allow_blank=True)
    duration = serializers.IntegerField()
    file_size = serializers.IntegerField()
    size_bytes = serializers.IntegerField()


class TabyinUploadConfigSerializer(serializers.Serializer):
    """قرارداد عمومیِ آپلود — سقف حجم و فرمت‌های مجاز هر نوع رسانه."""

    max_attachments = serializers.IntegerField()
    extensions = serializers.DictField(child=serializers.ListField(child=serializers.CharField()))
    max_mb = serializers.DictField(child=serializers.IntegerField())
    labels = serializers.DictField(child=serializers.CharField())


class UserTabyinSubmissionListSerializer(serializers.ModelSerializer):
    """List serializer for a user's own submitted contents."""

    attachments_count = serializers.IntegerField(source="attachments.count", read_only=True)

    class Meta:
        model = TabyinContent
        fields = [
            "id",
            "external_id",
            "title",
            "submission_status",
            "admin_note",
            "attachments_count",
            "created_at",
            "reviewed_at",
        ]


class UserTabyinSubmissionDetailSerializer(serializers.ModelSerializer):
    """Detail serializer for a user's own submitted content."""

    attachments = UserTabyinSubmissionAttachmentSerializer(many=True, read_only=True)

    class Meta:
        model = TabyinContent
        fields = [
            "id",
            "external_id",
            "title",
            "description",
            "submission_status",
            "admin_note",
            "attachments",
            "created_at",
            "updated_at",
            "reviewed_at",
        ]


class AdminTabyinSubmissionReviewSerializer(serializers.Serializer):
    """Input serializer for admin approval/rejection of user submissions."""

    admin_note = serializers.CharField(required=False, allow_blank=True)


class AdminTabyinSubmissionQueueSerializer(serializers.ModelSerializer):
    """Admin serializer for reviewing user-submitted content."""

    submitted_by_email = serializers.EmailField(source="submitted_by.email", read_only=True)
    attachments = UserTabyinSubmissionAttachmentSerializer(many=True, read_only=True)

    class Meta:
        model = TabyinContent
        fields = [
            "id",
            "external_id",
            "title",
            "description",
            "submission_status",
            "submitted_by_id",
            "submitted_by_email",
            "admin_note",
            "attachments",
            "created_at",
            "reviewed_at",
        ]

"""
Serializers اپ R4J.

پنج دسته serializer داریم:

1. Public     — برای نمایش به کاربر عمومی با visibility filter
2. Admin      — برای نمایش کامل (شامل فیلدهای حساس) به ادمین
3. Input      — برای create/update از ادمین
4. Report     — برای submit، نمایش user، نمایش admin و review
5. Bounty     — برای set/update، نمایش user، نمایش admin و cancel

اصول طراحی:
- public serializer از visibility map استفاده می‌کند تا فیلدهای حساس
  بسته به تنظیمات per-criminal hide شوند.
- admin serializer هیچ فیلتری اعمال نمی‌کند.
- input serializerها در مرز validation سختگیر هستند.
- report serializerها state machine را در validation enforce می‌کنند.
- bounty serializerها amount validation را در serializer layer اعمال می‌کنند.
- submit report از هر دو حالت JSON و multipart/form-data پشتیبانی می‌کند:
    * در JSON: field_changes به‌صورت list ارسال می‌شود.
    * در multipart: field_changes به‌صورت JSON string ارسال می‌شود.
"""

from __future__ import annotations

import json
from typing import Any

from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers

from .choices import (
    CriminalAttachmentKind,
    Gender,
    ReportFieldChangeStatus,
    SocialPlatform,
)
from .models import (
    R4JBounty,
    R4JCriminal,
    R4JCriminalAlias,
    R4JCriminalAttachment,
    R4JCriminalFieldVisibility,
    R4JCriminalPhone,
    R4JCriminalPhoto,
    R4JCriminalSocial,
    R4JEvidenceCustodyEvent,
    R4JReport,
    R4JReportAliasSuggestion,
    R4JReportAttachment,
    R4JReportFieldChange,
    R4JReportPhoneSuggestion,
    R4JReportSocialSuggestion,
)
from .selectors import compute_visibility_map
from .services import REPORTABLE_CRIMINAL_FIELDS
from .validators import R4J_BOUNTY_MIN_TOMAN

# ============================================================
# Nested — Public
# ============================================================


class R4JPublicPhotoSerializer(serializers.ModelSerializer):
    """نمایش عکس برای public."""

    class Meta:
        model = R4JCriminalPhoto
        fields = ("id", "image", "caption", "is_primary", "order")
        read_only_fields = fields


class R4JPublicPhoneSerializer(serializers.ModelSerializer):
    """نمایش شماره تماس public."""

    class Meta:
        model = R4JCriminalPhone
        fields = ("id", "label", "number")
        read_only_fields = fields


class R4JPublicSocialSerializer(serializers.ModelSerializer):
    """نمایش شبکه اجتماعی public."""

    class Meta:
        model = R4JCriminalSocial
        fields = ("id", "platform", "handle_or_url")
        read_only_fields = fields


class R4JPublicAttachmentSerializer(serializers.ModelSerializer):
    """نمایش سند public."""

    class Meta:
        model = R4JCriminalAttachment
        fields = ("id", "file", "title", "kind", "description")
        read_only_fields = fields


class R4JAliasSerializer(serializers.ModelSerializer):
    """نمایش نام مستعار."""

    class Meta:
        model = R4JCriminalAlias
        fields = ("id", "alias")
        read_only_fields = ("id",)


# ============================================================
# Criminal — Public
# ============================================================


class R4JPublicCriminalListSerializer(serializers.ModelSerializer):
    """نمایش لیست عمومی — حداقل اطلاعات + عکس primary + جوایز."""

    primary_photo = serializers.SerializerMethodField()

    class Meta:
        model = R4JCriminal
        fields = (
            "id",
            "slug",
            "first_name",
            "last_name",
            "country",
            "province",
            "city",
            "primary_photo",
            "total_bounty_toman",
            "bounties_count",
        )
        read_only_fields = fields

    def get_primary_photo(self, obj: R4JCriminal) -> dict[str, Any] | None:
        """دریافت عکس primary یا اولین عکس موجود."""
        photos = list(obj.photos.all())
        primary = next((p for p in photos if p.is_primary), None)
        if primary is None and photos:
            primary = photos[0]
        if primary is None:
            return None
        request = self.context.get("request")
        return {
            "id": primary.pk,
            "image": (
                request.build_absolute_uri(primary.image.url) if request else primary.image.url
            ),
        }


class R4JPublicCriminalDetailSerializer(serializers.ModelSerializer):
    """
    نمایش جزئیات عمومی با اعمال visibility map.

    فیلدهایی که visibility آن‌ها False است، None سرو می‌شوند تا
    schema یکپارچه باقی بماند.
    """

    photos = R4JPublicPhotoSerializer(many=True, read_only=True)
    phones = R4JPublicPhoneSerializer(many=True, read_only=True)
    socials = R4JPublicSocialSerializer(many=True, read_only=True)
    attachments = R4JPublicAttachmentSerializer(many=True, read_only=True)
    aliases = R4JAliasSerializer(many=True, read_only=True)

    class Meta:
        model = R4JCriminal
        fields = (
            "id",
            "slug",
            "first_name",
            "last_name",
            "national_code",
            "birth_date",
            "gender",
            "country",
            "province",
            "city",
            "description",
            "crimes_summary",
            "other_info",
            "photos",
            "phones",
            "socials",
            "attachments",
            "aliases",
            "total_bounty_toman",
            "bounties_count",
            "published_at",
        )
        read_only_fields = fields

    def to_representation(self, instance: R4JCriminal) -> dict[str, Any]:
        """اعمال visibility map روی فیلدهای حساس."""
        data = super().to_representation(instance)
        visibility = compute_visibility_map(instance)
        for field, is_public in visibility.items():
            if field in data and not is_public:
                data[field] = None
        return data


# ============================================================
# Criminal — Admin
# ============================================================


class R4JAdminPhoneSerializer(serializers.ModelSerializer):
    """نمایش کامل شماره تماس برای admin."""

    class Meta:
        model = R4JCriminalPhone
        fields = ("id", "label", "number", "is_public", "notes", "created_at")
        read_only_fields = ("id", "created_at")


class R4JAdminSocialSerializer(serializers.ModelSerializer):
    """نمایش کامل شبکه اجتماعی برای admin."""

    class Meta:
        model = R4JCriminalSocial
        fields = ("id", "platform", "handle_or_url", "is_public", "created_at")
        read_only_fields = ("id", "created_at")


class R4JAdminPhotoSerializer(serializers.ModelSerializer):
    """نمایش کامل عکس برای admin."""

    class Meta:
        model = R4JCriminalPhoto
        fields = ("id", "image", "caption", "is_primary", "order", "created_at")
        read_only_fields = ("id", "created_at")


class R4JAdminAttachmentSerializer(serializers.ModelSerializer):
    """نمایش کامل سند برای admin."""

    class Meta:
        model = R4JCriminalAttachment
        fields = (
            "id",
            "file",
            "title",
            "kind",
            "description",
            "is_public",
            "uploaded_by",
            "file_sha256",
            "file_size",
            "created_at",
        )
        read_only_fields = ("id", "uploaded_by", "created_at")


class R4JAdminFieldVisibilitySerializer(serializers.ModelSerializer):
    """نمایش تنظیمات visibility فیلد برای admin."""

    class Meta:
        model = R4JCriminalFieldVisibility
        fields = ("id", "field_name", "is_public")
        read_only_fields = ("id",)


class R4JAdminCriminalListSerializer(serializers.ModelSerializer):
    """نمایش لیست admin — شامل status flags."""

    class Meta:
        model = R4JCriminal
        fields = (
            "id",
            "slug",
            "first_name",
            "last_name",
            "country",
            "province",
            "city",
            "is_published",
            "is_active",
            "total_bounty_toman",
            "bounties_count",
            "created_at",
            "updated_at",
        )
        read_only_fields = fields


class R4JAdminCriminalDetailSerializer(serializers.ModelSerializer):
    """نمایش جزئیات admin — شامل nested resources و فیلدهای حساس."""

    photos = R4JAdminPhotoSerializer(many=True, read_only=True)
    phones = R4JAdminPhoneSerializer(many=True, read_only=True)
    socials = R4JAdminSocialSerializer(many=True, read_only=True)
    attachments = R4JAdminAttachmentSerializer(many=True, read_only=True)
    aliases = R4JAliasSerializer(many=True, read_only=True)
    field_visibility = R4JAdminFieldVisibilitySerializer(many=True, read_only=True)

    class Meta:
        model = R4JCriminal
        fields = (
            "id",
            "slug",
            "first_name",
            "last_name",
            "national_code",
            "birth_date",
            "gender",
            "country",
            "province",
            "city",
            "description",
            "crimes_summary",
            "other_info",
            "is_published",
            "is_active",
            "published_at",
            "total_bounty_toman",
            "bounties_count",
            "created_by",
            "created_at",
            "updated_at",
            "photos",
            "phones",
            "socials",
            "attachments",
            "aliases",
            "field_visibility",
        )
        read_only_fields = (
            "id",
            "slug",
            "is_published",
            "published_at",
            "total_bounty_toman",
            "bounties_count",
            "created_by",
            "created_at",
            "updated_at",
        )


# ============================================================
# Criminal — Input (Admin)
# ============================================================


class R4JCriminalCreateSerializer(serializers.Serializer):
    """ورودی ساخت پروفایل criminal توسط admin."""

    first_name = serializers.CharField(max_length=150)
    last_name = serializers.CharField(max_length=150)
    gender = serializers.ChoiceField(
        choices=Gender.choices,
        default=Gender.UNKNOWN,
        required=False,
    )
    national_code = serializers.CharField(
        max_length=10,
        required=False,
        allow_blank=True,
    )
    birth_date = serializers.DateField(required=False, allow_null=True)
    country = serializers.CharField(
        max_length=100,
        required=False,
        allow_blank=True,
    )
    province = serializers.CharField(
        max_length=100,
        required=False,
        allow_blank=True,
    )
    city = serializers.CharField(
        max_length=100,
        required=False,
        allow_blank=True,
    )
    description = serializers.CharField(required=False, allow_blank=True)
    crimes_summary = serializers.CharField(required=False, allow_blank=True)
    other_info = serializers.CharField(required=False, allow_blank=True)


class R4JCriminalUpdateSerializer(serializers.Serializer):
    """ورودی ویرایش پروفایل criminal توسط admin."""

    first_name = serializers.CharField(max_length=150, required=False)
    last_name = serializers.CharField(max_length=150, required=False)
    gender = serializers.ChoiceField(choices=Gender.choices, required=False)
    national_code = serializers.CharField(
        max_length=10,
        required=False,
        allow_blank=True,
    )
    birth_date = serializers.DateField(required=False, allow_null=True)
    country = serializers.CharField(
        max_length=100,
        required=False,
        allow_blank=True,
    )
    province = serializers.CharField(
        max_length=100,
        required=False,
        allow_blank=True,
    )
    city = serializers.CharField(
        max_length=100,
        required=False,
        allow_blank=True,
    )
    description = serializers.CharField(required=False, allow_blank=True)
    crimes_summary = serializers.CharField(required=False, allow_blank=True)
    other_info = serializers.CharField(required=False, allow_blank=True)


# ============================================================
# Nested — Input (Admin)
# ============================================================


class R4JAliasCreateSerializer(serializers.Serializer):
    """ورودی افزودن نام مستعار."""

    alias = serializers.CharField(max_length=200)


class R4JPhoneCreateSerializer(serializers.Serializer):
    """ورودی افزودن شماره تماس."""

    number = serializers.CharField(max_length=30)
    label = serializers.CharField(max_length=50, required=False, allow_blank=True)
    is_public = serializers.BooleanField(required=False, default=False)
    notes = serializers.CharField(required=False, allow_blank=True)


class R4JPhoneUpdateSerializer(serializers.Serializer):
    """ورودی ویرایش شماره تماس."""

    number = serializers.CharField(max_length=30, required=False)
    label = serializers.CharField(max_length=50, required=False, allow_blank=True)
    is_public = serializers.BooleanField(required=False)
    notes = serializers.CharField(required=False, allow_blank=True)


class R4JSocialCreateSerializer(serializers.Serializer):
    """ورودی افزودن شبکه اجتماعی."""

    platform = serializers.ChoiceField(choices=SocialPlatform.choices)
    handle_or_url = serializers.CharField(max_length=255)
    is_public = serializers.BooleanField(required=False, default=True)


class R4JSocialUpdateSerializer(serializers.Serializer):
    """ورودی ویرایش شبکه اجتماعی."""

    platform = serializers.ChoiceField(choices=SocialPlatform.choices, required=False)
    handle_or_url = serializers.CharField(max_length=255, required=False)
    is_public = serializers.BooleanField(required=False)


class R4JPhotoCreateSerializer(serializers.Serializer):
    """ورودی آپلود عکس."""

    image = serializers.ImageField()
    caption = serializers.CharField(max_length=255, required=False, allow_blank=True)
    is_primary = serializers.BooleanField(required=False, default=False)
    order = serializers.IntegerField(required=False, default=0)


class R4JAttachmentCreateSerializer(serializers.Serializer):
    """ورودی آپلود سند."""

    file = serializers.FileField()
    title = serializers.CharField(max_length=255)
    kind = serializers.ChoiceField(
        choices=CriminalAttachmentKind.choices,
        default=CriminalAttachmentKind.DOCUMENT,
        required=False,
    )
    description = serializers.CharField(required=False, allow_blank=True)
    is_public = serializers.BooleanField(required=False, default=False)


class R4JFieldVisibilityUpsertSerializer(serializers.Serializer):
    """ورودی upsert تنظیمات visibility."""

    field_name = serializers.CharField(max_length=50)
    is_public = serializers.BooleanField()


# ============================================================
# Report — nested output
# ============================================================


class R4JReportFieldChangeSerializer(serializers.ModelSerializer):
    """نمایش یک پیشنهاد تغییر فیلد در گزارش."""

    class Meta:
        model = R4JReportFieldChange
        fields = (
            "id",
            "field_name",
            "suggested_value",
            "current_value_snapshot",
            "status",
            "admin_note",
        )
        read_only_fields = fields


class R4JReportAliasSuggestionSerializer(serializers.ModelSerializer):
    """نمایش پیشنهاد نام مستعار در گزارش."""

    class Meta:
        model = R4JReportAliasSuggestion
        fields = ("id", "alias", "status", "admin_note", "applied_alias")
        read_only_fields = fields


class R4JReportPhoneSuggestionSerializer(serializers.ModelSerializer):
    """نمایش پیشنهاد شماره تماس در گزارش."""

    class Meta:
        model = R4JReportPhoneSuggestion
        fields = (
            "id",
            "label",
            "number",
            "is_public",
            "notes",
            "status",
            "admin_note",
            "applied_phone",
        )
        read_only_fields = fields


class R4JReportSocialSuggestionSerializer(serializers.ModelSerializer):
    """نمایش پیشنهاد شبکه اجتماعی در گزارش."""

    class Meta:
        model = R4JReportSocialSuggestion
        fields = (
            "id",
            "platform",
            "handle_or_url",
            "is_public",
            "status",
            "admin_note",
            "applied_social",
        )
        read_only_fields = fields


class R4JReportAttachmentSerializer(serializers.ModelSerializer):
    """نمایش ضمیمه گزارش."""

    class Meta:
        model = R4JReportAttachment
        fields = (
            "id",
            "file",
            "title",
            "kind",
            "status",
            "admin_note",
            "promoted_criminal_attachment",
        )
        read_only_fields = fields


# ============================================================
# Report — output (user scope)
# ============================================================


class R4JUserReportListSerializer(serializers.ModelSerializer):
    """
    نمایش لیست گزارشات برای کاربر — اطلاعات خلاصه.

    criminal نام نمایش داده می‌شود بدون nested data.
    """

    criminal_name = serializers.SerializerMethodField()

    class Meta:
        model = R4JReport
        fields = (
            "id",
            "criminal_id",
            "criminal_name",
            "status",
            "notes",
            "created_at",
            "updated_at",
        )
        read_only_fields = fields

    def get_criminal_name(self, obj: R4JReport) -> str:
        """نام کامل مجرم."""
        return f"{obj.criminal.first_name} {obj.criminal.last_name}".strip()


class R4JUserReportDetailSerializer(serializers.ModelSerializer):
    """نمایش جزئیات کامل یک گزارش برای کاربر — شامل field_changes و attachments."""

    criminal_name = serializers.SerializerMethodField()
    field_changes = R4JReportFieldChangeSerializer(many=True, read_only=True)
    alias_suggestions = R4JReportAliasSuggestionSerializer(many=True, read_only=True)
    phone_suggestions = R4JReportPhoneSuggestionSerializer(many=True, read_only=True)
    social_suggestions = R4JReportSocialSuggestionSerializer(many=True, read_only=True)
    attachments = R4JReportAttachmentSerializer(many=True, read_only=True)

    class Meta:
        model = R4JReport
        fields = (
            "id",
            "criminal_id",
            "criminal_name",
            "notes",
            "status",
            "admin_note",
            "field_changes",
            "alias_suggestions",
            "phone_suggestions",
            "social_suggestions",
            "attachments",
            "cancel_requested_at",
            "canceled_at",
            "created_at",
            "updated_at",
        )
        read_only_fields = fields

    def get_criminal_name(self, obj: R4JReport) -> str:
        """نام کامل مجرم."""
        return f"{obj.criminal.first_name} {obj.criminal.last_name}".strip()


# ============================================================
# Report — output (admin scope)
# ============================================================


class R4JAdminReportListSerializer(serializers.ModelSerializer):
    """نمایش لیست گزارشات برای admin — شامل submitted_by info."""

    criminal_name = serializers.SerializerMethodField()
    submitted_by_email = serializers.SerializerMethodField()

    class Meta:
        model = R4JReport
        fields = (
            "id",
            "criminal_id",
            "criminal_name",
            "submitted_by_id",
            "submitted_by_email",
            "status",
            "created_at",
            "updated_at",
        )
        read_only_fields = fields

    def get_criminal_name(self, obj: R4JReport) -> str:
        """نام کامل مجرم."""
        return f"{obj.criminal.first_name} {obj.criminal.last_name}".strip()

    def get_submitted_by_email(self, obj: R4JReport) -> str | None:
        """ایمیل گزارش‌دهنده."""
        return getattr(obj.submitted_by, "email", None)


class R4JAdminReportDetailSerializer(serializers.ModelSerializer):
    """نمایش جزئیات کامل گزارش برای admin — شامل تمام nested data."""

    criminal_name = serializers.SerializerMethodField()
    submitted_by_email = serializers.SerializerMethodField()
    reviewed_by_email = serializers.SerializerMethodField()
    field_changes = R4JReportFieldChangeSerializer(many=True, read_only=True)
    alias_suggestions = R4JReportAliasSuggestionSerializer(many=True, read_only=True)
    phone_suggestions = R4JReportPhoneSuggestionSerializer(many=True, read_only=True)
    social_suggestions = R4JReportSocialSuggestionSerializer(many=True, read_only=True)
    attachments = R4JReportAttachmentSerializer(many=True, read_only=True)

    class Meta:
        model = R4JReport
        fields = (
            "id",
            "criminal_id",
            "criminal_name",
            "submitted_by_id",
            "submitted_by_email",
            "notes",
            "status",
            "admin_note",
            "reviewed_by_id",
            "reviewed_by_email",
            "reviewed_at",
            "field_changes",
            "alias_suggestions",
            "phone_suggestions",
            "social_suggestions",
            "attachments",
            "cancel_requested_at",
            "canceled_at",
            "created_at",
            "updated_at",
        )
        read_only_fields = fields

    def get_criminal_name(self, obj: R4JReport) -> str:
        """نام کامل مجرم."""
        return f"{obj.criminal.first_name} {obj.criminal.last_name}".strip()

    def get_submitted_by_email(self, obj: R4JReport) -> str | None:
        """ایمیل گزارش‌دهنده."""
        return getattr(obj.submitted_by, "email", None)

    def get_reviewed_by_email(self, obj: R4JReport) -> str | None:
        """ایمیل بررسی‌کننده."""
        return getattr(obj.reviewed_by, "email", None) if obj.reviewed_by else None


# ============================================================
# Report — Input (User)
# ============================================================


class R4JReportFieldChangeInputSerializer(serializers.Serializer):
    """
    ورودی یک پیشنهاد تغییر فیلد در submit report.

    اعتبارسنجی field_name در اینجا انجام می‌شود تا validation error
    قبل از رسیدن به service layer برگردد.
    """

    field_name = serializers.CharField(max_length=100)
    suggested_value = serializers.CharField()

    def validate_field_name(self, value: str) -> str:
        """فقط فیلدهای مجاز قابل گزارش هستند."""
        if value not in REPORTABLE_CRIMINAL_FIELDS:
            raise serializers.ValidationError(
                f"فیلد '{value}' از طریق گزارش قابل تغییر نیست. "
                f"فیلدهای مجاز: {', '.join(sorted(REPORTABLE_CRIMINAL_FIELDS))}",
            )
        return value


class R4JReportAliasSuggestionInputSerializer(serializers.Serializer):
    """ورودی پیشنهاد نام مستعار در گزارش کاربر."""

    alias = serializers.CharField(max_length=200, trim_whitespace=True)


class R4JReportPhoneSuggestionInputSerializer(serializers.Serializer):
    """ورودی پیشنهاد شماره تماس در گزارش کاربر."""

    label = serializers.CharField(max_length=50, required=False, allow_blank=True, default="")
    number = serializers.CharField(max_length=30, trim_whitespace=True)
    is_public = serializers.BooleanField(required=False, default=False)
    notes = serializers.CharField(required=False, allow_blank=True, default="")


class R4JReportSocialSuggestionInputSerializer(serializers.Serializer):
    """ورودی پیشنهاد شبکه اجتماعی در گزارش کاربر."""

    platform = serializers.ChoiceField(choices=SocialPlatform.choices)
    handle_or_url = serializers.CharField(max_length=255, trim_whitespace=True)
    is_public = serializers.BooleanField(required=False, default=True)


class R4JFlexibleTypedListField(serializers.Field):
    """JSON-or-list input field for typed report suggestion arrays."""

    default_error_messages = {
        "invalid_json": "این فیلد باید یک JSON string معتبر باشد.",
        "invalid_type": "این فیلد باید یک آرایه باشد.",
    }

    def __init__(self, *, child_serializer_class: type[serializers.Serializer], **kwargs):
        self.child_serializer_class = child_serializer_class
        super().__init__(**kwargs)

    def to_internal_value(self, data: Any) -> list[dict[str, Any]]:
        if data in (None, "", [], ()):
            return []
        parsed = data
        if isinstance(data, str):
            stripped = data.strip()
            if not stripped or stripped == "[]":
                return []
            try:
                parsed = json.loads(stripped)
            except (json.JSONDecodeError, ValueError):
                raise serializers.ValidationError(self.error_messages["invalid_json"]) from None
        if not isinstance(parsed, list):
            raise serializers.ValidationError(self.error_messages["invalid_type"])
        nested = self.child_serializer_class(data=parsed, many=True)
        nested.is_valid(raise_exception=True)
        return nested.validated_data

    def to_representation(self, value: Any) -> Any:
        return value


@extend_schema_field(R4JReportAliasSuggestionInputSerializer(many=True))
class R4JFlexibleAliasSuggestionsField(R4JFlexibleTypedListField):
    """Schema-aware flexible field for alias suggestions."""

    def __init__(self, **kwargs):
        super().__init__(child_serializer_class=R4JReportAliasSuggestionInputSerializer, **kwargs)


@extend_schema_field(R4JReportPhoneSuggestionInputSerializer(many=True))
class R4JFlexiblePhoneSuggestionsField(R4JFlexibleTypedListField):
    """Schema-aware flexible field for phone suggestions."""

    def __init__(self, **kwargs):
        super().__init__(child_serializer_class=R4JReportPhoneSuggestionInputSerializer, **kwargs)


@extend_schema_field(R4JReportSocialSuggestionInputSerializer(many=True))
class R4JFlexibleSocialSuggestionsField(R4JFlexibleTypedListField):
    """Schema-aware flexible field for social suggestions."""

    def __init__(self, **kwargs):
        super().__init__(child_serializer_class=R4JReportSocialSuggestionInputSerializer, **kwargs)


@extend_schema_field(R4JReportFieldChangeInputSerializer(many=True))
class R4JFlexibleReportFieldChangesField(serializers.Field):
    """
    فیلد انعطاف‌پذیر برای `field_changes`.

    این فیلد هر دو حالت زیر را پشتیبانی می‌کند:
    - JSON request: لیست واقعی از objectها
    - multipart request: JSON string از همان لیست

    خروجی نهایی همیشه یک list[dict] validated خواهد بود.

    Schema:
    - به‌طور صریح به drf-spectacular اعلام می‌شود که این فیلد
      از نظر OpenAPI معادل لیستی از R4JReportFieldChangeInputSerializer است.
    """

    default_error_messages = {
        "invalid_json": "field_changes باید یک JSON string معتبر باشد.",
        "invalid_type": "field_changes باید یک آرایه باشد.",
        "invalid_item": "هر آیتم در field_changes باید یک object باشد.",
        "missing_keys": "هر field_change باید دارای field_name و suggested_value باشد.",
    }

    def to_internal_value(self, data: Any) -> list[dict[str, str]]:
        """
        تبدیل ورودی خام به لیست معتبر field changeها.

        Args:
            data: ورودی خام از request.data

        Returns:
            لیست validated از field changeها.
        """
        if data in (None, "", [], ()):
            return []

        parsed = data

        if isinstance(data, str):
            stripped = data.strip()
            if not stripped or stripped == "[]":
                return []
            try:
                parsed = json.loads(stripped)
            except (json.JSONDecodeError, ValueError):
                raise serializers.ValidationError(
                    self.error_messages["invalid_json"],
                ) from None

        if not isinstance(parsed, list):
            raise serializers.ValidationError(self.error_messages["invalid_type"])

        for item in parsed:
            if not isinstance(item, dict):
                raise serializers.ValidationError(self.error_messages["invalid_item"])
            if "field_name" not in item or "suggested_value" not in item:
                raise serializers.ValidationError(self.error_messages["missing_keys"])

        nested = R4JReportFieldChangeInputSerializer(data=parsed, many=True)
        nested.is_valid(raise_exception=True)
        return nested.validated_data

    def to_representation(self, value: Any) -> Any:
        """بازنمایی خروجی بدون تغییر."""
        return value


class R4JReportSubmitSerializer(serializers.Serializer):
    """
    ورودی submit گزارش توسط کاربر.

    پشتیبانی از دو حالت:
    1. JSON (application/json):
       - `field_changes` به‌صورت list واقعی
    2. Multipart (multipart/form-data):
       - `notes` به‌صورت string
       - `field_changes` به‌صورت JSON string
       - `attachments` از request.FILES در view خوانده می‌شود

    حداقل یک field_change یا یک notes غیر خالی لازم است.
    """

    notes = serializers.CharField(required=False, allow_blank=True, default="")
    field_changes = R4JFlexibleReportFieldChangesField(
        required=False,
        default=list,
        help_text=(
            "در JSON: لیست مستقیم field changeها.\n"
            "در multipart: JSON string از همان لیست.\n"
            'مثال: [{"field_name": "city", "suggested_value": "Tehran"}]'
        ),
    )

    alias_suggestions = R4JFlexibleAliasSuggestionsField(required=False, default=list)
    phone_suggestions = R4JFlexiblePhoneSuggestionsField(required=False, default=list)
    social_suggestions = R4JFlexibleSocialSuggestionsField(required=False, default=list)

    def validate(self, attrs: dict[str, Any]) -> dict[str, Any]:
        """حداقل یک field_change یا یادداشت غیر خالی لازم است."""
        notes = attrs.get("notes", "").strip()
        field_changes = attrs.get("field_changes", [])
        alias_suggestions = attrs.get("alias_suggestions", [])
        phone_suggestions = attrs.get("phone_suggestions", [])
        social_suggestions = attrs.get("social_suggestions", [])

        if not any(
            [notes, field_changes, alias_suggestions, phone_suggestions, social_suggestions]
        ):
            raise serializers.ValidationError(
                "گزارش باید حداقل یک یادداشت، پیشنهاد اصلاح فیلد، نام مستعار، شماره تماس یا شبکه اجتماعی داشته باشد.",
            )

        return attrs


# ============================================================
# Report — Input (Admin)
# ============================================================


class R4JFieldDecisionSerializer(serializers.Serializer):
    """
    تصمیم ادمین برای یک field_change.

    status فقط approved یا rejected می‌تواند باشد —
    ادمین نمی‌تواند وضعیت را در pending نگه دارد.
    """

    field_change_id = serializers.IntegerField()
    status = serializers.ChoiceField(
        choices=[
            ReportFieldChangeStatus.APPROVED,
            ReportFieldChangeStatus.REJECTED,
        ],
    )
    admin_note = serializers.CharField(
        required=False,
        allow_blank=True,
        default="",
    )


class R4JReportReviewSerializer(serializers.Serializer):
    """
    ورودی review گزارش توسط ادمین.

    field_decisions اختیاری است — اگر گزارش بدون field_change باشد.
    """

    field_decisions = R4JFieldDecisionSerializer(many=True, required=False)
    alias_decisions = serializers.ListField(child=serializers.DictField(), required=False)
    phone_decisions = serializers.ListField(child=serializers.DictField(), required=False)
    social_decisions = serializers.ListField(child=serializers.DictField(), required=False)
    attachment_decisions = serializers.ListField(child=serializers.DictField(), required=False)
    admin_note = serializers.CharField(
        required=False,
        allow_blank=True,
        default="",
    )


class R4JReportCancelActionSerializer(serializers.Serializer):
    """ورودی approve/reject cancel — فقط admin_note اختیاری."""

    admin_note = serializers.CharField(
        required=False,
        allow_blank=True,
        default="",
    )


# ============================================================
# Bounty — output (user scope)
# ============================================================


class R4JUserBountySerializer(serializers.ModelSerializer):
    """
    نمایش bounty برای کاربر — شامل اطلاعات criminal.

    کاربر فقط bountyهای خودش را می‌بیند.
    فیلدهای admin مثل admin_note در این serializer نیستند.
    """

    criminal_name = serializers.SerializerMethodField()
    criminal_slug = serializers.SerializerMethodField()

    class Meta:
        model = R4JBounty
        fields = (
            "id",
            "criminal_id",
            "criminal_name",
            "criminal_slug",
            "amount_toman",
            "status",
            "cancel_requested_at",
            "canceled_at",
            "created_at",
            "updated_at",
        )
        read_only_fields = fields

    def get_criminal_name(self, obj: R4JBounty) -> str:
        """نام کامل مجرم."""
        return f"{obj.criminal.first_name} {obj.criminal.last_name}".strip()

    def get_criminal_slug(self, obj: R4JBounty) -> str:
        """slug مجرم برای لینک‌دهی."""
        return obj.criminal.slug


# ============================================================
# Bounty — output (admin scope)
# ============================================================


class R4JAdminBountyListSerializer(serializers.ModelSerializer):
    """نمایش لیست bountyها برای admin — شامل user و criminal info."""

    criminal_name = serializers.SerializerMethodField()
    user_email = serializers.SerializerMethodField()

    class Meta:
        model = R4JBounty
        fields = (
            "id",
            "criminal_id",
            "criminal_name",
            "user_id",
            "user_email",
            "amount_toman",
            "status",
            "created_at",
            "updated_at",
        )
        read_only_fields = fields

    def get_criminal_name(self, obj: R4JBounty) -> str:
        """نام کامل مجرم."""
        return f"{obj.criminal.first_name} {obj.criminal.last_name}".strip()

    def get_user_email(self, obj: R4JBounty) -> str | None:
        """ایمیل کاربر تعیین‌کننده جایزه."""
        return getattr(obj.user, "email", None)


class R4JAdminBountyDetailSerializer(serializers.ModelSerializer):
    """نمایش جزئیات کامل bounty برای admin — شامل admin_note و timestamps."""

    criminal_name = serializers.SerializerMethodField()
    user_email = serializers.SerializerMethodField()

    class Meta:
        model = R4JBounty
        fields = (
            "id",
            "criminal_id",
            "criminal_name",
            "user_id",
            "user_email",
            "amount_toman",
            "status",
            "admin_note",
            "cancel_requested_at",
            "canceled_at",
            "created_at",
            "updated_at",
        )
        read_only_fields = fields

    def get_criminal_name(self, obj: R4JBounty) -> str:
        """نام کامل مجرم."""
        return f"{obj.criminal.first_name} {obj.criminal.last_name}".strip()

    def get_user_email(self, obj: R4JBounty) -> str | None:
        """ایمیل کاربر تعیین‌کننده جایزه."""
        return getattr(obj.user, "email", None)


# ============================================================
# Bounty — Input (User)
# ============================================================


class R4JBountySetSerializer(serializers.Serializer):
    """
    ورودی set/update bounty توسط کاربر.

    amount_toman در serializer layer validate می‌شود تا error message
    قبل از رسیدن به service layer برگردد.

    حداقل مبلغ مجاز: R4J_BOUNTY_MIN_TOMAN تومان.
    """

    amount_toman = serializers.IntegerField(
        min_value=R4J_BOUNTY_MIN_TOMAN,
        error_messages={
            "min_value": (f"حداقل مبلغ جایزه {R4J_BOUNTY_MIN_TOMAN:,} تومان است."),
            "invalid": "مبلغ جایزه باید یک عدد صحیح باشد.",
        },
    )


# ============================================================
# Bounty — Input (Admin)
# ============================================================


class R4JBountyCancelActionSerializer(serializers.Serializer):
    """ورودی approve/reject cancel bounty توسط ادمین — فقط admin_note اختیاری."""

    admin_note = serializers.CharField(
        required=False,
        allow_blank=True,
        default="",
    )


class R4JEvidenceCustodyEventSerializer(serializers.ModelSerializer):
    """Read serializer for R4J evidence chain-of-custody events."""

    actor_email = serializers.EmailField(source="actor.email", read_only=True, allow_null=True)
    event_type_display = serializers.CharField(source="get_event_type_display", read_only=True)

    class Meta:
        model = R4JEvidenceCustodyEvent
        fields = (
            "id",
            "criminal_attachment",
            "report_attachment",
            "event_type",
            "event_type_display",
            "actor",
            "actor_email",
            "file_sha256",
            "note",
            "metadata",
            "created_at",
        )
        read_only_fields = fields


class R4JEvidenceCustodyReviewSerializer(serializers.Serializer):
    """Input serializer for appending custody review/transfer/reject events."""

    event_type = serializers.ChoiceField(choices=("reviewed", "transferred", "rejected"))
    note = serializers.CharField(required=False, allow_blank=True, default="")

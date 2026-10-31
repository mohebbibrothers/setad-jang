"""Serializerهای دیوار مهربانی — عمومی، کاربر و ادمین.

اصل خانهٔ پروژه: سریالایزر نازک است؛ قواعد سیاست در ``services``/
``validators`` زندگی می‌کند. تنها استثنا، خروجیِ کانال‌های تماس است که از
``listing.channel_payload()`` (منبع یکتا) خوانده می‌شود.
"""

from __future__ import annotations

import re

from rest_framework import serializers

from apps.kindness_wall.choices import OfferStatus
from apps.kindness_wall.models import (
    KindnessCategory,
    KindnessListing,
    KindnessListingImage,
    KindnessOffer,
)

_WS_RE = re.compile(r"\s+")
#: سجاوندی انتهایی که بعد از برشِ کارت باید ریخته شود (فارسی+لاتین).
_TRAILING_PUNCT_RE = re.compile(r"[\s،.؛,:]+$")


def _excerpt(text: str, limit: int = 160) -> str:
    """چکیدهٔ تمیز برای کارت‌ها: فاصله‌ها جمع و برش با سه‌نقطه."""
    cleaned = _WS_RE.sub(" ", (text or "")).strip()
    if len(cleaned) <= limit:
        return cleaned
    return _TRAILING_PUNCT_RE.sub("", cleaned[:limit]) + "…"


class KindnessContactChannelSerializer(serializers.Serializer):
    """ساختار یک راه ارتباطی در پاسخ API."""

    kind = serializers.CharField(max_length=20)
    label = serializers.CharField(max_length=40)
    value = serializers.CharField(max_length=64)
    link = serializers.CharField(max_length=120, allow_blank=True)


class KindnessCategorySerializer(serializers.ModelSerializer):
    """دسته با شمارندهٔ زندهٔ آگهی‌های جاری."""

    open_listings_count = serializers.SerializerMethodField()

    class Meta:
        model = KindnessCategory
        fields = ("id", "title", "slug", "description", "icon", "order", "open_listings_count")
        read_only_fields = fields

    def get_open_listings_count(self, obj: KindnessCategory) -> int:
        """از annotation سلکتور خوانده می‌شود؛ بدون آن صفر امن است."""
        return int(getattr(obj, "open_listings_count", 0) or 0)


class KindnessCategoryInputSerializer(serializers.ModelSerializer):
    """ورودی ساخت/ویرایش دسته توسط ادمین."""

    class Meta:
        model = KindnessCategory
        fields = ("title", "description", "icon", "order")

    def validate_title(self, value: str) -> str:
        """عنوان حداقل ۲ نویسه."""
        value = (value or "").strip()
        if len(value) < 2:
            raise serializers.ValidationError("عنوان دسته باید حداقل ۲ نویسه باشد.")
        return value


class KindnessListingImageSerializer(serializers.ModelSerializer):
    """تصویر آگهی."""

    class Meta:
        model = KindnessListingImage
        fields = ("id", "image", "alt_text", "is_cover", "order")
        read_only_fields = fields


class KindnessListingListSerializer(serializers.ModelSerializer):
    """کارت آگهی روی دیوار — بدون هیچ اطلاعات تماس (ضد اسکرپینگ)."""

    category = KindnessCategorySerializer(read_only=True)
    urgency_display = serializers.CharField(source="get_urgency_display", read_only=True)
    excerpt = serializers.SerializerMethodField()
    cover_url = serializers.SerializerMethodField()
    days_left = serializers.IntegerField(read_only=True)
    open_offers_count = serializers.IntegerField(read_only=True, required=False)
    is_nationwide = serializers.SerializerMethodField()

    class Meta:
        model = KindnessListing
        fields = (
            "id",
            "slug",
            "title",
            "excerpt",
            "category",
            "urgency",
            "urgency_display",
            "is_featured",
            "quantity",
            "unit",
            "province",
            "city",
            "locality",
            "is_nationwide",
            "view_count",
            "open_offers_count",
            "cover_url",
            "days_left",
            "published_at",
        )
        read_only_fields = fields

    def get_is_nationwide(self, obj: KindnessListing) -> bool:
        """آگهیِ «سراسر کشور» = بدونِ استان؛ در فیلترِ همهٔ استان‌ها هم می‌آید."""
        return not (obj.province or "").strip()

    def get_excerpt(self, obj: KindnessListing) -> str:
        """چکیدهٔ توضیحات برای کارت."""
        return _excerpt(obj.description)

    def get_cover_url(self, obj: KindnessListing) -> str | None:
        """URL کاور از مجموعهٔ prefetch‌شده (بدون کوئری اضافه)."""
        for image in obj.images.all():
            if image.image:
                return image.image.url
        return None


class KindnessListingDetailSerializer(KindnessListingListSerializer):
    """جزئیات عمومی آگهی: شرح کامل + راه‌های تماس + وضعیت اعلام آمادگیِ کاربر."""

    images = KindnessListingImageSerializer(many=True, read_only=True)
    contact_channels = serializers.SerializerMethodField()
    my_offer_status = serializers.SerializerMethodField()
    can_offer = serializers.SerializerMethodField()

    class Meta(KindnessListingListSerializer.Meta):
        fields = (
            *KindnessListingListSerializer.Meta.fields,
            "description",
            "beneficiary_name",
            "contact_note",
            "expires_at",
            "images",
            "contact_channels",
            "my_offer_status",
            "can_offer",
        )
        read_only_fields = fields

    def get_contact_channels(self, obj: KindnessListing) -> list[dict[str, str]]:
        """کانال‌های پرشده — همان چیزی که سیاست می‌گوید: «درج‌شده در آگهی»."""
        return obj.channel_payload()

    def get_my_offer_status(self, obj: KindnessListing) -> str | None:
        """وضعیت اعلام آمادگیِ کاربر جاری (None = هنوز ثبت نکرده)."""
        offer = self.context.get("my_offer")
        return offer.status if offer is not None else None

    def get_can_offer(self, obj: KindnessListing) -> bool:
        """دکمهٔ «می‌تونم کمک کنم» فقط برای کاربر واردشده فعال است."""
        request = self.context.get("request")
        return bool(request is not None and getattr(request.user, "is_authenticated", False))


class KindnessStorySerializer(serializers.ModelSerializer):
    """ردیف بایگانی «داستان‌های مهربانی» — بدون تماس، فقط روایت شفاف."""

    category = KindnessCategorySerializer(read_only=True)
    cover_url = serializers.SerializerMethodField()

    class Meta:
        model = KindnessListing
        fields = (
            "slug",
            "title",
            "category",
            "quantity",
            "unit",
            "city",
            "fulfilled_at",
            "fulfillment_note",
            "cover_url",
        )
        read_only_fields = fields

    def get_cover_url(self, obj: KindnessListing) -> str | None:
        """URL کاور استوری از تصاویر prefetch‌شده."""
        for image in obj.images.all():
            if image.image:
                return image.image.url
        return None


class KindnessOfferSerializer(serializers.ModelSerializer):
    """اعلام آمادگی (نمای کاربر از خودِ رکوردها)."""

    listing_slug = serializers.CharField(source="listing.slug", read_only=True)
    listing_title = serializers.CharField(source="listing.title", read_only=True)
    status_display = serializers.CharField(source="get_status_display", read_only=True)

    class Meta:
        model = KindnessOffer
        fields = (
            "id",
            "listing_slug",
            "listing_title",
            "message",
            "status",
            "status_display",
            "admin_note",
            "created_at",
            "handled_at",
        )
        read_only_fields = fields


class KindnessOfferInputSerializer(serializers.Serializer):
    """ورودی اعلام آمادگی."""

    message = serializers.CharField(
        required=False,
        allow_blank=True,
        max_length=500,
        trim_whitespace=True,
    )


class KindnessOfferReviewInputSerializer(serializers.Serializer):
    """ورودی بررسی ادمین روی اعلام آمادگی."""

    status = serializers.ChoiceField(choices=[OfferStatus.CONTACTED, OfferStatus.DECLINED])
    note = serializers.CharField(required=False, allow_blank=True, max_length=240)


class KindnessFulfillInputSerializer(serializers.Serializer):
    """ورودی «برطرف شد» — یک خط روایت اختیاری برای بایگانی."""

    note = serializers.CharField(required=False, allow_blank=True, max_length=240)


class KindnessFeatureInputSerializer(serializers.Serializer):
    """ورودی ویژه/لغو ویژه."""

    featured = serializers.BooleanField(default=True)


class KindnessListingInputSerializer(serializers.ModelSerializer):
    """ساخت/ویرایش کامل آگهی توسط ادمین (REST). وضعیت‌ها فقط از اکشن‌ها."""

    class Meta:
        model = KindnessListing
        fields = (
            "category",
            "title",
            "description",
            "quantity",
            "unit",
            "urgency",
            "beneficiary_name",
            "province",
            "city",
            "contact_note",
            "contact_phone",
            "contact_bale",
            "contact_eitaa",
            "contact_telegram",
            "contact_rubika",
            "contact_instagram",
            "expires_at",
        )

    def validate_title(self, value: str) -> str:
        """حداقل ۵ نویسه — از عنوان‌های یک‌کلمه‌ایِ بی‌کیفیت جلوگیری."""
        value = (value or "").strip()
        if len(value) < 5:
            raise serializers.ValidationError("عنوان آگهی باید حداقل ۵ نویسه باشد.")
        return value

    def validate_description(self, value: str) -> str:
        """حداقل ۲۰ نویسه؛ آگهی بی‌شرح روی دیوار مهربانی معنی ندارد."""
        value = (value or "").strip()
        if len(value) < 20:
            raise serializers.ValidationError("شرح نیاز باید حداقل ۲۰ نویسه باشد.")
        return value

    def validate_quantity(self, value: int) -> int:
        """تعداد مثبت و واقع‌بینانه (سقف ۹۹۹؛ فیلد PositiveSmallInt تا ۳۲۷۶۷)."""
        if value < 1 or value > 999:
            raise serializers.ValidationError("تعداد باید بین ۱ تا ۹۹۹ باشد.")
        return value

    def validate(self, attrs: dict[str, object]) -> dict[str, object]:
        """اعتبار شکل کانال‌ها + نرمال‌سازی؛ قاعدهٔ «حداقل یکی» در اکشن انتشار است."""
        from django.core.exceptions import ValidationError

        from apps.kindness_wall.validators import normalize_channel_value, validate_channel_value

        instance = self.instance
        merged: dict[str, str] = {}
        for field, code, _label, _link in KindnessListing.channel_fields():
            raw = attrs.get(field)
            if raw is None and instance is not None:
                raw = getattr(instance, field)
            raw = (raw or "").strip()
            if raw:
                merged[field] = normalize_channel_value(kind=code, value=raw)
        errors: dict[str, str] = {}
        for field, code, label, _link in KindnessListing.channel_fields():
            value = merged.get(field)
            if not value:
                continue
            try:
                validate_channel_value(kind=code, value=value)
            except ValidationError as exc:
                errors[field] = f"{label}: {exc.messages[0]}"
        if errors:
            raise serializers.ValidationError(errors)
        attrs.update(merged)
        return attrs


class KindnessAdminListingSerializer(KindnessListingDetailSerializer):
    """نمای کامل ادمین: همهٔ فیلدهای عمومی + چرخهٔ حیات و شمارنده‌ها."""

    status_display = serializers.CharField(source="get_status_display", read_only=True)

    class Meta(KindnessListingDetailSerializer.Meta):
        fields = (
            *KindnessListingDetailSerializer.Meta.fields,
            "status",
            "status_display",
            "renew_count",
            "fulfilled_at",
            "fulfillment_note",
            "created_at",
            "updated_at",
        )
        read_only_fields = fields


class KindnessAdminOfferSerializer(KindnessOfferSerializer):
    """نمای ادمین از اعلام آمادگی با شناسهٔ آگهی و نام داوطلب."""

    listing_id = serializers.IntegerField(read_only=True)
    user_label = serializers.SerializerMethodField()

    class Meta(KindnessOfferSerializer.Meta):
        fields = (*KindnessOfferSerializer.Meta.fields, "listing_id", "user_label")
        read_only_fields = fields

    def get_user_label(self, obj: KindnessOffer) -> str:
        """نمایش انسانی داوطلب (نام کامل؛ مدل کاربر پروژه username ندارد)."""
        return getattr(obj.user, "full_name", "") or str(obj.user)


class KindnessBoardStatsSerializer(serializers.Serializer):
    """اسکیمای شمارنده‌های عمومی دیوار."""

    open_listings = serializers.IntegerField()
    urgent_listings = serializers.IntegerField()
    fulfilled_total = serializers.IntegerField()
    fulfilled_30d = serializers.IntegerField()
    volunteers_total = serializers.IntegerField()
    active_categories = serializers.IntegerField()

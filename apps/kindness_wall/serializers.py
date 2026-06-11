"""DRF serializers for Kindness Wall."""

from rest_framework import serializers

from apps.kindness_wall.models import (
    KindnessCategory,
    KindnessListing,
    KindnessListingImage,
    KindnessListingReport,
    KindnessMatch,
)


class KindnessCategorySerializer(serializers.ModelSerializer):
    """Category tree row serializer."""

    class Meta:
        model = KindnessCategory
        fields = ("id", "parent_id", "title", "slug", "description", "icon", "cover_image", "path", "depth", "order")
        read_only_fields = fields


class KindnessListingImageSerializer(serializers.ModelSerializer):
    """Listing image serializer."""

    class Meta:
        model = KindnessListingImage
        fields = ("id", "image", "caption", "alt_text", "is_cover", "order", "width", "height")
        read_only_fields = fields


class KindnessListingListSerializer(serializers.ModelSerializer):
    """Public listing card serializer; never exposes contact phone."""

    category = KindnessCategorySerializer(read_only=True)
    cover_image = serializers.SerializerMethodField()

    class Meta:
        model = KindnessListing
        fields = (
            "id",
            "slug",
            "listing_type",
            "category",
            "title",
            "province",
            "city",
            "district",
            "owner_full_name_snapshot",
            "owner_avatar_snapshot",
            "published_at",
            "expires_at",
            "view_count",
            "cover_image",
        )
        read_only_fields = fields

    def get_cover_image(self, obj: KindnessListing) -> str | None:
        """Return cover image URL if available."""
        images = list(obj.images.all())
        cover = next((image for image in images if image.is_cover), None) or (images[0] if images else None)
        return cover.image.url if cover else None


class KindnessListingDetailSerializer(KindnessListingListSerializer):
    """Public detail serializer with contact availability but without raw phone."""

    images = KindnessListingImageSerializer(many=True, read_only=True)
    contact_available = serializers.SerializerMethodField()

    class Meta(KindnessListingListSerializer.Meta):
        fields = (
            *KindnessListingListSerializer.Meta.fields,
            "description",
            "address_hint",
            "images",
            "contact_available",
        )

    def get_contact_available(self, obj: KindnessListing) -> bool:
        """Return whether contact can be revealed via dedicated endpoint."""
        return bool(obj.contact_phone_snapshot)


class KindnessMatchSerializer(serializers.ModelSerializer):
    """Serializer for smart match results."""

    target_listing = KindnessListingListSerializer(read_only=True)

    class Meta:
        model = KindnessMatch
        fields = ("id", "target_listing", "score", "score_breakdown", "reason_codes", "explanation", "status", "generated_at")
        read_only_fields = fields


class KindnessListingCreateUpdateSerializer(serializers.Serializer):
    """Input serializer for user listing create/update."""

    listing_type = serializers.ChoiceField(choices=[("need_help", "نیاز به کمک دارم"), ("offer_help", "می‌خواهم کمک کنم")], required=False)
    category_id = serializers.PrimaryKeyRelatedField(queryset=KindnessCategory.objects.all(), source="category", required=False)
    title = serializers.CharField(max_length=260, required=False)
    description = serializers.CharField(required=False)
    province = serializers.CharField(max_length=100, required=False, allow_blank=True)
    city = serializers.CharField(max_length=100, required=False, allow_blank=True)
    district = serializers.CharField(max_length=120, required=False, allow_blank=True)
    address_hint = serializers.CharField(max_length=260, required=False, allow_blank=True)
    latitude = serializers.DecimalField(max_digits=9, decimal_places=6, required=False, allow_null=True)
    longitude = serializers.DecimalField(max_digits=9, decimal_places=6, required=False, allow_null=True)

    def validate_title(self, value: str) -> str:
        """Require meaningful listing title."""
        value = value.strip()
        if len(value) < 5:
            raise serializers.ValidationError("عنوان آگهی باید حداقل ۵ کاراکتر باشد.")
        return value

    def validate_description(self, value: str) -> str:
        """Require meaningful listing description."""
        value = value.strip()
        if len(value) < 15:
            raise serializers.ValidationError("توضیحات آگهی باید حداقل ۱۵ کاراکتر باشد.")
        return value


class KindnessUserListingDetailSerializer(KindnessListingDetailSerializer):
    """Owner/admin listing serializer with workflow metadata and contact snapshot."""

    class Meta(KindnessListingDetailSerializer.Meta):
        fields = (
            *KindnessListingDetailSerializer.Meta.fields,
            "status",
            "contact_phone_snapshot",
            "admin_note",
            "rejection_reason",
            "suspension_reason",
            "contact_reveal_count",
            "bookmark_count",
            "report_count",
            "last_matched_at",
            "created_at",
            "updated_at",
        )
        read_only_fields = fields


class KindnessContactRevealSerializer(serializers.Serializer):
    """Response serializer for contact reveal endpoint."""

    phone_number = serializers.CharField()
    listing_id = serializers.IntegerField()
    owner_full_name = serializers.CharField()


class KindnessListingReportCreateSerializer(serializers.Serializer):
    """Input serializer for reporting a listing."""

    reason = serializers.ChoiceField(choices=[
        ("spam", "اسپم"),
        ("fraud", "مشکوک به سوءاستفاده"),
        ("wrong_category", "دسته‌بندی اشتباه"),
        ("inappropriate", "محتوای نامناسب"),
        ("duplicate", "تکراری"),
        ("expired", "منقضی‌شده"),
        ("contact_invalid", "شماره تماس نامعتبر"),
        ("other", "سایر"),
    ])
    description = serializers.CharField(required=False, allow_blank=True, default="")


class KindnessListingReportSerializer(serializers.ModelSerializer):
    """Report output serializer."""

    class Meta:
        model = KindnessListingReport
        fields = ("id", "listing_id", "reported_by_id", "reason", "description", "status", "reviewed_by_id", "reviewed_at", "admin_note", "created_at")
        read_only_fields = fields


class KindnessAdminReviewSerializer(serializers.Serializer):
    """Input serializer for admin review actions."""

    admin_note = serializers.CharField(required=False, allow_blank=True, default="")
    reason = serializers.CharField(required=False, allow_blank=True, default="")
    needs_edit = serializers.BooleanField(required=False, default=False)


class KindnessAdminSuspendSerializer(serializers.Serializer):
    """Input serializer for admin listing suspension."""

    reason = serializers.CharField()


class KindnessMatchActionSerializer(serializers.Serializer):
    """Input serializer for match state actions."""


class KindnessAdminAnalyticsSerializer(serializers.Serializer):
    """Admin analytics summary serializer."""

    total_listings = serializers.IntegerField()
    pending_listings = serializers.IntegerField()
    published_listings = serializers.IntegerField()
    need_help_listings = serializers.IntegerField()
    offer_help_listings = serializers.IntegerField()
    contact_reveals = serializers.IntegerField()
    active_matches = serializers.IntegerField()
    pending_reports = serializers.IntegerField()

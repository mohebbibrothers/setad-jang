"""DRF serializers for Kindness Wall."""

from rest_framework import serializers

from apps.kindness_wall.choices import DuplicateStatus, ReportStatus
from apps.kindness_wall.models import (
    KindnessBookmark,
    KindnessCategory,
    KindnessContactReveal,
    KindnessDuplicateCandidate,
    KindnessListing,
    KindnessListingImage,
    KindnessListingReport,
    KindnessMatch,
)


class KindnessCategorySerializer(serializers.ModelSerializer):
    """Category tree row serializer."""

    class Meta:
        model = KindnessCategory
        fields = (
            "id",
            "parent_id",
            "title",
            "slug",
            "description",
            "icon",
            "cover_image",
            "path",
            "depth",
            "order",
            "is_active",
            "listings_count",
            "published_listings_count",
        )
        read_only_fields = fields


class KindnessAdminCategoryInputSerializer(serializers.Serializer):
    """Admin input serializer for creating/updating tree categories."""

    parent_id = serializers.PrimaryKeyRelatedField(
        queryset=KindnessCategory.all_objects.all(),
        source="parent",
        required=False,
        allow_null=True,
    )
    title = serializers.CharField(max_length=180)
    description = serializers.CharField(required=False, allow_blank=True, default="")
    icon = serializers.CharField(max_length=80, required=False, allow_blank=True, default="")
    order = serializers.IntegerField(required=False, min_value=0)
    is_active = serializers.BooleanField(required=False)

    def validate_title(self, value: str) -> str:
        """Normalize and validate category title."""
        value = value.strip()
        if len(value) < 2:
            raise serializers.ValidationError("عنوان دسته‌بندی باید حداقل ۲ کاراکتر باشد.")
        return value


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
        cover = next((image for image in images if image.is_cover), None) or (
            images[0] if images else None
        )
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
        fields = (
            "id",
            "target_listing",
            "score",
            "score_breakdown",
            "reason_codes",
            "explanation",
            "status",
            "generated_at",
        )
        read_only_fields = fields


class KindnessAdminMatchSerializer(serializers.ModelSerializer):
    """Admin serializer exposing both sides of a generated match."""

    source_listing = KindnessListingListSerializer(read_only=True)
    target_listing = KindnessListingListSerializer(read_only=True)

    class Meta:
        model = KindnessMatch
        fields = (
            "id",
            "source_listing",
            "target_listing",
            "score",
            "score_breakdown",
            "reason_codes",
            "explanation",
            "status",
            "algorithm_version",
            "generated_at",
            "dismissed_by_id",
            "dismissed_at",
            "contacted_at",
            "created_at",
            "updated_at",
        )
        read_only_fields = fields


class KindnessListingCreateUpdateSerializer(serializers.Serializer):
    """Input serializer for user listing create/update."""

    listing_type = serializers.ChoiceField(
        choices=[("need_help", "نیاز به کمک دارم"), ("offer_help", "می‌خواهم کمک کنم")],
        required=False,
    )
    category_id = serializers.PrimaryKeyRelatedField(
        queryset=KindnessCategory.objects.all(), source="category", required=False
    )
    title = serializers.CharField(max_length=260, required=False)
    description = serializers.CharField(required=False)
    province = serializers.CharField(max_length=100, required=False, allow_blank=True)
    city = serializers.CharField(max_length=100, required=False, allow_blank=True)
    district = serializers.CharField(max_length=120, required=False, allow_blank=True)
    address_hint = serializers.CharField(max_length=260, required=False, allow_blank=True)
    latitude = serializers.DecimalField(
        max_digits=9, decimal_places=6, required=False, allow_null=True
    )
    longitude = serializers.DecimalField(
        max_digits=9, decimal_places=6, required=False, allow_null=True
    )

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
            "latitude",
            "longitude",
            "created_at",
            "updated_at",
        )
        read_only_fields = fields


class KindnessBookmarkSerializer(serializers.ModelSerializer):
    """User bookmark serializer with optimized listing card."""

    listing = KindnessListingListSerializer(read_only=True)

    class Meta:
        model = KindnessBookmark
        fields = ("id", "listing", "created_at")
        read_only_fields = fields


class KindnessContactRevealSerializer(serializers.Serializer):
    """Response serializer for contact reveal endpoint."""

    phone_number = serializers.CharField()
    listing_id = serializers.IntegerField()
    owner_full_name = serializers.CharField()


class KindnessAdminContactRevealSerializer(serializers.ModelSerializer):
    """Admin audit serializer for contact reveal rows."""

    listing_title = serializers.CharField(source="listing.title", read_only=True)
    viewer_full_name = serializers.SerializerMethodField()
    owner_full_name = serializers.SerializerMethodField()

    class Meta:
        model = KindnessContactReveal
        fields = (
            "id",
            "listing_id",
            "listing_title",
            "viewer_id",
            "viewer_full_name",
            "listing_owner_id",
            "owner_full_name",
            "phone_snapshot",
            "ip_address",
            "request_id",
            "created_at",
        )
        read_only_fields = fields

    def get_viewer_full_name(self, obj: KindnessContactReveal) -> str:
        """Return viewer display name."""
        return getattr(obj.viewer, "full_name", "") or str(obj.viewer)

    def get_owner_full_name(self, obj: KindnessContactReveal) -> str:
        """Return listing owner display name."""
        return getattr(obj.listing_owner, "full_name", "") or str(obj.listing_owner)


class KindnessListingReportCreateSerializer(serializers.Serializer):
    """Input serializer for reporting a listing."""

    reason = serializers.ChoiceField(
        choices=[
            ("spam", "اسپم"),
            ("fraud", "مشکوک به سوءاستفاده"),
            ("wrong_category", "دسته‌بندی اشتباه"),
            ("inappropriate", "محتوای نامناسب"),
            ("duplicate", "تکراری"),
            ("expired", "منقضی‌شده"),
            ("contact_invalid", "شماره تماس نامعتبر"),
            ("other", "سایر"),
        ]
    )
    description = serializers.CharField(required=False, allow_blank=True, default="")


class KindnessListingReportSerializer(serializers.ModelSerializer):
    """Report output serializer."""

    listing_title = serializers.CharField(source="listing.title", read_only=True)

    class Meta:
        model = KindnessListingReport
        fields = (
            "id",
            "listing_id",
            "listing_title",
            "reported_by_id",
            "reason",
            "description",
            "status",
            "reviewed_by_id",
            "reviewed_at",
            "admin_note",
            "created_at",
        )
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


class KindnessDuplicateReviewSerializer(serializers.Serializer):
    """Input serializer for duplicate candidate review."""

    status = serializers.CharField()
    reason = serializers.CharField(required=False, allow_blank=True, default="")

    def validate_status(self, value: str) -> str:
        """Validate duplicate review status without generating ambiguous OpenAPI enums."""
        if value not in DuplicateStatus.values:
            raise serializers.ValidationError("وضعیت بررسی تکراری بودن نامعتبر است.")
        return value


class KindnessDuplicateCandidateSerializer(serializers.ModelSerializer):
    """Admin serializer for likely duplicate listings."""

    listing = KindnessListingListSerializer(read_only=True)
    candidate_listing = KindnessListingListSerializer(read_only=True)

    class Meta:
        model = KindnessDuplicateCandidate
        fields = (
            "id",
            "listing",
            "candidate_listing",
            "score",
            "reason",
            "status",
            "created_at",
            "updated_at",
        )
        read_only_fields = fields


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
    duplicate_candidates = serializers.IntegerField()
    status_distribution = serializers.ListField(child=serializers.DictField())
    type_distribution = serializers.ListField(child=serializers.DictField())
    province_distribution = serializers.ListField(child=serializers.DictField())
    city_distribution = serializers.ListField(child=serializers.DictField())
    category_distribution = serializers.ListField(child=serializers.DictField())
    top_viewed_listings = serializers.ListField(child=serializers.DictField())
    top_revealed_listings = serializers.ListField(child=serializers.DictField())
    match_effectiveness = serializers.DictField()
    report_distribution = serializers.ListField(child=serializers.DictField())
    generated_at = serializers.DateTimeField()


class KindnessReportReviewInputSerializer(serializers.Serializer):
    """Dedicated report-review input with explicit finite states."""

    status = serializers.CharField(required=False, default=ReportStatus.REVIEWED)
    admin_note = serializers.CharField(required=False, allow_blank=True, default="")
    suspend_listing = serializers.BooleanField(required=False, default=False)

    def validate_status(self, value: str) -> str:
        """Validate report review status without ambiguous schema enum names."""
        if value not in ReportStatus.values:
            raise serializers.ValidationError("وضعیت گزارش نامعتبر است.")
        return value

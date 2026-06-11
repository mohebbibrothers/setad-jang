"""DRF serializers for Kindness Wall."""

from rest_framework import serializers

from apps.kindness_wall.models import (
    KindnessCategory,
    KindnessListing,
    KindnessListingImage,
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

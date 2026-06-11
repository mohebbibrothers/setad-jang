"""Read-side selectors for Kindness Wall."""

from __future__ import annotations

from django.db.models import Prefetch, QuerySet

from apps.kindness_wall.choices import MatchStatus
from apps.kindness_wall.models import (
    KindnessCategory,
    KindnessListing,
    KindnessListingImage,
    KindnessMatch,
)


def get_public_categories() -> QuerySet[KindnessCategory]:
    """Return active tree categories for public UI."""
    return KindnessCategory.objects.select_related("parent").order_by("depth", "order", "title")


def get_admin_categories() -> QuerySet[KindnessCategory]:
    """Return all categories for admin."""
    return KindnessCategory.all_objects.select_related("parent").order_by("depth", "order", "title")


def get_public_listings() -> QuerySet[KindnessListing]:
    """Return published listings with related data optimized."""
    return (
        KindnessListing.objects.published()
        .select_related("category", "category__parent", "owner")
        .prefetch_related(Prefetch("images", queryset=KindnessListingImage.objects.order_by("order", "id")))
    )


def get_public_listing_by_slug(slug: str) -> KindnessListing | None:
    """Return one public listing by slug."""
    return get_public_listings().filter(slug=slug).first()


def get_user_listings(*, user_id: int) -> QuerySet[KindnessListing]:
    """Return listings owned by a user."""
    return KindnessListing.objects.filter(owner_id=user_id).select_related("category").prefetch_related("images")


def get_listing_matches(*, listing: KindnessListing) -> QuerySet[KindnessMatch]:
    """Return active matches for a listing."""
    return (
        KindnessMatch.objects.filter(source_listing=listing, status=MatchStatus.ACTIVE)
        .select_related("target_listing", "target_listing__category")
        .order_by("-score", "-generated_at")
    )

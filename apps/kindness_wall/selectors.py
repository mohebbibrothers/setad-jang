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


def get_public_category_by_slug(slug: str) -> KindnessCategory | None:
    """Return one active category by slug."""
    return get_public_categories().filter(slug=slug).first()


def get_admin_listings() -> QuerySet[KindnessListing]:
    """Return all listings for admin moderation."""
    return KindnessListing.all_objects.select_related("category", "owner", "reviewed_by").prefetch_related("images")


def get_admin_listing_by_id(listing_id: int) -> KindnessListing | None:
    """Return one listing in admin scope."""
    return get_admin_listings().filter(pk=listing_id).first()


def get_user_listing_by_id(*, user_id: int, listing_id: int) -> KindnessListing | None:
    """Return a user's own listing with IDOR protection."""
    return get_user_listings(user_id=user_id).filter(pk=listing_id).first()


def get_match_by_id(*, match_id: int) -> KindnessMatch | None:
    """Return one match with listing owners loaded."""
    return KindnessMatch.objects.select_related("source_listing", "target_listing", "source_listing__owner").filter(pk=match_id).first()


def get_user_matches(*, user_id: int) -> QuerySet[KindnessMatch]:
    """Return active matches for listings owned by a user."""
    return (
        KindnessMatch.objects.filter(source_listing__owner_id=user_id, status=MatchStatus.ACTIVE)
        .select_related("source_listing", "target_listing", "target_listing__category")
        .order_by("-score", "-generated_at")
    )


def get_admin_reports():
    """Return listing reports for admin review."""
    from apps.kindness_wall.models import KindnessListingReport

    return KindnessListingReport.objects.select_related("listing", "reported_by", "reviewed_by").order_by("-created_at")


def get_admin_report_by_id(*, report_id: int):
    """Return one listing report for admin review."""
    return get_admin_reports().filter(pk=report_id).first()

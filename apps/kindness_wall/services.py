"""Business services for Kindness Wall mutations and workflows."""

from __future__ import annotations

from typing import Any

from django.db import transaction
from django.utils import timezone

from apps.kindness_wall.choices import ListingStatus, MatchStatus
from apps.kindness_wall.matching import calculate_match_score, tokenize
from apps.kindness_wall.models import (
    KindnessCategory,
    KindnessDuplicateCandidate,
    KindnessListing,
    KindnessListingTag,
    KindnessMatch,
    KindnessTag,
)


class KindnessWallServiceError(Exception):
    """Base service-layer exception for Kindness Wall."""


class KindnessProfileIncompleteError(KindnessWallServiceError):
    """Raised when a user profile is incomplete for listing creation/contact reveal."""


class KindnessListingStateError(KindnessWallServiceError):
    """Raised when a listing workflow transition is invalid."""


class KindnessPermissionError(KindnessWallServiceError):
    """Raised when an owner/admin boundary is violated."""


DEFAULT_LISTING_TTL_DAYS = 45
MATCH_THRESHOLD = 40
MAX_MATCHES_PER_LISTING = 25


def ensure_user_can_create_listing(user: Any) -> None:
    """Validate identity/profile requirements for creating a listing."""
    profile = getattr(user, "profile", None)
    if not (
        user
        and getattr(user, "is_authenticated", False)
        and getattr(user, "first_name", "").strip()
        and getattr(user, "last_name", "").strip()
        and getattr(user, "phone_number", "")
        and getattr(user, "is_phone_verified", False)
        and profile
        and getattr(profile, "national_code", "").strip()
        and getattr(profile, "province", "").strip()
        and getattr(profile, "city", "").strip()
    ):
        raise KindnessProfileIncompleteError(
            "برای ثبت آگهی باید نام، نام خانوادگی، شماره موبایل تأییدشده، کد ملی، استان و شهر را در پروفایل تکمیل کنید."
        )


def _snapshot_owner(user: Any) -> dict[str, str]:
    """Build stable owner/contact snapshots for a listing."""
    profile = getattr(user, "profile", None)
    avatar = getattr(profile, "avatar", None) if profile else None
    return {
        "contact_phone_snapshot": user.phone_number,
        "owner_full_name_snapshot": getattr(user, "full_name", "") or f"{user.first_name} {user.last_name}".strip(),
        "owner_avatar_snapshot": getattr(avatar, "url", "") if avatar else "",
        "owner_gender_snapshot": getattr(profile, "gender", "") if profile else "",
        "owner_province_snapshot": getattr(profile, "province", "") if profile else "",
        "owner_city_snapshot": getattr(profile, "city", "") if profile else "",
    }


@transaction.atomic
def create_listing(
    *,
    owner: Any,
    listing_type: str,
    category: KindnessCategory,
    title: str,
    description: str,
    province: str | None = None,
    city: str | None = None,
    district: str = "",
    address_hint: str = "",
) -> KindnessListing:
    """Create a listing in draft state with owner identity snapshots and auto-tags."""
    ensure_user_can_create_listing(owner)
    profile = owner.profile
    listing = KindnessListing.objects.create(
        owner=owner,
        listing_type=listing_type,
        category=category,
        title=title.strip(),
        description=description.strip(),
        province=province or profile.province,
        city=city or profile.city,
        district=district,
        address_hint=address_hint,
        status=ListingStatus.DRAFT,
        expires_at=timezone.now() + timezone.timedelta(days=DEFAULT_LISTING_TTL_DAYS),
        **_snapshot_owner(owner),
    )
    sync_listing_tags(listing=listing)
    return listing


@transaction.atomic
def sync_listing_tags(*, listing: KindnessListing) -> None:
    """Extract and persist normalized tags from listing title/description."""
    tokens = tokenize(f"{listing.title} {listing.description}")
    for token in tokens:
        tag, _created = KindnessTag.objects.get_or_create(name=token, defaults={"normalized_name": token})
        KindnessListingTag.objects.get_or_create(listing=listing, tag=tag, defaults={"weight": 1})
        tag.usage_count = tag.listing_tags.count()
        tag.save(update_fields=["usage_count", "updated_at"])


@transaction.atomic
def submit_listing_for_review(*, listing: KindnessListing, user: Any) -> KindnessListing:
    """Submit a draft/rejected/needs-edit listing for admin review."""
    if listing.owner_id != user.pk:
        raise KindnessPermissionError("فقط سازنده آگهی می‌تواند آن را برای بررسی ارسال کند.")
    if listing.status not in {ListingStatus.DRAFT, ListingStatus.REJECTED, ListingStatus.NEEDS_EDIT, ListingStatus.CLOSED}:
        raise KindnessListingStateError("این آگهی در وضعیت فعلی قابل ارسال برای بررسی نیست.")
    listing.status = ListingStatus.PENDING_REVIEW
    listing.save(update_fields=["status", "updated_at"])
    return listing


@transaction.atomic
def approve_listing(*, listing: KindnessListing, admin: Any, admin_note: str = "") -> KindnessListing:
    """Approve a pending listing, publish it, and regenerate matches."""
    if listing.status != ListingStatus.PENDING_REVIEW:
        raise KindnessListingStateError("فقط آگهی‌های در انتظار بررسی قابل تأیید هستند.")
    listing.status = ListingStatus.PUBLISHED
    listing.reviewed_by = admin
    listing.reviewed_at = timezone.now()
    listing.admin_note = admin_note
    listing.published_at = timezone.now()
    listing.save(update_fields=["status", "reviewed_by", "reviewed_at", "admin_note", "published_at", "updated_at"])
    sync_category_counters(category=listing.category)
    regenerate_matches_for_listing(listing=listing)
    return listing


@transaction.atomic
def reject_listing(*, listing: KindnessListing, admin: Any, reason: str, needs_edit: bool = False) -> KindnessListing:
    """Reject or mark a pending listing as needing edits."""
    if listing.status != ListingStatus.PENDING_REVIEW:
        raise KindnessListingStateError("فقط آگهی‌های در انتظار بررسی قابل رد هستند.")
    listing.status = ListingStatus.NEEDS_EDIT if needs_edit else ListingStatus.REJECTED
    listing.reviewed_by = admin
    listing.reviewed_at = timezone.now()
    listing.rejection_reason = reason
    listing.save(update_fields=["status", "reviewed_by", "reviewed_at", "rejection_reason", "updated_at"])
    return listing


def sync_category_counters(*, category: KindnessCategory) -> KindnessCategory:
    """Recalculate category listing counters."""
    category.listings_count = KindnessListing.all_objects.filter(category=category).count()
    category.published_listings_count = KindnessListing.objects.published().filter(category=category).count()
    category.save(update_fields=["listings_count", "published_listings_count", "updated_at"])
    return category


@transaction.atomic
def regenerate_matches_for_listing(*, listing: KindnessListing) -> list[KindnessMatch]:
    """Generate and persist top active matches for a published listing."""
    if listing.status != ListingStatus.PUBLISHED:
        return []
    candidates = (
        KindnessListing.objects.published()
        .opposite_type(listing.listing_type)
        .select_related("category", "category__parent", "owner")
        .exclude(pk=listing.pk)
    )
    matches: list[KindnessMatch] = []
    for candidate in candidates:
        score = calculate_match_score(source=listing, target=candidate)
        if score.score < MATCH_THRESHOLD:
            continue
        match, _created = KindnessMatch.objects.update_or_create(
            source_listing=listing,
            target_listing=candidate,
            defaults={
                "score": score.score,
                "score_breakdown": score.breakdown,
                "reason_codes": score.reason_codes,
                "explanation": score.explanation,
                "status": MatchStatus.ACTIVE,
                "algorithm_version": listing.match_generation_version,
                "generated_at": timezone.now(),
            },
        )
        matches.append(match)
    stale_ids = [match.pk for match in sorted(matches, key=lambda item: item.score, reverse=True)[:MAX_MATCHES_PER_LISTING]]
    KindnessMatch.objects.filter(source_listing=listing).exclude(pk__in=stale_ids).update(status=MatchStatus.STALE)
    listing.last_matched_at = timezone.now()
    listing.save(update_fields=["last_matched_at", "updated_at"])
    return sorted(matches, key=lambda item: item.score, reverse=True)[:MAX_MATCHES_PER_LISTING]


def _text_similarity_score(left: str, right: str, *, multiplier: int) -> int:
    """Return token-overlap similarity for duplicate detection."""
    left_tokens = tokenize(left)
    right_tokens = tokenize(right)
    if not left_tokens or not right_tokens:
        return 0
    return round((len(left_tokens & right_tokens) / len(left_tokens | right_tokens)) * 10 * multiplier)


def detect_duplicate_candidates(*, listing: KindnessListing, threshold: int = 75) -> list[KindnessDuplicateCandidate]:
    """Detect likely duplicate listings by same owner/type/category and text similarity."""
    candidates = KindnessListing.all_objects.filter(
        owner=listing.owner,
        listing_type=listing.listing_type,
        category=listing.category,
    ).exclude(pk=listing.pk)
    duplicates: list[KindnessDuplicateCandidate] = []
    for candidate in candidates:
        title_score = _text_similarity_score(listing.title, candidate.title, multiplier=4)
        description_score = _text_similarity_score(listing.description, candidate.description, multiplier=3)
        duplicate_score = min(title_score + description_score, 100)
        if duplicate_score >= threshold:
            duplicate, _created = KindnessDuplicateCandidate.objects.update_or_create(
                listing=listing,
                candidate_listing=candidate,
                defaults={"score": duplicate_score, "reason": "شباهت بالای عنوان و توضیحات"},
            )
            duplicates.append(duplicate)
    return duplicates

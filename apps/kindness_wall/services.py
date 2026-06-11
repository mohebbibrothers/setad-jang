"""Business services for Kindness Wall mutations and workflows."""

from __future__ import annotations

from typing import Any

from django.db import transaction
from django.utils import timezone

from apps.kindness_wall.choices import DuplicateStatus, ListingStatus, MatchStatus, ReportStatus
from apps.kindness_wall.matching import calculate_match_score, tokenize
from apps.kindness_wall.models import (
    KindnessBookmark,
    KindnessCategory,
    KindnessContactReveal,
    KindnessDuplicateCandidate,
    KindnessListing,
    KindnessListingReport,
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


_SENSITIVE_REVIEW_FIELDS = {
    "listing_type",
    "category",
    "title",
    "description",
    "province",
    "city",
    "district",
    "address_hint",
}


@transaction.atomic
def update_listing(*, listing: KindnessListing, user: Any, **fields: Any) -> KindnessListing:
    """Update owner listing and return to review if sensitive public fields changed."""
    if listing.owner_id != user.pk:
        raise KindnessPermissionError("فقط سازنده آگهی می‌تواند آن را ویرایش کند.")
    allowed = _SENSITIVE_REVIEW_FIELDS | {"latitude", "longitude"}
    changed_sensitive = False
    update_fields: list[str] = []
    for field, value in fields.items():
        if field not in allowed:
            continue
        current = getattr(listing, field)
        if current != value:
            setattr(listing, field, value)
            update_fields.append(field)
            if field in _SENSITIVE_REVIEW_FIELDS:
                changed_sensitive = True
    if changed_sensitive and listing.status == ListingStatus.PUBLISHED:
        listing.status = ListingStatus.PENDING_REVIEW
        listing.published_at = None
        update_fields.extend(["status", "published_at"])
    if update_fields:
        update_fields.append("updated_at")
        listing.save(update_fields=list(set(update_fields)))
        sync_listing_tags(listing=listing)
        detect_duplicate_candidates(listing=listing)
    return listing


@transaction.atomic
def close_listing(*, listing: KindnessListing, user: Any) -> KindnessListing:
    """Close a listing by owner."""
    if listing.owner_id != user.pk:
        raise KindnessPermissionError("فقط سازنده آگهی می‌تواند آن را ببندد.")
    if listing.status not in {ListingStatus.PUBLISHED, ListingStatus.PENDING_REVIEW, ListingStatus.REJECTED, ListingStatus.NEEDS_EDIT}:
        raise KindnessListingStateError("این آگهی در وضعیت فعلی قابل بستن نیست.")
    listing.status = ListingStatus.CLOSED
    listing.closed_at = timezone.now()
    listing.save(update_fields=["status", "closed_at", "updated_at"])
    return listing


@transaction.atomic
def soft_delete_listing(*, listing: KindnessListing, user: Any) -> None:
    """Soft-delete a listing by owner."""
    if listing.owner_id != user.pk:
        raise KindnessPermissionError("فقط سازنده آگهی می‌تواند آن را حذف کند.")
    listing.status = ListingStatus.DELETED
    listing.is_active = False
    listing.save(update_fields=["status", "is_active", "updated_at"])
    sync_category_counters(category=listing.category)


@transaction.atomic
def suspend_listing(*, listing: KindnessListing, admin: Any, reason: str) -> KindnessListing:
    """Suspend a published listing by admin."""
    if listing.status != ListingStatus.PUBLISHED:
        raise KindnessListingStateError("فقط آگهی منتشرشده قابل تعلیق است.")
    listing.status = ListingStatus.SUSPENDED
    listing.reviewed_by = admin
    listing.reviewed_at = timezone.now()
    listing.suspension_reason = reason
    listing.save(update_fields=["status", "reviewed_by", "reviewed_at", "suspension_reason", "updated_at"])
    return listing


@transaction.atomic
def restore_suspended_listing(*, listing: KindnessListing, admin: Any) -> KindnessListing:
    """Restore a suspended listing to published state by admin."""
    if listing.status != ListingStatus.SUSPENDED:
        raise KindnessListingStateError("فقط آگهی تعلیق‌شده قابل بازگردانی است.")
    listing.status = ListingStatus.PUBLISHED
    listing.reviewed_by = admin
    listing.reviewed_at = timezone.now()
    listing.suspension_reason = ""
    listing.save(update_fields=["status", "reviewed_by", "reviewed_at", "suspension_reason", "updated_at"])
    regenerate_matches_for_listing(listing=listing)
    return listing


@transaction.atomic
def renew_listing(*, listing: KindnessListing, user: Any, ttl_days: int = DEFAULT_LISTING_TTL_DAYS) -> KindnessListing:
    """Renew an owner listing expiration window."""
    if listing.owner_id != user.pk:
        raise KindnessPermissionError("فقط سازنده آگهی می‌تواند آن را تمدید کند.")
    if listing.status not in {ListingStatus.PUBLISHED, ListingStatus.EXPIRED, ListingStatus.CLOSED}:
        raise KindnessListingStateError("این آگهی در وضعیت فعلی قابل تمدید نیست.")
    listing.expires_at = timezone.now() + timezone.timedelta(days=ttl_days)
    if listing.status in {ListingStatus.EXPIRED, ListingStatus.CLOSED}:
        listing.status = ListingStatus.PENDING_REVIEW
    listing.save(update_fields=["expires_at", "status", "updated_at"])
    return listing


@transaction.atomic
def expire_due_listings(*, now=None) -> int:
    """Expire published listings whose expiration date has passed."""
    now = now or timezone.now()
    updated = KindnessListing.objects.filter(
        status=ListingStatus.PUBLISHED,
        expires_at__isnull=False,
        expires_at__lte=now,
    ).update(status=ListingStatus.EXPIRED, updated_at=now)
    return int(updated)


@transaction.atomic
def reveal_contact(*, listing: KindnessListing, viewer: Any, ip_address: str | None = None, user_agent: str = "", request_id: str = "") -> KindnessContactReveal:
    """Reveal listing contact phone to an authenticated user and record audit trail."""
    if not getattr(viewer, "is_authenticated", False):
        raise KindnessPermissionError("برای مشاهده شماره تماس باید وارد حساب کاربری شوید.")
    if not listing.is_public:
        raise KindnessListingStateError("شماره تماس فقط برای آگهی منتشرشده قابل مشاهده است.")
    reveal = KindnessContactReveal.objects.create(
        listing=listing,
        viewer=viewer,
        listing_owner=listing.owner,
        phone_snapshot=listing.contact_phone_snapshot,
        ip_address=ip_address,
        user_agent=user_agent[:512] if user_agent else "",
        request_id=request_id or "",
    )
    listing.contact_reveal_count = listing.contact_reveals.count()
    listing.save(update_fields=["contact_reveal_count", "updated_at"])
    return reveal


@transaction.atomic
def create_bookmark(*, listing: KindnessListing, user: Any) -> KindnessBookmark:
    """Bookmark a public listing idempotently."""
    if not listing.is_public:
        raise KindnessListingStateError("فقط آگهی منتشرشده قابل ذخیره است.")
    bookmark, _created = KindnessBookmark.objects.get_or_create(user=user, listing=listing)
    listing.bookmark_count = listing.bookmarks.count()
    listing.save(update_fields=["bookmark_count", "updated_at"])
    return bookmark


@transaction.atomic
def delete_bookmark(*, listing: KindnessListing, user: Any) -> None:
    """Remove a user's bookmark for a listing."""
    KindnessBookmark.objects.filter(user=user, listing=listing).delete()
    listing.bookmark_count = listing.bookmarks.count()
    listing.save(update_fields=["bookmark_count", "updated_at"])


@transaction.atomic
def report_listing(*, listing: KindnessListing, reported_by: Any, reason: str, description: str = "") -> KindnessListingReport:
    """Report a public listing for admin moderation."""
    if not listing.is_public:
        raise KindnessListingStateError("فقط آگهی منتشرشده قابل گزارش است.")
    report = KindnessListingReport.objects.create(
        listing=listing,
        reported_by=reported_by,
        reason=reason,
        description=description,
    )
    listing.report_count = listing.reports.count()
    listing.save(update_fields=["report_count", "updated_at"])
    return report


@transaction.atomic
def review_listing_report(*, report: KindnessListingReport, admin: Any, status: str, admin_note: str = "", suspend_listing_on_review: bool = False) -> KindnessListingReport:
    """Review a listing report and optionally suspend the listing."""
    if status not in ReportStatus.values:
        raise KindnessListingStateError("وضعیت گزارش نامعتبر است.")
    report.status = status
    report.reviewed_by = admin
    report.reviewed_at = timezone.now()
    report.admin_note = admin_note
    report.save(update_fields=["status", "reviewed_by", "reviewed_at", "admin_note", "updated_at"])
    if suspend_listing_on_review and status == ReportStatus.REVIEWED and report.listing.status == ListingStatus.PUBLISHED:
        suspend_listing(listing=report.listing, admin=admin, reason=admin_note or "گزارش تخلف تأیید شد.")
    return report


@transaction.atomic
def dismiss_match(*, match: KindnessMatch, user: Any) -> KindnessMatch:
    """Dismiss a match for the owner of the source listing."""
    if match.source_listing.owner_id != user.pk:
        raise KindnessPermissionError("فقط صاحب آگهی می‌تواند این پیشنهاد را نادیده بگیرد.")
    match.status = MatchStatus.DISMISSED
    match.dismissed_by = user
    match.dismissed_at = timezone.now()
    match.save(update_fields=["status", "dismissed_by", "dismissed_at", "updated_at"])
    return match


@transaction.atomic
def mark_match_contacted(*, match: KindnessMatch, user: Any) -> KindnessMatch:
    """Mark a match as contacted by the source listing owner."""
    if match.source_listing.owner_id != user.pk:
        raise KindnessPermissionError("فقط صاحب آگهی می‌تواند این پیشنهاد را به‌عنوان تماس‌گرفته‌شده ثبت کند.")
    match.status = MatchStatus.CONTACTED
    match.contacted_at = timezone.now()
    match.save(update_fields=["status", "contacted_at", "updated_at"])
    return match


@transaction.atomic
def review_duplicate_candidate(*, duplicate: KindnessDuplicateCandidate, status: str, reason: str = "") -> KindnessDuplicateCandidate:
    """Review a duplicate candidate."""
    if status not in DuplicateStatus.values:
        raise KindnessListingStateError("وضعیت بررسی تکراری بودن نامعتبر است.")
    duplicate.status = status
    if reason:
        duplicate.reason = reason
    duplicate.save(update_fields=["status", "reason", "updated_at"])
    return duplicate


def get_admin_analytics_summary() -> dict[str, int]:
    """Return aggregate counters for admin dashboard."""
    return {
        "total_listings": KindnessListing.all_objects.count(),
        "pending_listings": KindnessListing.all_objects.filter(status=ListingStatus.PENDING_REVIEW).count(),
        "published_listings": KindnessListing.objects.published().count(),
        "need_help_listings": KindnessListing.all_objects.filter(listing_type="need_help").count(),
        "offer_help_listings": KindnessListing.all_objects.filter(listing_type="offer_help").count(),
        "contact_reveals": KindnessContactReveal.objects.count(),
        "active_matches": KindnessMatch.objects.filter(status=MatchStatus.ACTIVE).count(),
        "pending_reports": KindnessListingReport.objects.filter(status=ReportStatus.PENDING).count(),
    }


@transaction.atomic
def increment_listing_view_count(*, listing: KindnessListing) -> KindnessListing:
    """Increment listing view counter in service layer."""
    listing.view_count = listing.view_count + 1
    listing.save(update_fields=["view_count", "updated_at"])
    return listing

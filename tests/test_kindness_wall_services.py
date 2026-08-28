"""
Kindness Wall Phase 2 service workflow tests.

این تست‌ها full service layer دیوار مهربانی را پوشش می‌دهند: update/resubmit،
admin moderation، reveal-contact فقط برای کاربر لاگین‌شده، bookmark/report،
match actions، expiration/renewal، duplicate review و analytics primitives.
"""

from __future__ import annotations

import pytest
from django.utils import timezone

from apps.kindness_wall.choices import (
    DuplicateStatus,
    ListingStatus,
    MatchStatus,
    ReportReason,
    ReportStatus,
)
from apps.kindness_wall.models import (
    KindnessBookmark,
    KindnessContactReveal,
    KindnessMatch,
)
from apps.kindness_wall.services import (
    KindnessPermissionError,
    approve_listing,
    close_listing,
    create_bookmark,
    create_listing,
    delete_bookmark,
    dismiss_match,
    expire_due_listings,
    get_admin_analytics_summary,
    mark_match_contacted,
    reject_listing,
    renew_listing,
    report_listing,
    restore_suspended_listing,
    reveal_contact,
    review_duplicate_candidate,
    review_listing_report,
    submit_listing_for_review,
    suspend_listing,
    update_listing,
)
from tests.factories.kindness_wall import (
    KindnessCategoryFactory,
    KindnessListingFactory,
    KindnessUserFactory,
    PublishedNeedListingFactory,
    PublishedOfferListingFactory,
)

pytestmark = pytest.mark.django_db


def _approved_listing(*, owner=None, category=None, **kwargs):
    """Create a published listing through service workflow."""
    owner = owner or KindnessUserFactory()
    category = category or KindnessCategoryFactory()
    listing = create_listing(owner=owner, category=category, **kwargs)
    submit_listing_for_review(listing=listing, user=owner)
    approve_listing(listing=listing, admin=KindnessUserFactory())
    listing.refresh_from_db()
    return listing


class TestKindnessListingOwnerWorkflow:
    """Owner update/close/delete/renew behavior."""

    def test_sensitive_update_moves_published_listing_back_to_pending_review(self) -> None:
        listing = _approved_listing(
            listing_type="need_help",
            title="برنامه نویس نیاز دارم",
            description="برای سایت خیریه دنبال کمک هستم",
        )

        updated = update_listing(
            listing=listing, user=listing.owner, title="برنامه نویس فول استک نیاز دارم"
        )

        assert updated.status == ListingStatus.PENDING_REVIEW
        assert updated.published_at is None
        assert updated.listing_tags.count() > 0

    def test_non_owner_cannot_update_or_close_listing(self) -> None:
        listing = _approved_listing(
            listing_type="offer_help",
            title="طراح سایت هستم",
            description="برای کارهای خیریه کمک می‌کنم",
        )
        other = KindnessUserFactory()

        with pytest.raises(KindnessPermissionError):
            update_listing(listing=listing, user=other, title="تغییر غیرمجاز")

        with pytest.raises(KindnessPermissionError):
            close_listing(listing=listing, user=other)

    def test_owner_can_close_and_renew_listing_for_review(self) -> None:
        listing = _approved_listing(
            listing_type="need_help",
            title="نیاز به وسیله",
            description="توضیح آگهی",
        )

        close_listing(listing=listing, user=listing.owner)
        listing.refresh_from_db()
        assert listing.status == ListingStatus.CLOSED

        renew_listing(listing=listing, user=listing.owner)
        listing.refresh_from_db()
        assert listing.status == ListingStatus.PENDING_REVIEW
        assert listing.expires_at > timezone.now()


class TestKindnessAdminModerationWorkflow:
    """Admin listing review/suspend/restore behavior."""

    def test_admin_can_suspend_and_restore_published_listing(self) -> None:
        listing = _approved_listing(
            listing_type="offer_help",
            title="کمک برنامه نویسی",
            description="کمک داوطلبانه برای طراحی سایت",
        )
        admin = KindnessUserFactory()

        suspend_listing(listing=listing, admin=admin, reason="گزارش تخلف")
        listing.refresh_from_db()
        assert listing.status == ListingStatus.SUSPENDED
        assert listing.suspension_reason == "گزارش تخلف"

        restore_suspended_listing(listing=listing, admin=admin)
        listing.refresh_from_db()
        assert listing.status == ListingStatus.PUBLISHED
        assert listing.suspension_reason == ""

    def test_reject_listing_can_mark_needs_edit(self) -> None:
        listing = KindnessListingFactory(status=ListingStatus.PENDING_REVIEW)
        admin = KindnessUserFactory()

        reject_listing(listing=listing, admin=admin, reason="توضیحات ناقص", needs_edit=True)
        listing.refresh_from_db()

        assert listing.status == ListingStatus.NEEDS_EDIT
        assert listing.rejection_reason == "توضیحات ناقص"


class TestKindnessContactBookmarkReport:
    """Contact reveal, bookmark, report, and analytics behavior."""

    def test_reveal_contact_requires_authenticated_user_and_records_audit_row(self) -> None:
        listing = PublishedOfferListingFactory(contact_phone_snapshot="+989120000000")
        viewer = KindnessUserFactory()

        reveal = reveal_contact(
            listing=listing,
            viewer=viewer,
            ip_address="203.0.113.1",
            user_agent="pytest-agent",
            request_id="req-kindness-1",
        )

        assert reveal.phone_snapshot == "+989120000000"
        assert reveal.viewer_id == viewer.pk
        listing.refresh_from_db()
        assert listing.contact_reveal_count == 1
        assert KindnessContactReveal.objects.count() == 1

    def test_anonymous_cannot_reveal_contact(self) -> None:
        listing = PublishedNeedListingFactory()
        anonymous = type("Anon", (), {"is_authenticated": False})()

        with pytest.raises(KindnessPermissionError):
            reveal_contact(listing=listing, viewer=anonymous)

    def test_bookmark_is_idempotent_and_deletable(self) -> None:
        listing = PublishedOfferListingFactory()
        user = KindnessUserFactory()

        first = create_bookmark(listing=listing, user=user)
        second = create_bookmark(listing=listing, user=user)

        assert first.pk == second.pk
        assert KindnessBookmark.objects.count() == 1
        listing.refresh_from_db()
        assert listing.bookmark_count == 1

        delete_bookmark(listing=listing, user=user)
        assert KindnessBookmark.objects.count() == 0
        listing.refresh_from_db()
        assert listing.bookmark_count == 0

    def test_report_review_can_suspend_listing_and_updates_counts(self) -> None:
        listing = PublishedNeedListingFactory()
        reporter = KindnessUserFactory()
        admin = KindnessUserFactory()

        report = report_listing(
            listing=listing,
            reported_by=reporter,
            reason=ReportReason.SPAM,
            description="آگهی اسپم است",
        )
        listing.refresh_from_db()
        assert listing.report_count == 1

        review_listing_report(
            report=report,
            admin=admin,
            status=ReportStatus.REVIEWED,
            admin_note="گزارش درست بود",
            suspend_listing_on_review=True,
        )
        report.refresh_from_db()
        listing.refresh_from_db()
        assert report.status == ReportStatus.REVIEWED
        assert listing.status == ListingStatus.SUSPENDED


class TestKindnessMatchAndMaintenance:
    """Match actions, duplicate review, expiration, and analytics."""

    def test_match_can_be_dismissed_and_marked_contacted_by_source_owner(self) -> None:
        source = PublishedNeedListingFactory(
            title="برنامه نویس لازم دارم", description="طراحی سایت"
        )
        target = PublishedOfferListingFactory(
            category=source.category, title="برنامه نویس هستم", description="طراحی سایت"
        )
        match = KindnessMatch.objects.create(source_listing=source, target_listing=target, score=80)

        dismiss_match(match=match, user=source.owner)
        match.refresh_from_db()
        assert match.status == MatchStatus.DISMISSED
        assert match.dismissed_by_id == source.owner_id

        match.status = MatchStatus.ACTIVE
        match.save(update_fields=["status"])
        mark_match_contacted(match=match, user=source.owner)
        match.refresh_from_db()
        assert match.status == MatchStatus.CONTACTED
        assert match.contacted_at is not None

    def test_expire_due_listings_and_analytics_summary(self) -> None:
        expired = PublishedNeedListingFactory(
            expires_at=timezone.now() - timezone.timedelta(days=1)
        )
        active = PublishedOfferListingFactory(
            expires_at=timezone.now() + timezone.timedelta(days=10)
        )
        report_listing(listing=active, reported_by=KindnessUserFactory(), reason=ReportReason.OTHER)
        reveal_contact(listing=active, viewer=KindnessUserFactory())

        updated = expire_due_listings()
        expired.refresh_from_db()
        summary = get_admin_analytics_summary()

        assert updated == 1
        assert expired.status == ListingStatus.EXPIRED
        assert summary["total_listings"] >= 2
        assert summary["published_listings"] == 1
        assert summary["contact_reveals"] == 1
        assert summary["pending_reports"] == 1

    def test_duplicate_candidate_review_changes_status(self) -> None:
        listing = KindnessListingFactory()
        candidate = KindnessListingFactory(owner=listing.owner, category=listing.category)
        duplicate = listing.duplicate_candidates.create(candidate_listing=candidate, score=90)

        review_duplicate_candidate(
            duplicate=duplicate, status=DuplicateStatus.CONFIRMED, reason="واقعاً تکراری است"
        )
        duplicate.refresh_from_db()

        assert duplicate.status == DuplicateStatus.CONFIRMED
        assert duplicate.reason == "واقعاً تکراری است"

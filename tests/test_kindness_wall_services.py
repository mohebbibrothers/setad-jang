"""تست‌های لایهٔ سرویس دیوار مهربانی — چرخهٔ حیات، TTL، نگهبان‌ها، upsert اعلام.

هر قاعدهٔ سیاست‌گذاری v2 باید همین‌جا آزمون مستقل داشته باشد؛ اگر تستی از
این فایل حذف می‌شود، یعنی آن قاعده عمداً از سیاست بیرون رفته است.
"""

from __future__ import annotations

from datetime import timedelta

import pytest
from django.test import override_settings
from django.utils import timezone

from apps.kindness_wall import services
from apps.kindness_wall.choices import ListingStatus, OfferStatus
from apps.kindness_wall.models import KindnessListing
from tests.factories import UserFactory
from tests.factories.kindness_wall import (
    KindnessCategoryFactory,
    KindnessListingFactory,
    PublishedNeedListingFactory,
)

pytestmark = pytest.mark.django_db


class TestPublishGuard:
    def test_publish_requires_at_least_one_channel(self) -> None:
        listing = KindnessListingFactory(status=ListingStatus.DRAFT, contact_phone="")
        with pytest.raises(services.KindnessWallServiceError, match="حداقل یکی"):
            services.publish_listing(listing=listing)
        listing.refresh_from_db()
        assert listing.status == ListingStatus.DRAFT

    def test_publish_sets_expiry_from_ttl_setting(self) -> None:
        with override_settings(KINDNESS_LISTING_TTL_DAYS=7):
            listing = KindnessListingFactory()
            services.publish_listing(listing=listing)
        assert listing.status == ListingStatus.PUBLISHED
        assert listing.expires_at is not None
        window = listing.expires_at - timezone.now()
        assert 6 * 24 * 3600 < window.total_seconds() <= 7 * 24 * 3600 + 1

    def test_publish_keeps_manual_expiry(self) -> None:
        manual = timezone.now() + timedelta(days=365)
        listing = KindnessListingFactory(expires_at=manual)
        services.publish_listing(listing=listing)
        assert listing.expires_at == manual

    def test_publish_rejects_incomplete_content(self) -> None:
        listing = KindnessListingFactory(title="", description="کوتاه")
        with pytest.raises(services.KindnessWallServiceError, match="کامل نیستند"):
            services.publish_listing(listing=listing)

    def test_publish_resumes_expired_listing(self) -> None:
        """انتشار مجدد آگهی منقضی: وضعیت برمی‌گردد و مهلت از تازه ساخته می‌شود."""
        listing = PublishedNeedListingFactory()
        KindnessListing.all_objects.filter(pk=listing.pk).update(
            status=ListingStatus.EXPIRED, expires_at=timezone.now() - timedelta(days=2)
        )
        services.publish_listing(listing=listing)
        assert listing.status == ListingStatus.PUBLISHED
        assert listing.expires_at > timezone.now()


class TestRenewFulfillArchive:
    def test_renew_extends_from_now_not_from_old_expiry(self) -> None:
        past_expiry = timezone.now() - timedelta(days=3)
        listing = PublishedNeedListingFactory(expires_at=past_expiry)
        listing.refresh_from_db()
        with override_settings(KINDNESS_LISTING_TTL_DAYS=45):
            services.renew_listing(listing=listing)
        assert listing.status == ListingStatus.PUBLISHED
        assert listing.renew_count == 1
        assert listing.expires_at > timezone.now() + timedelta(days=44)

    def test_renew_counts_and_resumes_expired(self) -> None:
        listing = PublishedNeedListingFactory()
        KindnessListing.all_objects.filter(pk=listing.pk).update(
            status=ListingStatus.EXPIRED, expires_at=timezone.now() - timedelta(hours=1)
        )
        listing.refresh_from_db()
        services.renew_listing(listing=listing)
        assert listing.status == ListingStatus.PUBLISHED
        assert listing.renew_count == 1

    def test_renew_rejected_on_fulfilled(self) -> None:
        listing = PublishedNeedListingFactory()
        services.fulfill_listing(listing=listing)
        with pytest.raises(services.KindnessListingStateError):
            services.renew_listing(listing=listing)

    def test_fulfill_records_note_and_timestamp(self) -> None:
        listing = PublishedNeedListingFactory()
        services.fulfill_listing(listing=listing, note="  دو خانواده کمک کردند  ")
        listing.refresh_from_db()
        assert listing.status == ListingStatus.FULFILLED
        assert listing.fulfilled_at is not None
        assert listing.fulfillment_note == "دو خانواده کمک کردند"

    def test_fulfill_from_draft_not_allowed(self) -> None:
        listing = KindnessListingFactory()
        with pytest.raises(services.KindnessListingStateError):
            services.fulfill_listing(listing=listing)

    def test_archive_from_any_state_and_revert(self) -> None:
        listing = KindnessListingFactory()
        services.archive_listing(listing=listing)
        assert listing.status == ListingStatus.ARCHIVED
        services.revert_to_draft(listing=listing)
        assert listing.status == ListingStatus.DRAFT
        assert KindnessListing.all_objects.filter(pk=listing.pk).exists()

    def test_featured_toggle_persists(self) -> None:
        listing = PublishedNeedListingFactory()
        services.set_featured(listing=listing, featured=True)
        listing.refresh_from_db()
        assert listing.is_featured is True
        services.set_featured(listing=listing, featured=False)
        listing.refresh_from_db()
        assert listing.is_featured is False


class TestExpiryTaskService:
    def test_expire_due_listings_only_touches_overdue_published(self) -> None:
        stale = PublishedNeedListingFactory(expires_at=timezone.now() - timedelta(minutes=1))
        fresh = PublishedNeedListingFactory()
        draft = KindnessListingFactory()
        count = services.expire_due_listings()
        assert count == 1
        stale.refresh_from_db()
        fresh.refresh_from_db()
        draft.refresh_from_db()
        assert stale.status == ListingStatus.EXPIRED
        assert fresh.status == ListingStatus.PUBLISHED
        assert draft.status == ListingStatus.DRAFT

    def test_expire_task_returns_count_and_is_idempotent(self) -> None:
        from apps.kindness_wall.tasks import expire_old_listings_task

        PublishedNeedListingFactory(expires_at=timezone.now() - timedelta(minutes=1))
        assert expire_old_listings_task() >= 1
        assert expire_old_listings_task() == 0

    def test_bulk_update_does_not_break_board(self) -> None:
        """انقضای دسته‌ای باید آگهی را از تختهٔ عمومی خارج کند (سلکتور، نه سیگنال)."""
        stale = PublishedNeedListingFactory(expires_at=timezone.now() - timedelta(minutes=1))
        services.expire_due_listings()
        from apps.kindness_wall import selectors

        slugs = {row.slug for row in selectors.get_public_listings()}
        assert stale.slug not in slugs


class TestCategoryGuard:
    def test_deactivate_blocked_while_listings_open(self) -> None:
        category = KindnessCategoryFactory()
        PublishedNeedListingFactory(category=category)
        with pytest.raises(services.KindnessCategoryGuardError):
            services.set_category_active(category=category, active=False)
        assert category.is_active is True

    def test_deactivate_allowed_when_board_empty(self) -> None:
        category = KindnessCategoryFactory()
        KindnessListingFactory(category=category)  # فقط پیش‌نویس
        services.set_category_active(category=category, active=False)
        category.refresh_from_db()
        assert category.is_active is False


class TestOfferLifecycle:
    def test_submit_offer_creates_then_updates_same_row(self) -> None:
        listing = PublishedNeedListingFactory()
        user = UserFactory()
        offer, created = services.submit_offer(listing=listing, user=user, message="یک پتو دارم")
        assert created is True
        offer2, created2 = services.submit_offer(listing=listing, user=user, message="دو پتو دارم")
        assert created2 is False
        assert offer2.pk == offer.pk
        assert offer2.message == "دو پتو دارم"

    def test_submit_offer_rejects_non_board_listing(self) -> None:
        listing = KindnessListingFactory()
        user = UserFactory()
        with pytest.raises(services.KindnessOfferError, match="روی دیوار نیست"):
            services.submit_offer(listing=listing, user=user, message="")

    def test_handled_offer_is_locked_for_editing(self) -> None:
        listing = PublishedNeedListingFactory()
        user = UserFactory()
        offer, _ = services.submit_offer(listing=listing, user=user)
        admin = UserFactory()
        services.review_offer(
            offer=offer, admin=admin, status=OfferStatus.CONTACTED, note="تماس شد"
        )
        with pytest.raises(services.KindnessOfferError, match="بررسی شده"):
            services.submit_offer(listing=listing, user=user, message="باز هم!")

    def test_withdraw_only_before_handling_and_only_owner(self) -> None:
        listing = PublishedNeedListingFactory()
        owner = UserFactory()
        stranger = UserFactory()
        offer, _ = services.submit_offer(listing=listing, user=owner)
        with pytest.raises(services.KindnessOfferError, match="صاحب اعلام"):
            services.withdraw_offer(offer=offer, user=stranger)
        services.withdraw_offer(offer=offer, user=owner)
        assert not listing.offers.exists()

    def test_withdraw_blocked_after_review(self) -> None:
        listing = PublishedNeedListingFactory()
        user = UserFactory()
        offer, _ = services.submit_offer(listing=listing, user=user)
        services.review_offer(offer=offer, admin=UserFactory(), status=OfferStatus.DECLINED)
        with pytest.raises(services.KindnessOfferError, match="قابل پس‌گرفتن نیست"):
            services.withdraw_offer(offer=offer, user=user)

    def test_review_validates_status_choice(self) -> None:
        listing = PublishedNeedListingFactory()
        user = UserFactory()
        offer, _ = services.submit_offer(listing=listing, user=user)
        with pytest.raises(services.KindnessWallServiceError):
            services.review_offer(offer=offer, admin=UserFactory(), status="ghost")

    def test_review_records_handler_and_note(self) -> None:
        listing = PublishedNeedListingFactory()
        user = UserFactory()
        admin = UserFactory()
        offer, _ = services.submit_offer(listing=listing, user=user)
        services.review_offer(
            offer=offer, admin=admin, status=OfferStatus.CONTACTED, note="هماهنگ شد"
        )
        offer.refresh_from_db()
        assert offer.handled_by == admin
        assert offer.handled_at is not None
        assert offer.admin_note == "هماهنگ شد"


class TestViewCounter:
    def test_view_bump_uses_update_not_save(self) -> None:
        """شمارش بازدید نباید ردیف را save کند (سیگنال کش/رخداد ساخت)."""
        listing = PublishedNeedListingFactory()
        before = listing.updated_at
        for _ in range(3):
            services.bump_listing_view_count(listing=listing)
        listing.refresh_from_db()
        assert listing.view_count == 3
        assert listing.updated_at == before

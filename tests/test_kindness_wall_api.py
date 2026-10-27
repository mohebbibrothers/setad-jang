"""تست‌های API عمومی/کاربری دیوار مهربانی v2.

قراردادهای قفل‌شده اینجا:
- کارت‌های فهرست هیچ راه تماسی ندارند؛ فقط جزئیات؛
- انتشار فقط ادمین؛ کاربر فقط اعلام آمادگی (upsert) و پس‌گرفتن؛
- پاسخ‌ها در envelope استاندارد پروژه؛ مسیرهای عمومی کش‌شده و throttleدار.
"""

from __future__ import annotations

from datetime import timedelta

import pytest
from django.urls import reverse
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APIClient

from apps.kindness_wall.choices import ListingStatus, OfferStatus
from apps.kindness_wall.models import KindnessListing, KindnessOffer
from tests.factories import UserFactory
from tests.factories.kindness_wall import (
    KindnessCategoryFactory,
    KindnessListingFactory,
    PublishedNeedListingFactory,
)

pytestmark = pytest.mark.django_db

_CONTACT_FIELDS = (
    "contact_phone",
    "contact_bale",
    "contact_eitaa",
    "contact_telegram",
    "contact_rubika",
    "contact_instagram",
)


def _results(response) -> list[dict]:
    """دسترسی یک‌جا به آیتم‌های صفحه‌بندی‌شده در envelope پروژه."""
    return response.data["data"]["results"]


class TestPublicBoard:
    def test_board_lists_only_published_and_excludes_contacts(self) -> None:
        live = PublishedNeedListingFactory(contact_eitaa="@mehrban_id")
        draft = KindnessListingFactory(contact_phone="09122223333")

        response = APIClient().get(reverse("kindness_wall:listing-list"))

        assert response.status_code == status.HTTP_200_OK
        assert response.data["success"] is True
        rows = _results(response)
        slugs = {row["slug"] for row in rows}
        assert live.slug in slugs
        assert draft.slug not in slugs
        for row in rows:
            for field in _CONTACT_FIELDS:
                assert field not in row
            assert "contact_channels" not in row

    def test_detail_exposes_contact_channels_only_for_filled(self) -> None:
        listing = PublishedNeedListingFactory(contact_phone="09121234567", contact_bale="")
        client = APIClient()

        response = client.get(
            reverse("kindness_wall:listing-detail", kwargs={"slug": listing.slug})
        )

        assert response.status_code == status.HTTP_200_OK
        channels = response.data["data"]["contact_channels"]
        assert [item["kind"] for item in channels] == ["phone"]
        assert channels[0]["value"] == "09121234567"
        assert channels[0]["link"] == "tel:+989121234567"
        assert "bale" not in {item["kind"] for item in channels}

    def test_detail_404_for_draft_expired_and_archived(self) -> None:
        draft = KindnessListingFactory()
        expired = PublishedNeedListingFactory(expires_at=timezone.now() - timedelta(minutes=2))
        archived = PublishedNeedListingFactory()
        KindnessListing.all_objects.filter(pk=archived.pk).update(status=ListingStatus.ARCHIVED)

        client = APIClient()
        for slug in (draft.slug, expired.slug, archived.slug):
            response = client.get(reverse("kindness_wall:listing-detail", kwargs={"slug": slug}))
            assert response.status_code == status.HTTP_404_NOT_FOUND, slug

    def test_detail_bumps_view_count(self) -> None:
        listing = PublishedNeedListingFactory()
        client = APIClient()
        client.get(reverse("kindness_wall:listing-detail", kwargs={"slug": listing.slug}))
        listing.refresh_from_db()
        assert listing.view_count == 1

    def test_search_filters_on_title(self) -> None:
        needle = PublishedNeedListingFactory(title="بخاری نفتی برای اردوگاه")
        PublishedNeedListingFactory(title="یخچال قدیمی")

        response = APIClient().get(reverse("kindness_wall:listing-list"), {"search": "بخاری"})

        rows = _results(response)
        assert [row["slug"] for row in rows] == [needle.slug]

    def test_category_and_city_and_urgent_filters(self) -> None:
        category = KindnessCategoryFactory(title="لوازم آشپزخانه")
        target = PublishedNeedListingFactory(
            category=category, city="املد", urgency="urgent", title="دیگ زودپز"
        )
        other_city = PublishedNeedListingFactory(category=category, city="رشت", title="ماهیتابه")
        other_cat = PublishedNeedListingFactory(title="کاپشن")

        response = APIClient().get(
            reverse("kindness_wall:listing-list"),
            {"category": category.slug, "city": "املد"},
        )
        assert [row["slug"] for row in _results(response)] == [target.slug]

        response = APIClient().get(reverse("kindness_wall:listing-list"), {"urgent": "true"})
        slugs = {row["slug"] for row in _results(response)}
        assert target.slug in slugs
        assert other_city.slug not in slugs
        assert other_cat.slug not in slugs

    def test_ordering_whitelist_ignores_junk(self) -> None:
        old = PublishedNeedListingFactory(
            title="قدیمی", published_at=timezone.now() - timedelta(days=9)
        )
        new = PublishedNeedListingFactory(title="تازه", published_at=timezone.now())

        response = APIClient().get(reverse("kindness_wall:listing-list"), {"ordering": "fresh"})
        slugs = [row["slug"] for row in _results(response)]
        assert slugs.index(new.slug) < slugs.index(old.slug)

        junk = APIClient().get(
            reverse("kindness_wall:listing-list"), {"ordering": ");drop table--"}
        )
        assert junk.status_code == status.HTTP_200_OK  # بی‌اثر، نه ۴۰۰

    def test_categories_endpoint_counts_open_listings_only(self) -> None:
        category = KindnessCategoryFactory()
        PublishedNeedListingFactory(category=category)
        KindnessListingFactory(category=category)  # draft شمرده نمی‌شود

        response = APIClient().get(reverse("kindness_wall:category-list"))

        rows = response.data["data"]
        mine = next(row for row in rows if row["slug"] == category.slug)
        assert mine["open_listings_count"] == 1
        assert "is_active" not in mine

    def test_stats_endpoint_shape(self) -> None:
        PublishedNeedListingFactory(urgency="urgent")
        fulfilled = PublishedNeedListingFactory()
        KindnessListing.all_objects.filter(pk=fulfilled.pk).update(
            status=ListingStatus.FULFILLED, fulfilled_at=timezone.now()
        )

        response = APIClient().get(reverse("kindness_wall:stats"))

        data = response.data["data"]
        assert data["open_listings"] == 1
        assert data["urgent_listings"] == 1
        assert data["fulfilled_30d"] == 1
        assert data["active_categories"] >= 1

    def test_stories_show_fulfilled_without_contacts(self) -> None:
        fulfilled = PublishedNeedListingFactory(title="چرخ خیاطی", contact_phone="09123334455")
        KindnessListing.all_objects.filter(pk=fulfilled.pk).update(
            status=ListingStatus.FULFILLED,
            fulfilled_at=timezone.now(),
            fulfillment_note="همسایه کمک کرد",
        )

        response = APIClient().get(reverse("kindness_wall:story-list"))

        rows = _results(response)
        assert [row["slug"] for row in rows] == [fulfilled.slug]
        assert rows[0]["fulfillment_note"] == "همسایه کمک کرد"
        for field in _CONTACT_FIELDS:
            assert field not in rows[0]
        assert "contact_channels" not in rows[0]

    def test_throttle_scopes_exist_in_settings(self) -> None:
        """conftest نرخ‌ها را در تست خالی می‌کند؛ پس source-of-truth را می‌خوانیم."""
        from importlib import import_module

        base = import_module("config.settings.base")
        rates = base.REST_FRAMEWORK["DEFAULT_THROTTLE_RATES"]
        assert rates["kindness_browse_anon"] == "60/min"
        assert rates["kindness_browse_user"] == "120/min"
        assert rates["kindness_offer_create"] == "20/hour"
        for gone in ("kindness_listing_create", "kindness_contact_reveal", "kindness_report"):
            assert gone not in rates, f"اسکوپ سیاست قدیمی {gone} باید حذف می‌شد"


class TestOfferEndpoints:
    def test_offer_requires_authentication(self) -> None:
        listing = PublishedNeedListingFactory()
        response = APIClient().post(
            reverse("kindness_wall:offer-create", kwargs={"slug": listing.slug}),
            {"message": "دارم"},
            format="json",
        )
        assert response.status_code in (status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN)

    def test_offer_flow_create_upsert_withdraw(self) -> None:
        listing = PublishedNeedListingFactory()
        user = UserFactory()
        client = APIClient()
        client.force_authenticate(user=user)

        first = client.post(
            reverse("kindness_wall:offer-create", kwargs={"slug": listing.slug}),
            {"message": "یک بسته لباس سالم دارم"},
            format="json",
        )
        assert first.status_code == status.HTTP_201_CREATED
        assert first.data["data"]["status"] == OfferStatus.NEW

        second = client.post(
            reverse("kindness_wall:offer-create", kwargs={"slug": listing.slug}),
            {"message": "دو بسته دارم"},
            format="json",
        )
        assert second.status_code == status.HTTP_200_OK
        assert second.data["data"]["id"] == first.data["data"]["id"]
        assert second.data["data"]["message"] == "دو بسته دارم"
        assert KindnessOffer.objects.filter(listing=listing, user=user).count() == 1

        withdrawn = client.delete(
            reverse("kindness_wall:offer-withdraw", kwargs={"offer_id": first.data["data"]["id"]})
        )
        assert withdrawn.status_code == status.HTTP_200_OK
        assert not KindnessOffer.objects.exists()

    def test_offer_on_draft_listing_is_404(self) -> None:
        draft = KindnessListingFactory()
        client = APIClient()
        client.force_authenticate(user=UserFactory())
        response = client.post(
            reverse("kindness_wall:offer-create", kwargs={"slug": draft.slug}),
            {"message": "هستی؟"},
            format="json",
        )
        assert response.status_code == status.HTTP_404_NOT_FOUND

    def test_detail_reveals_my_offer_status_to_owner(self) -> None:
        listing = PublishedNeedListingFactory()
        user = UserFactory()
        KindnessOffer.objects.create(listing=listing, user=user)
        client = APIClient()
        client.force_authenticate(user=user)

        response = client.get(
            reverse("kindness_wall:listing-detail", kwargs={"slug": listing.slug})
        )

        assert response.data["data"]["my_offer_status"] == OfferStatus.NEW
        assert response.data["data"]["can_offer"] is True

    def test_detail_anonymous_has_no_offer_state(self) -> None:
        listing = PublishedNeedListingFactory()
        response = APIClient().get(
            reverse("kindness_wall:listing-detail", kwargs={"slug": listing.slug})
        )
        assert response.data["data"]["my_offer_status"] is None
        assert response.data["data"]["can_offer"] is False

    def test_my_offers_lists_only_mine_with_listing_context(self) -> None:
        listing = PublishedNeedListingFactory(title="کتری برقی")
        me = UserFactory()
        other = UserFactory()
        KindnessOffer.objects.create(listing=listing, user=me, message="دارم")
        KindnessOffer.objects.create(listing=listing, user=other)
        client = APIClient()
        client.force_authenticate(user=me)

        response = client.get(reverse("kindness_wall:my-offers"))

        rows = _results(response)
        assert len(rows) == 1
        assert rows[0]["listing_title"] == "کتری برقی"

    def test_cannot_withdraw_someone_elses_offer(self) -> None:
        listing = PublishedNeedListingFactory()
        owner = UserFactory()
        offer = KindnessOffer.objects.create(listing=listing, user=owner)
        client = APIClient()
        client.force_authenticate(user=UserFactory())

        response = client.delete(
            reverse("kindness_wall:offer-withdraw", kwargs={"offer_id": offer.pk})
        )

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert KindnessOffer.objects.filter(pk=offer.pk).exists()

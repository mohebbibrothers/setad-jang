"""Kindness Wall Phase 5 final polish, edge-case, and performance contracts.

این تست‌ها guard نهایی اپ دیوار مهربانی هستند:
- serializerهای پرترافیک بعد از selector مناسب نباید N+1 query تولید کنند.
- privacy boundary نمایش شماره تماس باید سخت‌گیرانه بماند.
- workflowهای مالک مثل بستن آگهی و bookmark dashboard باید کامل باشند.
- edge-caseهای tree/category و location payload باید regression نشوند.
"""

from __future__ import annotations

from decimal import Decimal

import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient

from apps.kindness_wall import selectors
from apps.kindness_wall.choices import ListingStatus, ListingType
from apps.kindness_wall.models import KindnessBookmark, KindnessContactReveal, KindnessMatch
from apps.kindness_wall.serializers import (
    KindnessAdminMatchSerializer,
    KindnessBookmarkSerializer,
    KindnessListingListSerializer,
)
from tests.factories import AdminUserFactory
from tests.factories.kindness_wall import (
    KindnessCategoryFactory,
    KindnessUserFactory,
    PublishedNeedListingFactory,
    PublishedOfferListingFactory,
)

pytestmark = pytest.mark.django_db


def _client_for(user) -> APIClient:
    """Return authenticated API client."""
    client = APIClient()
    client.force_authenticate(user=user)
    return client


class TestKindnessQueryPerformanceContracts:
    """N+1 regression tests for Kindness Wall selectors/serializers."""

    def test_public_listing_card_serializer_does_not_query_after_public_selector(self) -> None:
        category = KindnessCategoryFactory(title="کارآفرینی")
        PublishedNeedListingFactory(category=category, title="کمک برای ساخت رزومه")
        PublishedOfferListingFactory(category=category, title="مشاوره شغلی رایگان")

        listings = list(selectors.get_public_listings())

        with CaptureQueriesContext(connection) as captured:
            data = KindnessListingListSerializer(listings, many=True).data

        assert len(data) == 2
        assert len(captured) == 0

    def test_user_bookmark_serializer_does_not_query_after_bookmark_selector(self) -> None:
        user = KindnessUserFactory()
        listing = PublishedOfferListingFactory(title="کمک آموزشی رایگان")
        KindnessBookmark.objects.create(user=user, listing=listing)

        bookmarks = list(selectors.get_user_bookmarks(user_id=user.pk))

        with CaptureQueriesContext(connection) as captured:
            data = KindnessBookmarkSerializer(bookmarks, many=True).data

        assert len(data) == 1
        assert data[0]["listing"]["id"] == listing.pk
        assert len(captured) == 0

    def test_admin_match_serializer_does_not_query_after_admin_match_selector(self) -> None:
        category = KindnessCategoryFactory(title="مهارت")
        source = PublishedNeedListingFactory(category=category, title="نیاز به مربی پایتون")
        target = PublishedOfferListingFactory(category=category, title="آموزش پایتون رایگان")
        KindnessMatch.objects.create(source_listing=source, target_listing=target, score=88)

        matches = list(selectors.get_admin_matches())

        with CaptureQueriesContext(connection) as captured:
            data = KindnessAdminMatchSerializer(matches, many=True).data

        assert len(data) == 1
        assert data[0]["source_listing"]["id"] == source.pk
        assert data[0]["target_listing"]["id"] == target.pk
        assert len(captured) == 0


class TestKindnessFinalPrivacyAndWorkflowContracts:
    """Final user-facing workflow and privacy guards."""

    def test_listing_owner_cannot_use_reveal_contact_to_inflate_contact_metrics(self) -> None:
        listing = PublishedNeedListingFactory(contact_phone_snapshot="+989120000000")

        response = _client_for(listing.owner).post(reverse("kindness_wall:listing-reveal-contact", kwargs={"slug": listing.slug}))

        assert response.status_code == status.HTTP_403_FORBIDDEN
        assert KindnessContactReveal.objects.count() == 0

    def test_authenticated_non_owner_can_still_reveal_contact(self) -> None:
        listing = PublishedNeedListingFactory(contact_phone_snapshot="+989120000001")
        viewer = KindnessUserFactory()

        response = _client_for(viewer).post(reverse("kindness_wall:listing-reveal-contact", kwargs={"slug": listing.slug}))

        assert response.status_code == status.HTTP_200_OK
        assert response.data["data"]["phone_number"] == "+989120000001"
        assert KindnessContactReveal.objects.filter(listing=listing, viewer=viewer).exists()

    def test_owner_can_close_published_listing_without_soft_deleting_it(self) -> None:
        listing = PublishedOfferListingFactory()

        response = _client_for(listing.owner).post(reverse("kindness_wall:user-listing-close", kwargs={"listing_id": listing.pk}))

        assert response.status_code == status.HTTP_200_OK
        listing.refresh_from_db()
        assert listing.status == ListingStatus.CLOSED
        assert listing.is_active is True

    def test_user_bookmark_dashboard_returns_saved_listing_cards(self) -> None:
        user = KindnessUserFactory()
        listing = PublishedOfferListingFactory(title="کمک به طراحی سایت")
        KindnessBookmark.objects.create(user=user, listing=listing)

        response = _client_for(user).get(reverse("kindness_wall:user-bookmark-list"))

        assert response.status_code == status.HTTP_200_OK
        results = response.data["data"]["results"]
        assert len(results) == 1
        assert results[0]["listing"]["id"] == listing.pk
        assert "contact_phone_snapshot" not in results[0]["listing"]


class TestKindnessFinalEdgeCases:
    """Final edge cases for professional completeness."""

    def test_create_listing_accepts_precise_location_and_returns_it_to_owner_only(self) -> None:
        user = KindnessUserFactory()
        category = KindnessCategoryFactory(title="حمل‌ونقل")

        response = _client_for(user).post(
            reverse("kindness_wall:user-listing-list-create"),
            data={
                "listing_type": ListingType.NEED_HELP,
                "category_id": category.pk,
                "title": "نیاز به کمک حمل وسایل",
                "description": "برای جابه‌جایی وسایل خیریه نیاز به کمک دارم",
                "latitude": "35.700000",
                "longitude": "51.400000",
            },
            format="json",
        )

        assert response.status_code == status.HTTP_201_CREATED
        assert Decimal(response.data["data"]["latitude"]) == Decimal("35.700000")
        assert Decimal(response.data["data"]["longitude"]) == Decimal("51.400000")

    def test_admin_cannot_deactivate_category_with_published_listing(self) -> None:
        category = KindnessCategoryFactory(title="دسته فعال")
        PublishedNeedListingFactory(category=category)

        response = _client_for(AdminUserFactory()).delete(reverse("kindness_wall:admin-category-detail", kwargs={"category_id": category.pk}))

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        category.refresh_from_db()
        assert category.is_active is True

    def test_public_listing_detail_never_exposes_exact_coordinates_or_raw_phone(self) -> None:
        listing = PublishedNeedListingFactory(latitude=Decimal("35.700000"), longitude=Decimal("51.400000"), contact_phone_snapshot="+989120000002")

        response = APIClient().get(reverse("kindness_wall:listing-detail", kwargs={"slug": listing.slug}))

        assert response.status_code == status.HTTP_200_OK
        payload = response.data["data"]
        assert "contact_phone_snapshot" not in payload
        assert "latitude" not in payload
        assert "longitude" not in payload

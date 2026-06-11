"""
Kindness Wall Phase 1 foundation tests.

These tests verify the full-pro domain foundation: tree categories, profile
requirements, listing workflow, Persian matching, materialized matches, duplicate
detection, and public serializers hiding phone numbers.
"""

from __future__ import annotations

import pytest
from django.db import IntegrityError, transaction

from apps.kindness_wall.choices import ListingStatus, ListingType
from apps.kindness_wall.matching import calculate_match_score, normalize_text, tokenize
from apps.kindness_wall.models import KindnessCategory, KindnessMatch
from apps.kindness_wall.serializers import (
    KindnessListingDetailSerializer,
    KindnessListingListSerializer,
)
from apps.kindness_wall.services import (
    KindnessProfileIncompleteError,
    approve_listing,
    create_listing,
    detect_duplicate_candidates,
    submit_listing_for_review,
)
from tests.factories import UserFactory
from tests.factories.kindness_wall import (
    KindnessCategoryFactory,
    KindnessListingFactory,
    KindnessUserFactory,
    PublishedOfferListingFactory,
)

pytestmark = pytest.mark.django_db


class TestKindnessCategoryTree:
    """Tree category contracts."""

    def test_category_generates_slug_path_and_depth(self) -> None:
        root = KindnessCategoryFactory(title="مشاغل")
        child = KindnessCategoryFactory(title="برنامه‌نویسی", parent=root)

        assert root.path == f"/{root.slug}/"
        assert root.depth == 0
        assert child.depth == 1
        assert child.path == f"{root.path}{child.slug}/"

    def test_category_title_unique_per_parent(self) -> None:
        root = KindnessCategoryFactory(title="لوازم")
        KindnessCategoryFactory(title="آشپزخانه", parent=root)

        with pytest.raises(IntegrityError), transaction.atomic():
            KindnessCategory.objects.create(title="آشپزخانه", parent=root)


class TestKindnessListingFoundation:
    """Listing creation and workflow contracts."""

    def test_listing_requires_complete_identity_profile(self) -> None:
        user = UserFactory(first_name="", last_name="")
        category = KindnessCategoryFactory()

        with pytest.raises(KindnessProfileIncompleteError):
            create_listing(
                owner=user,
                listing_type=ListingType.NEED_HELP,
                category=category,
                title="نیاز به کمک",
                description="توضیح کامل نیاز به کمک",
            )

    def test_create_listing_snapshots_owner_and_extracts_tags(self) -> None:
        user = KindnessUserFactory(first_name="علی", last_name="رضایی")
        category = KindnessCategoryFactory(title="مشاغل")

        listing = create_listing(
            owner=user,
            listing_type=ListingType.NEED_HELP,
            category=category,
            title="برنامه نویس فول استک لازم دارم",
            description="برای سایت خیریه دنبال طراح سایت و توسعه دهنده هستم",
        )

        assert listing.status == ListingStatus.DRAFT
        assert listing.owner_full_name_snapshot == "علی رضایی"
        assert listing.contact_phone_snapshot == user.phone_number
        assert listing.owner_province_snapshot == "تهران"
        assert listing.listing_tags.count() > 0

    def test_submit_and_approve_listing_publishes_and_generates_matches(self) -> None:
        category = KindnessCategoryFactory(title="مشاغل")
        need_owner = KindnessUserFactory()
        offer = PublishedOfferListingFactory(
            category=category,
            title="طراح سایت فول استک هستم",
            description="برنامه نویس و طراح سایت فول استک برای کمک داوطلبانه",
        )
        need = create_listing(
            owner=need_owner,
            listing_type=ListingType.NEED_HELP,
            category=category,
            title="برنامه نویس فول استک نیاز دارم",
            description="دنبال طراح سایت برای پروژه خیریه هستم",
        )
        submit_listing_for_review(listing=need, user=need_owner)

        approve_listing(listing=need, admin=KindnessUserFactory())

        need.refresh_from_db()
        assert need.status == ListingStatus.PUBLISHED
        match = KindnessMatch.objects.get(source_listing=need, target_listing=offer)
        assert match.score >= 40
        assert "same_category" in match.reason_codes


class TestKindnessMatchingEngine:
    """Persian matching engine contracts."""

    def test_normalize_and_tokenize_expand_persian_synonyms(self) -> None:
        assert normalize_text("برنامه‌ نویسِ فول-استک") == "برنامه نویس فول استک"
        tokens = tokenize("دنبال برنامه نویس فول استک سایت هستم")

        assert "developer" in tokens
        assert "fullstack" in tokens

    def test_match_score_prefers_opposite_type_same_category_and_city(self) -> None:
        category = KindnessCategoryFactory(title="مشاغل")
        need = KindnessListingFactory(
            listing_type=ListingType.NEED_HELP,
            category=category,
            title="برنامه نویس فول استک نیاز دارم",
            description="برای سایت مردم نیاز به توسعه دهنده دارم",
            status=ListingStatus.PUBLISHED,
        )
        offer = KindnessListingFactory(
            listing_type=ListingType.OFFER_HELP,
            category=category,
            title="طراح سایت فول استک هستم",
            description="برنامه نویس داوطلب برای طراحی سایت",
            status=ListingStatus.PUBLISHED,
        )

        result = calculate_match_score(source=need, target=offer)

        assert result.score >= 60
        assert result.breakdown["type_complementarity"] == 30
        assert result.breakdown["category_similarity"] == 25
        assert "تطابق" in result.explanation

    def test_duplicate_detection_records_candidate(self) -> None:
        owner = KindnessUserFactory()
        category = KindnessCategoryFactory(title="مشاغل")
        existing = KindnessListingFactory(
            owner=owner,
            category=category,
            listing_type=ListingType.NEED_HELP,
            title="برنامه نویس فول استک نیاز دارم",
            description="برای سایت خیریه برنامه نویس فول استک نیاز دارم",
        )
        listing = KindnessListingFactory(
            owner=owner,
            category=category,
            listing_type=ListingType.NEED_HELP,
            title="برنامه نویس فول استک نیاز دارم",
            description="برای سایت خیریه برنامه نویس فول استک نیاز دارم",
        )

        duplicates = detect_duplicate_candidates(listing=listing, threshold=20)

        assert duplicates
        assert duplicates[0].candidate_listing_id == existing.pk


class TestKindnessPublicSerializers:
    """Public serializer privacy contracts."""

    def test_public_list_and_detail_do_not_expose_phone_number(self) -> None:
        listing = PublishedOfferListingFactory(contact_phone_snapshot="+989120000000")

        list_payload = KindnessListingListSerializer(listing).data
        detail_payload = KindnessListingDetailSerializer(listing).data

        assert "contact_phone_snapshot" not in list_payload
        assert "contact_phone_snapshot" not in detail_payload
        assert detail_payload["contact_available"] is True

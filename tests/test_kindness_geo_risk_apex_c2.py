"""Kindness Apex C2 geo matching and risk signal tests."""

from __future__ import annotations

from decimal import Decimal

import pytest

from apps.kindness_wall.choices import RiskSeverity, RiskSignalType
from apps.kindness_wall.matching import calculate_match_score
from apps.kindness_wall.models import KindnessContactReveal, KindnessRiskSignal
from apps.kindness_wall.services import evaluate_contact_reveal_risk, reveal_contact
from tests.factories.kindness_wall import (
    KindnessUserFactory,
    PublishedNeedListingFactory,
    PublishedOfferListingFactory,
)

pytestmark = pytest.mark.django_db


def test_geo_matching_boosts_nearby_listings_with_reason_code() -> None:
    """Listings with close coordinates should receive geo boost and reason code."""
    source = PublishedNeedListingFactory(
        title="نیاز به مربی پایتون",
        description="برای آموزش برنامه نویسی کمک می‌خواهم",
        latitude=Decimal("35.700000"),
        longitude=Decimal("51.400000"),
    )
    target = PublishedOfferListingFactory(
        category=source.category,
        title="آموزش پایتون رایگان",
        description="برای کمک آموزشی آماده‌ام",
        latitude=Decimal("35.701000"),
        longitude=Decimal("51.401000"),
    )

    score = calculate_match_score(source=source, target=target)

    assert score.breakdown["location_similarity"] == 20
    assert "nearby_5km" in score.reason_codes
    assert "فاصله مکانی بسیار نزدیک" in score.explanation


def test_geo_matching_falls_back_to_city_when_coordinates_missing() -> None:
    """City/province fallback must remain intact when coordinates are unavailable."""
    source = PublishedNeedListingFactory(city="تهران", province="تهران")
    target = PublishedOfferListingFactory(category=source.category, city="تهران", province="تهران")

    score = calculate_match_score(source=source, target=target)

    assert score.breakdown["location_similarity"] == 15
    assert "same_city" in score.reason_codes


def test_contact_reveal_velocity_creates_risk_signal() -> None:
    """Fast repeated contact reveals by one viewer should generate risk signal."""
    viewer = KindnessUserFactory()
    listings = [PublishedNeedListingFactory() for _ in range(5)]

    for listing in listings:
        reveal_contact(listing=listing, viewer=viewer)

    signal = KindnessRiskSignal.objects.get(signal_type=RiskSignalType.CONTACT_REVEAL_VELOCITY)
    assert signal.user == viewer
    assert signal.severity == RiskSeverity.MEDIUM
    assert signal.metadata["viewer_reveal_count"] == 5


def test_listing_contact_spike_creates_high_risk_signal() -> None:
    """Many reveals on one listing should create listing spike signal."""
    listing = PublishedNeedListingFactory()
    for _ in range(10):
        KindnessContactReveal.objects.create(
            listing=listing,
            viewer=KindnessUserFactory(),
            listing_owner=listing.owner,
            phone_snapshot=listing.contact_phone_snapshot,
        )
    latest = listing.contact_reveals.order_by("-created_at").first()

    signals = evaluate_contact_reveal_risk(reveal=latest)

    assert any(signal.signal_type == RiskSignalType.LISTING_CONTACT_SPIKE for signal in signals)
    signal = KindnessRiskSignal.objects.get(signal_type=RiskSignalType.LISTING_CONTACT_SPIKE)
    assert signal.severity == RiskSeverity.HIGH
    assert signal.metadata["listing_reveal_count"] == 10

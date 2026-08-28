"""Madadkar C4 campaign intelligence tests."""

from __future__ import annotations

import pytest
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken

from apps.madadkar.choices import (
    FinancialAdjustmentType,
    MadadkarRiskSeverity,
    MadadkarRiskSignalType,
)
from apps.madadkar.selectors import get_campaign_intelligence, get_madadkar_intelligence_overview
from apps.madadkar.services import (
    apply_financial_adjustment,
    approve_financial_adjustment,
    approve_payment_refund,
    complete_payment_refund,
    create_financial_adjustment,
    create_madadkar_risk_signal,
    request_payment_refund,
)
from tests.factories.auth import AdminUserFactory, UserFactory
from tests.factories.madadkar import (
    FailedPaymentFactory,
    PaidParticipationFactory,
    PublishedCampaignFactory,
    SuccessPaymentFactory,
)

pytestmark = pytest.mark.django_db


def _admin_client(admin_user=None) -> APIClient:
    """Build a JWT-authenticated admin client."""
    user = admin_user or AdminUserFactory()
    client = APIClient()
    refresh = RefreshToken.for_user(user)
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {refresh.access_token!s}")
    return client


def _success_payment(*, campaign, user=None, amount: int = 20_000):
    """Create one successful payment bound to a campaign."""
    participation = PaidParticipationFactory(
        campaign=campaign,
        user=user or UserFactory(),
        share_count=1,
        share_price_snapshot=amount,
        total_amount=amount,
    )
    return SuccessPaymentFactory(
        participation=participation, user=participation.user, amount=amount
    )


def test_campaign_intelligence_computes_refund_adjusted_financials_and_health() -> None:
    """Campaign intelligence should expose net metrics, funnel, trend, and risk health."""
    campaign = PublishedCampaignFactory(total_amount=100_000, total_shares=10)
    user = UserFactory()
    first_payment = _success_payment(campaign=campaign, user=user, amount=40_000)
    _success_payment(campaign=campaign, user=user, amount=10_000)
    FailedPaymentFactory(
        participation=PaidParticipationFactory(campaign=campaign, total_amount=5_000), amount=5_000
    )
    refund = request_payment_refund(
        payment=first_payment, amount=5_000, idempotency_key="intel-refund-1"
    )
    complete_payment_refund(refund=approve_payment_refund(refund=refund))
    adjustment = create_financial_adjustment(
        campaign=campaign,
        payment=first_payment,
        amount=2_000,
        adjustment_type=FinancialAdjustmentType.CREDIT,
        reason="کمک آفلاین ثبت‌شده",
    )
    apply_financial_adjustment(adjustment=approve_financial_adjustment(adjustment=adjustment))
    create_madadkar_risk_signal(
        signal_type=MadadkarRiskSignalType.HIGH_AMOUNT_NEW_USER,
        severity=MadadkarRiskSeverity.HIGH,
        user=first_payment.user,
        campaign=campaign,
        payment=first_payment,
    )
    campaign.refresh_from_db()

    intelligence = get_campaign_intelligence(campaign=campaign, days=7)

    assert intelligence["financials"]["gross_amount"] == 50_000
    assert intelligence["financials"]["completed_refund_amount"] == 5_000
    assert intelligence["financials"]["applied_adjustment_delta"] == 2_000
    assert intelligence["financials"]["net_amount"] == 47_000
    assert intelligence["financials"]["net_progress_percent"] == 47.0
    assert intelligence["funnel"]["successful_payments"] == 2
    assert intelligence["funnel"]["failed_payments"] == 1
    assert intelligence["donor_concentration"]["is_concentrated"] is True
    assert intelligence["risk"]["open_risk_signals"] == 1
    assert "top_donor_dependency" in intelligence["health"]["flags"]
    assert len(intelligence["daily_trend"]) == 7
    assert sum(day["net_amount"] for day in intelligence["daily_trend"]) >= 47_000


def test_campaign_intelligence_estimates_completion_velocity() -> None:
    """Velocity block should estimate completion date from daily net average."""
    campaign = PublishedCampaignFactory(total_amount=100_000, total_shares=10)
    _success_payment(campaign=campaign, amount=20_000)
    campaign.purchased_amount = 20_000
    campaign.save(update_fields=["purchased_amount", "updated_at"])

    intelligence = get_campaign_intelligence(campaign=campaign, days=10)

    assert intelligence["velocity"]["average_daily_net_amount"] > 0
    assert intelligence["velocity"]["estimated_completion_days"] is not None
    assert intelligence["velocity"]["estimated_completion_date"] is not None


def test_intelligence_overview_lists_weakest_and_strongest_campaigns() -> None:
    """Portfolio overview should summarize active campaign health."""
    weak_campaign = PublishedCampaignFactory(title="ضعیف", total_amount=100_000, total_shares=10)
    strong_campaign = PublishedCampaignFactory(title="قوی", total_amount=100_000, total_shares=10)
    _success_payment(campaign=strong_campaign, amount=50_000)
    create_madadkar_risk_signal(
        signal_type=MadadkarRiskSignalType.PAYMENT_FAILURE_SPIKE,
        severity=MadadkarRiskSeverity.HIGH,
        campaign=weak_campaign,
    )

    overview = get_madadkar_intelligence_overview(days=30)

    assert overview["portfolio"]["published_campaigns"] >= 2
    assert overview["portfolio"]["total_open_risk_signals"] == 1
    assert overview["weakest_campaigns"]
    assert overview["strongest_campaigns"]


def test_admin_campaign_intelligence_endpoint_returns_payload() -> None:
    """Admin campaign intelligence endpoint should expose selector payload."""
    campaign = PublishedCampaignFactory(total_amount=100_000, total_shares=10)
    _success_payment(campaign=campaign, amount=25_000)
    client = _admin_client()

    response = client.get(
        reverse("madadkar:admin-campaign-intelligence", kwargs={"campaign_id": campaign.pk}),
        data={"days": 5},
    )

    assert response.status_code == status.HTTP_200_OK
    assert response.data["data"]["campaign_id"] == campaign.pk
    assert response.data["data"]["window_days"] == 5
    assert response.data["data"]["financials"]["gross_amount"] == 25_000


def test_admin_intelligence_overview_endpoint_returns_portfolio() -> None:
    """Admin overview endpoint should expose portfolio intelligence."""
    campaign = PublishedCampaignFactory(total_amount=100_000, total_shares=10)
    _success_payment(campaign=campaign, amount=25_000)
    client = _admin_client()

    response = client.get(reverse("madadkar:admin-intelligence-overview"), data={"days": 5})

    assert response.status_code == status.HTTP_200_OK
    assert response.data["data"]["window_days"] == 5
    assert response.data["data"]["portfolio"]["published_campaigns"] >= 1

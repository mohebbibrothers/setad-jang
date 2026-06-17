"""Madadkar C8 public transparency layer tests."""

from __future__ import annotations

import pytest
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient

from apps.madadkar.choices import FinancialAdjustmentType
from apps.madadkar.selectors import get_public_campaign_transparency
from apps.madadkar.services import (
    apply_financial_adjustment,
    approve_campaign_disbursement,
    approve_financial_adjustment,
    approve_payment_refund,
    complete_payment_refund,
    issue_donation_receipt_for_payment,
    mark_campaign_disbursement_paid,
    request_campaign_disbursement,
    request_payment_refund,
)
from tests.factories.auth import UserFactory
from tests.factories.madadkar import (
    CampaignFactory,
    PaidParticipationFactory,
    PublishedCampaignFactory,
    SuccessPaymentFactory,
)

pytestmark = pytest.mark.django_db


def _success_payment(*, campaign, user=None, amount: int = 50_000):
    """Create successful payment tied to a campaign."""
    participation = PaidParticipationFactory(
        campaign=campaign,
        user=user or UserFactory(),
        share_count=1,
        share_price_snapshot=amount,
        total_amount=amount,
    )
    return SuccessPaymentFactory(participation=participation, user=participation.user, amount=amount)


def test_public_transparency_snapshot_is_refund_adjustment_and_disbursement_aware() -> None:
    """Public transparency should expose net public-safe campaign finances."""
    campaign = PublishedCampaignFactory(total_amount=200_000, total_shares=10)
    first = _success_payment(campaign=campaign, amount=80_000)
    second = _success_payment(campaign=campaign, amount=40_000)
    issue_donation_receipt_for_payment(payment=first)
    issue_donation_receipt_for_payment(payment=second)
    refund = request_payment_refund(payment=first, amount=10_000, idempotency_key="trans-refund-1")
    complete_payment_refund(refund=approve_payment_refund(refund=refund))
    adjustment = create_adjustment_for_transparency(campaign=campaign, payment=second, amount=5_000)
    apply_financial_adjustment(adjustment=approve_financial_adjustment(adjustment=adjustment))
    campaign.refresh_from_db()
    disbursement = request_campaign_disbursement(
        campaign=campaign,
        amount=30_000,
        recipient_name="مقصد عمومی",
        purpose="تخصیص بسته حمایتی",
    )
    mark_campaign_disbursement_paid(
        disbursement=approve_campaign_disbursement(disbursement=disbursement),
        bank_tracking_reference="PUBLIC-BANK-1",
    )

    transparency = get_public_campaign_transparency(campaign=campaign)

    assert transparency["gross_raised_amount"] == 120_000
    assert transparency["completed_refund_amount"] == 10_000
    assert transparency["applied_adjustment_delta"] == 5_000
    assert transparency["net_raised_amount"] == 115_000
    assert transparency["paid_disbursement_amount"] == 30_000
    assert transparency["committed_disbursement_amount"] == 30_000
    assert transparency["remaining_disbursable_amount"] == 85_000
    assert transparency["receipt_count"] == 2
    assert transparency["successful_payment_count"] == 2
    assert "donor" not in str(transparency).lower()


def create_adjustment_for_transparency(*, campaign, payment, amount: int):
    """Create debit/credit adjustment helper for transparency tests."""
    from apps.madadkar.services import create_financial_adjustment

    return create_financial_adjustment(
        campaign=campaign,
        payment=payment,
        amount=amount,
        adjustment_type=FinancialAdjustmentType.CREDIT,
        reason="شفافیت کمک آفلاین",
    )


def test_public_transparency_endpoint_returns_safe_payload() -> None:
    """Public endpoint should return transparency payload without authentication."""
    campaign = PublishedCampaignFactory(total_amount=100_000, total_shares=10)
    payment = _success_payment(campaign=campaign, amount=25_000)
    issue_donation_receipt_for_payment(payment=payment)
    client = APIClient()

    response = client.get(reverse("madadkar:public-campaign-transparency", kwargs={"slug": campaign.slug}))

    assert response.status_code == status.HTTP_200_OK
    data = response.data["data"]
    assert data["campaign_slug"] == campaign.slug
    assert data["gross_raised_amount"] == 25_000
    assert data["net_raised_amount"] == 25_000
    assert data["receipt_count"] == 1
    assert "donor_snapshot" not in str(data)
    assert "email" not in str(data).lower()


def test_public_transparency_hidden_campaign_returns_404() -> None:
    """Draft/hidden campaigns must not leak transparency information."""
    campaign = CampaignFactory(is_visible=False)
    client = APIClient()

    response = client.get(reverse("madadkar:public-campaign-transparency", kwargs={"slug": campaign.slug}))

    assert response.status_code == status.HTTP_404_NOT_FOUND

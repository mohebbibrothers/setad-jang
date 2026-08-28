"""Madadkar C2 refund and financial-adjustment workflow tests."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken

from apps.audit_logs import actions as audit_actions
from apps.madadkar.choices import (
    FinancialAdjustmentStatus,
    FinancialAdjustmentType,
    ParticipationStatus,
    RefundReason,
    RefundStatus,
)
from apps.madadkar.models import CampaignFinancialAdjustment, PaymentRefund
from apps.madadkar.selectors import get_campaign_financial_control_summary
from apps.madadkar.services import (
    FinancialAdjustmentWorkflowError,
    RefundWorkflowError,
    apply_financial_adjustment,
    approve_financial_adjustment,
    approve_payment_refund,
    complete_payment_refund,
    create_financial_adjustment,
    request_payment_refund,
)
from tests.factories.auth import AdminUserFactory
from tests.factories.madadkar import (
    PaidParticipationFactory,
    PublishedCampaignFactory,
    SuccessPaymentFactory,
)

pytestmark = pytest.mark.django_db

_AUDIT_TASK_PATH = "apps.audit_logs.tasks.create_audit_log_task"


def _admin_client(admin_user=None) -> APIClient:
    """Build JWT-authenticated admin API client."""
    user = admin_user or AdminUserFactory()
    client = APIClient()
    refresh = RefreshToken.for_user(user)
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {refresh.access_token!s}")
    return client


def _successful_payment(*, amount: int = 20_000):
    """Create a successful payment with campaign counters aligned."""
    campaign = PublishedCampaignFactory(total_amount=100_000, total_shares=10)
    participation = PaidParticipationFactory(
        campaign=campaign,
        share_count=2,
        share_price_snapshot=10_000,
        total_amount=amount,
    )
    payment = SuccessPaymentFactory(
        participation=participation, amount=amount, user=participation.user
    )
    campaign.purchased_shares = participation.share_count
    campaign.purchased_amount = amount
    campaign.participant_count = 1
    campaign.save(
        update_fields=["purchased_shares", "purchased_amount", "participant_count", "updated_at"]
    )
    return campaign, participation, payment


def test_partial_refund_workflow_reduces_net_campaign_amount() -> None:
    """Approved/completed partial refund should reduce effective campaign accounting."""
    campaign, participation, payment = _successful_payment(amount=20_000)

    refund = request_payment_refund(
        payment=payment,
        amount=5_000,
        reason=RefundReason.USER_REQUEST,
        idempotency_key="refund-partial-1",
    )
    approved = approve_payment_refund(refund=refund)
    completed = complete_payment_refund(refund=approved, provider_ref_id="RF-1")

    campaign.refresh_from_db()
    participation.refresh_from_db()
    assert completed.status == RefundStatus.COMPLETED
    assert completed.provider_ref_id == "RF-1"
    assert participation.status == ParticipationStatus.PAID
    assert campaign.purchased_shares == 2
    assert campaign.purchased_amount == 15_000


def test_full_refund_releases_shares_and_marks_participation_refunded() -> None:
    """Full refund should release reserved/sold shares from campaign counters."""
    campaign, participation, payment = _successful_payment(amount=20_000)

    refund = request_payment_refund(
        payment=payment, amount=20_000, reason=RefundReason.ADMIN_CORRECTION
    )
    complete_payment_refund(refund=approve_payment_refund(refund=refund))

    campaign.refresh_from_db()
    participation.refresh_from_db()
    assert participation.status == ParticipationStatus.REFUNDED
    assert campaign.purchased_shares == 0
    assert campaign.purchased_amount == 0
    assert campaign.participant_count == 0


def test_refund_request_is_idempotent_and_prevents_over_refund() -> None:
    """Refund service should enforce idempotency and available refundable balance."""
    _campaign, _participation, payment = _successful_payment(amount=20_000)

    first = request_payment_refund(payment=payment, amount=10_000, idempotency_key="refund-key-1")
    second = request_payment_refund(payment=payment, amount=10_000, idempotency_key="refund-key-1")

    assert first.pk == second.pk
    with pytest.raises(RefundWorkflowError, match="مانده قابل بازپرداخت"):
        request_payment_refund(payment=payment, amount=15_000)


def test_financial_adjustment_workflow_applies_signed_delta() -> None:
    """Approved adjustment should affect campaign effective amount only after apply."""
    campaign, _participation, payment = _successful_payment(amount=20_000)

    adjustment = create_financial_adjustment(
        campaign=campaign,
        payment=payment,
        amount=3_000,
        adjustment_type=FinancialAdjustmentType.DEBIT,
        reason="اصلاح کارمزد دستی",
    )
    approved = approve_financial_adjustment(adjustment=adjustment)
    applied = apply_financial_adjustment(adjustment=approved)

    campaign.refresh_from_db()
    assert applied.status == FinancialAdjustmentStatus.APPLIED
    assert applied.signed_amount == -3_000
    assert campaign.purchased_amount == 17_000


def test_financial_adjustment_rejects_payment_from_other_campaign() -> None:
    """Adjustment linked payment must belong to the same campaign."""
    campaign, _participation, _payment = _successful_payment(amount=20_000)
    other_campaign, _other_participation, other_payment = _successful_payment(amount=10_000)

    with pytest.raises(FinancialAdjustmentWorkflowError, match="متعلق به این حرکت نیست"):
        create_financial_adjustment(
            campaign=campaign,
            payment=other_payment,
            amount=1_000,
            adjustment_type=FinancialAdjustmentType.CREDIT,
            reason=f"wrong campaign {other_campaign.pk}",
        )


def test_financial_control_summary_reports_refunds_and_adjustments() -> None:
    """Admin summary should expose gross, refunds, adjustment delta and net amount."""
    campaign, _participation, payment = _successful_payment(amount=20_000)
    refund = request_payment_refund(payment=payment, amount=5_000)
    complete_payment_refund(refund=approve_payment_refund(refund=refund))
    adjustment = create_financial_adjustment(
        campaign=campaign,
        amount=2_000,
        adjustment_type=FinancialAdjustmentType.CREDIT,
        reason="کمک ثبت‌شده آفلاین",
    )
    apply_financial_adjustment(adjustment=approve_financial_adjustment(adjustment=adjustment))
    campaign.refresh_from_db()

    summary = get_campaign_financial_control_summary(campaign=campaign)

    assert summary["gross_paid_amount"] == 20_000
    assert summary["completed_refund_amount"] == 5_000
    assert summary["applied_adjustment_delta"] == 2_000
    assert summary["net_effective_amount"] == 17_000


def test_admin_refund_api_creates_approves_and_completes_with_audit() -> None:
    """Admin refund API should orchestrate service workflow and audit each mutation."""
    admin = AdminUserFactory()
    _campaign, _participation, payment = _successful_payment(amount=20_000)
    client = _admin_client(admin)

    with patch(_AUDIT_TASK_PATH) as mock_task:
        mock_task.delay = MagicMock()
        create_response = client.post(
            reverse("madadkar:admin-refund-list-create"),
            data={
                "payment_id": payment.pk,
                "amount": 5_000,
                "reason": RefundReason.USER_REQUEST,
                "idempotency_key": "api-refund-1",
            },
            format="json",
        )
        refund_id = create_response.data["data"]["id"]
        approve_response = client.post(
            reverse(
                "madadkar:admin-refund-action", kwargs={"refund_id": refund_id, "action": "approve"}
            )
        )
        complete_response = client.post(
            reverse(
                "madadkar:admin-refund-action",
                kwargs={"refund_id": refund_id, "action": "complete"},
            ),
            data={"provider_ref_id": "API-RF-1"},
            format="json",
        )

    assert create_response.status_code == status.HTTP_201_CREATED
    assert approve_response.status_code == status.HTTP_200_OK
    assert complete_response.status_code == status.HTTP_200_OK
    assert PaymentRefund.objects.get(pk=refund_id).status == RefundStatus.COMPLETED
    called_actions = [call.kwargs.get("action") for call in mock_task.delay.call_args_list]
    assert audit_actions.MADADKAR_REFUND_REQUESTED in called_actions
    assert audit_actions.MADADKAR_REFUND_APPROVED in called_actions
    assert audit_actions.MADADKAR_REFUND_COMPLETED in called_actions


def test_admin_adjustment_api_applies_with_audit() -> None:
    """Admin adjustment API should create, approve, apply and audit the workflow."""
    admin = AdminUserFactory()
    campaign, _participation, payment = _successful_payment(amount=20_000)
    client = _admin_client(admin)

    with patch(_AUDIT_TASK_PATH) as mock_task:
        mock_task.delay = MagicMock()
        create_response = client.post(
            reverse("madadkar:admin-adjustment-list-create"),
            data={
                "campaign_id": campaign.pk,
                "payment_id": payment.pk,
                "adjustment_type": FinancialAdjustmentType.DEBIT,
                "amount": 1_000,
                "reason": "اصلاح گزارش مالی",
            },
            format="json",
        )
        adjustment_id = create_response.data["data"]["id"]
        approve_response = client.post(
            reverse(
                "madadkar:admin-adjustment-action",
                kwargs={"adjustment_id": adjustment_id, "action": "approve"},
            )
        )
        apply_response = client.post(
            reverse(
                "madadkar:admin-adjustment-action",
                kwargs={"adjustment_id": adjustment_id, "action": "apply"},
            )
        )

    assert create_response.status_code == status.HTTP_201_CREATED
    assert approve_response.status_code == status.HTTP_200_OK
    assert apply_response.status_code == status.HTTP_200_OK
    assert (
        CampaignFinancialAdjustment.objects.get(pk=adjustment_id).status
        == FinancialAdjustmentStatus.APPLIED
    )
    called_actions = [call.kwargs.get("action") for call in mock_task.delay.call_args_list]
    assert audit_actions.MADADKAR_ADJUSTMENT_CREATED in called_actions
    assert audit_actions.MADADKAR_ADJUSTMENT_APPROVED in called_actions
    assert audit_actions.MADADKAR_ADJUSTMENT_APPLIED in called_actions

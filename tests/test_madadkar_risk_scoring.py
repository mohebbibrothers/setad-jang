"""Madadkar C3 fraud/risk scoring tests."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken

from apps.audit_logs import actions as audit_actions
from apps.command_center.selectors import get_command_center_summary
from apps.madadkar.choices import (
    FinancialAdjustmentType,
    MadadkarRiskSeverity,
    MadadkarRiskSignalType,
    MadadkarRiskStatus,
    RefundReason,
)
from apps.madadkar.models import MadadkarRiskSignal
from apps.madadkar.services import (
    apply_financial_adjustment,
    approve_financial_adjustment,
    create_financial_adjustment,
    create_madadkar_risk_signal,
    evaluate_payment_risk,
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

_AUDIT_TASK_PATH = "apps.audit_logs.tasks.create_audit_log_task"


def _admin_client(admin_user=None) -> APIClient:
    """Build a JWT-authenticated admin client."""
    user = admin_user or AdminUserFactory()
    client = APIClient()
    refresh = RefreshToken.for_user(user)
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {refresh.access_token!s}")
    return client


def _success_payment(*, user=None, amount: int = 20_000, ip_address: str = "127.0.0.1"):
    """Create a successful payment with a paid participation."""
    campaign = PublishedCampaignFactory(total_amount=100_000_000, total_shares=10)
    participation = PaidParticipationFactory(
        campaign=campaign,
        user=user or UserFactory(),
        share_count=1,
        share_price_snapshot=amount,
        total_amount=amount,
    )
    payment = SuccessPaymentFactory(
        participation=participation,
        user=participation.user,
        amount=amount,
        ip_address=ip_address,
    )
    campaign.purchased_shares = 1
    campaign.purchased_amount = amount
    campaign.participant_count = 1
    campaign.save(
        update_fields=["purchased_shares", "purchased_amount", "participant_count", "updated_at"]
    )
    return campaign, participation, payment


def test_high_amount_new_user_payment_generates_risk_signal(settings) -> None:
    """A first successful high-value payment should be flagged for admin review."""
    settings.MADADKAR_RISK_HIGH_AMOUNT_NEW_USER_THRESHOLD = 50_000
    _campaign, _participation, payment = _success_payment(amount=100_000, ip_address="10.0.0.1")

    signals = evaluate_payment_risk(payment=payment)

    assert len(signals) == 1
    assert signals[0].signal_type == MadadkarRiskSignalType.HIGH_AMOUNT_NEW_USER
    assert signals[0].severity == MadadkarRiskSeverity.HIGH
    assert signals[0].status == MadadkarRiskStatus.OPEN
    assert signals[0].metadata["amount"] == 100_000


def test_payment_failure_spike_generates_risk_signal(settings) -> None:
    """Repeated failed payments in a short window should create risk signal."""
    settings.MADADKAR_RISK_PAYMENT_FAILURE_SPIKE_THRESHOLD = 3
    user = UserFactory()
    last_payment = None
    for _index in range(3):
        participation = PaidParticipationFactory(user=user, total_amount=10_000)
        last_payment = FailedPaymentFactory(participation=participation, user=user, amount=10_000)

    signals = evaluate_payment_risk(payment=last_payment)

    assert any(
        signal.signal_type == MadadkarRiskSignalType.PAYMENT_FAILURE_SPIKE for signal in signals
    )


def test_suspicious_ip_velocity_generates_risk_signal(settings) -> None:
    """One IP used by multiple users in a short window should be flagged."""
    settings.MADADKAR_RISK_IP_DISTINCT_USERS_THRESHOLD = 3
    ip_address = "192.0.2.10"
    last_payment = None
    for _index in range(3):
        _campaign, _participation, last_payment = _success_payment(
            amount=10_000, ip_address=ip_address
        )

    signals = evaluate_payment_risk(payment=last_payment)

    assert any(
        signal.signal_type == MadadkarRiskSignalType.SUSPICIOUS_IP_VELOCITY for signal in signals
    )


def test_refund_velocity_generates_risk_signal(settings) -> None:
    """Multiple refund requests by one user should be flagged."""
    settings.MADADKAR_RISK_REFUND_VELOCITY_THRESHOLD = 3
    user = UserFactory()
    last_refund = None
    for index in range(3):
        _campaign, _participation, payment = _success_payment(user=user, amount=20_000 + index)
        last_refund = request_payment_refund(
            payment=payment,
            amount=1_000,
            reason=RefundReason.USER_REQUEST,
            idempotency_key=f"risk-refund-{index}",
        )

    signals = list(last_refund.risk_signals.all())

    assert any(signal.signal_type == MadadkarRiskSignalType.REFUND_VELOCITY for signal in signals)


def test_large_financial_adjustment_generates_risk_signal(settings) -> None:
    """Large manual financial adjustments should be flagged after apply."""
    settings.MADADKAR_RISK_ADJUSTMENT_RATIO_THRESHOLD = 0.25
    campaign, _participation, payment = _success_payment(amount=20_000)
    adjustment = create_financial_adjustment(
        campaign=campaign,
        payment=payment,
        amount=10_000,
        adjustment_type=FinancialAdjustmentType.DEBIT,
        reason="اصلاح غیرعادی",
    )

    applied = apply_financial_adjustment(
        adjustment=approve_financial_adjustment(adjustment=adjustment)
    )

    assert applied.risk_signals.filter(
        signal_type=MadadkarRiskSignalType.ADJUSTMENT_ANOMALY
    ).exists()


def test_admin_can_review_risk_signal_with_audit() -> None:
    """Risk review endpoint should mutate through service and audit the action."""
    admin = AdminUserFactory()
    campaign, _participation, payment = _success_payment(amount=20_000)
    signal = create_madadkar_risk_signal(
        signal_type=MadadkarRiskSignalType.HIGH_AMOUNT_NEW_USER,
        severity=MadadkarRiskSeverity.HIGH,
        user=payment.user,
        campaign=campaign,
        payment=payment,
        description="test signal",
    )
    client = _admin_client(admin)

    with patch(_AUDIT_TASK_PATH) as mock_task:
        mock_task.delay = MagicMock()
        response = client.post(
            reverse("madadkar:admin-risk-signal-review", kwargs={"signal_id": signal.pk}),
            data={"status": MadadkarRiskStatus.ESCALATED, "review_note": "نیازمند بررسی مالی"},
            format="json",
        )

    assert response.status_code == status.HTTP_200_OK
    signal.refresh_from_db()
    assert signal.status == MadadkarRiskStatus.ESCALATED
    assert signal.reviewed_by == admin
    assert signal.review_note == "نیازمند بررسی مالی"
    called_actions = [call.kwargs.get("action") for call in mock_task.delay.call_args_list]
    assert audit_actions.MADADKAR_RISK_SIGNAL_REVIEWED in called_actions


def test_command_center_exposes_madadkar_open_risk_signals() -> None:
    """Unified command center should expose Madadkar open risk-signal count."""
    campaign, _participation, payment = _success_payment(amount=20_000)
    create_madadkar_risk_signal(
        signal_type=MadadkarRiskSignalType.HIGH_AMOUNT_NEW_USER,
        severity=MadadkarRiskSeverity.HIGH,
        user=payment.user,
        campaign=campaign,
        payment=payment,
    )

    summary = get_command_center_summary()

    assert summary["madadkar"]["open_risk_signals"] == 1
    assert MadadkarRiskSignal.objects.filter(status=MadadkarRiskStatus.OPEN).count() == 1

"""Madadkar C9 financial operations automation/control tests."""

from __future__ import annotations

from io import StringIO

import pytest
from django.core.management import call_command
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken

from apps.audit_logs import actions as audit_actions
from apps.audit_logs.models import AuditLog
from apps.madadkar.choices import (
    FinancialControlSeverity,
    MadadkarRiskSeverity,
    MadadkarRiskSignalType,
    PaymentStatus,
)
from apps.madadkar.models import MadadkarFinancialControlSnapshot
from apps.madadkar.services import (
    generate_financial_control_snapshot,
    request_campaign_disbursement,
)
from apps.madadkar.tasks import generate_financial_control_snapshot_task
from tests.factories.auth import AdminUserFactory, UserFactory
from tests.factories.madadkar import (
    FailedPaymentFactory,
    PaidParticipationFactory,
    PaymentFactory,
    PublishedCampaignFactory,
)

pytestmark = pytest.mark.django_db


def _admin_client(admin_user=None) -> APIClient:
    """Build JWT-authenticated admin client."""
    user = admin_user or AdminUserFactory()
    client = APIClient()
    refresh = RefreshToken.for_user(user)
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {refresh.access_token!s}")
    return client


def test_financial_control_snapshot_flags_risks_and_pending_operations(settings) -> None:
    """Snapshot should summarize stale payments, open risks, refunds and disbursement queues."""
    settings.MADADKAR_PAYMENT_TIMEOUT_MINUTES = 0
    campaign = PublishedCampaignFactory(total_amount=100_000, total_shares=10)
    campaign.purchased_amount = 100_000
    campaign.save(update_fields=["purchased_amount", "updated_at"])
    participation = PaidParticipationFactory(campaign=campaign, total_amount=10_000)
    PaymentFactory(participation=participation, user=participation.user, amount=10_000, status=PaymentStatus.PENDING)
    FailedPaymentFactory(participation=PaidParticipationFactory(campaign=campaign), amount=10_000)
    from apps.madadkar.services import create_madadkar_risk_signal

    create_madadkar_risk_signal(
        signal_type=MadadkarRiskSignalType.PAYMENT_FAILURE_SPIKE,
        severity=MadadkarRiskSeverity.HIGH,
        user=UserFactory(),
        campaign=campaign,
    )
    request_campaign_disbursement(
        campaign=campaign,
        amount=20_000,
        recipient_name="گروه مقصد",
        purpose="تخصیص عملیاتی",
    )

    snapshot = generate_financial_control_snapshot()

    assert snapshot.severity == FinancialControlSeverity.CRITICAL
    assert snapshot.controls["stale_pending_payments"] >= 1
    assert snapshot.controls["high_risk_signals"] == 1
    assert snapshot.controls["requested_disbursements"] == 1
    assert snapshot.summary["open_flags"] >= 3
    assert any(flag["key"] == "high_risk_signals" for flag in snapshot.flags)


def test_financial_control_snapshot_can_be_generated_by_task_and_command() -> None:
    """Celery task and management command should both generate snapshots."""
    task_result = generate_financial_control_snapshot_task.apply().get()
    output = StringIO()

    call_command("generate_madadkar_financial_control", stdout=output)

    assert task_result["snapshot_id"]
    assert "snapshot_id" in output.getvalue()
    assert MadadkarFinancialControlSnapshot.objects.count() == 2


def test_admin_financial_control_api_generate_list_latest_and_audit() -> None:
    """Admin API should generate, list, and fetch latest control snapshot with audit."""
    admin = AdminUserFactory()
    client = _admin_client(admin)

    generate_response = client.post(reverse("madadkar:admin-financial-control-generate"))
    snapshot_id = generate_response.data["data"]["id"]
    list_response = client.get(reverse("madadkar:admin-financial-control-list"))
    latest_response = client.get(reverse("madadkar:admin-financial-control-latest"))

    assert generate_response.status_code == status.HTTP_201_CREATED
    assert list_response.status_code == status.HTTP_200_OK
    assert latest_response.status_code == status.HTTP_200_OK
    assert latest_response.data["data"]["id"] == snapshot_id
    assert AuditLog.objects.filter(
        action=audit_actions.MADADKAR_FINANCIAL_CONTROL_GENERATED,
        resource_id=str(snapshot_id),
        user=admin,
    ).exists()

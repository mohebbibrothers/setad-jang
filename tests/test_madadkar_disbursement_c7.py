"""Madadkar C7 campaign disbursement/allocation ledger tests."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken

from apps.audit_logs import actions as audit_actions
from apps.madadkar.choices import DisbursementStatus
from apps.madadkar.models import CampaignDisbursement
from apps.madadkar.selectors import get_campaign_disbursable_summary
from apps.madadkar.services import (
    DisbursementWorkflowError,
    approve_campaign_disbursement,
    calculate_campaign_disbursable_amount,
    mark_campaign_disbursement_paid,
    reject_campaign_disbursement,
    request_campaign_disbursement,
)
from tests.factories.auth import AdminUserFactory
from tests.factories.madadkar import PublishedCampaignFactory

pytestmark = pytest.mark.django_db

_AUDIT_TASK_PATH = "apps.audit_logs.tasks.create_audit_log_task"


def _admin_client(admin_user=None) -> APIClient:
    """Build JWT-authenticated admin API client."""
    user = admin_user or AdminUserFactory()
    client = APIClient()
    refresh = RefreshToken.for_user(user)
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {refresh.access_token!s}")
    return client


def _funded_campaign(*, amount: int = 100_000):
    """Create campaign with net effective purchased amount for disbursement tests."""
    campaign = PublishedCampaignFactory(total_amount=amount, total_shares=10)
    campaign.purchased_amount = amount
    campaign.purchased_shares = 10
    campaign.participant_count = 3
    campaign.save(update_fields=["purchased_amount", "purchased_shares", "participant_count", "updated_at"])
    return campaign


def test_disbursement_workflow_commits_and_pays_amount() -> None:
    """Request → approve → paid should reserve and then record paid allocation."""
    admin = AdminUserFactory()
    campaign = _funded_campaign(amount=100_000)

    disbursement = request_campaign_disbursement(
        campaign=campaign,
        amount=40_000,
        recipient_name="گروه جهادی مقصد",
        recipient_identifier="ORG-1",
        recipient_bank_account="IR123",
        purpose="خرید بسته معیشتی",
        requested_by=admin,
        supporting_document={"file": "doc.pdf"},
    )
    assert disbursement.status == DisbursementStatus.REQUESTED
    assert calculate_campaign_disbursable_amount(campaign=campaign) == 60_000

    approved = approve_campaign_disbursement(disbursement=disbursement, reviewed_by=admin)
    paid = mark_campaign_disbursement_paid(
        disbursement=approved,
        paid_by=admin,
        bank_tracking_reference="BANK-TRACK-1",
    )

    assert paid.status == DisbursementStatus.PAID
    assert paid.bank_tracking_reference == "BANK-TRACK-1"
    assert paid.paid_at is not None
    assert calculate_campaign_disbursable_amount(campaign=campaign) == 60_000


def test_disbursement_prevents_over_allocation_and_releases_rejected_amount() -> None:
    """Disbursement service should prevent over-allocation and release rejected requests."""
    admin = AdminUserFactory()
    campaign = _funded_campaign(amount=50_000)
    first = request_campaign_disbursement(
        campaign=campaign,
        amount=40_000,
        recipient_name="مقصد اول",
        purpose="پرداخت اول",
        requested_by=admin,
    )

    with pytest.raises(DisbursementWorkflowError, match="مانده قابل تخصیص"):
        request_campaign_disbursement(
            campaign=campaign,
            amount=20_000,
            recipient_name="مقصد دوم",
            purpose="پرداخت دوم",
            requested_by=admin,
        )

    rejected = reject_campaign_disbursement(
        disbursement=first,
        reviewed_by=admin,
        rejection_reason="مدرک ناقص است.",
    )
    assert rejected.status == DisbursementStatus.REJECTED
    assert calculate_campaign_disbursable_amount(campaign=campaign) == 50_000


def test_campaign_disbursable_summary_reports_committed_paid_and_available() -> None:
    """Disbursable summary should expose allocation accounting clearly."""
    admin = AdminUserFactory()
    campaign = _funded_campaign(amount=100_000)
    paid = request_campaign_disbursement(
        campaign=campaign,
        amount=30_000,
        recipient_name="پرداخت‌شده",
        purpose="پرداخت",
        requested_by=admin,
    )
    mark_campaign_disbursement_paid(
        disbursement=approve_campaign_disbursement(disbursement=paid, reviewed_by=admin),
        paid_by=admin,
        bank_tracking_reference="BANK-1",
    )
    request_campaign_disbursement(
        campaign=campaign,
        amount=20_000,
        recipient_name="در انتظار",
        purpose="رزرو",
        requested_by=admin,
    )

    summary = get_campaign_disbursable_summary(campaign=campaign)

    assert summary["net_effective_amount"] == 100_000
    assert summary["committed_disbursement_amount"] == 50_000
    assert summary["paid_disbursement_amount"] == 30_000
    assert summary["disbursable_amount"] == 50_000


def test_admin_disbursement_api_full_workflow_with_audit() -> None:
    """Admin API should orchestrate create/approve/mark-paid and audit all sensitive actions."""
    admin = AdminUserFactory()
    campaign = _funded_campaign(amount=100_000)
    client = _admin_client(admin)

    with patch(_AUDIT_TASK_PATH) as mock_task:
        mock_task.delay = MagicMock()
        create_response = client.post(
            reverse("madadkar:admin-disbursement-list-create"),
            data={
                "campaign_id": campaign.pk,
                "amount": 45_000,
                "recipient_name": "مؤسسه مقصد",
                "recipient_identifier": "NID-1",
                "recipient_bank_account": "IR999",
                "purpose": "تخصیص مرحله اول",
                "supporting_document": {"doc_id": "support-1"},
            },
            format="json",
        )
        disbursement_id = create_response.data["data"]["id"]
        approve_response = client.post(
            reverse("madadkar:admin-disbursement-action", kwargs={"disbursement_id": disbursement_id, "action": "approve"}),
        )
        paid_response = client.post(
            reverse("madadkar:admin-disbursement-action", kwargs={"disbursement_id": disbursement_id, "action": "mark-paid"}),
            data={"bank_tracking_reference": "BANK-API-1"},
            format="json",
        )

    assert create_response.status_code == status.HTTP_201_CREATED
    assert approve_response.status_code == status.HTTP_200_OK
    assert paid_response.status_code == status.HTTP_200_OK
    assert CampaignDisbursement.objects.get(pk=disbursement_id).status == DisbursementStatus.PAID
    called_actions = [call.kwargs.get("action") for call in mock_task.delay.call_args_list]
    assert audit_actions.MADADKAR_DISBURSEMENT_REQUESTED in called_actions
    assert audit_actions.MADADKAR_DISBURSEMENT_APPROVED in called_actions
    assert audit_actions.MADADKAR_DISBURSEMENT_PAID in called_actions


def test_admin_disbursement_list_detail_and_disbursable_endpoint() -> None:
    """Admin read endpoints should expose disbursement rows and campaign availability."""
    campaign = _funded_campaign(amount=100_000)
    disbursement = request_campaign_disbursement(
        campaign=campaign,
        amount=10_000,
        recipient_name="مقصد",
        purpose="پرداخت",
    )
    client = _admin_client()

    list_response = client.get(reverse("madadkar:admin-disbursement-list-create"), data={"campaign": campaign.pk})
    detail_response = client.get(reverse("madadkar:admin-disbursement-detail", kwargs={"disbursement_id": disbursement.pk}))
    summary_response = client.get(reverse("madadkar:admin-campaign-disbursable", kwargs={"campaign_id": campaign.pk}))

    assert list_response.status_code == status.HTTP_200_OK
    assert list_response.data["data"]["count"] == 1
    assert detail_response.status_code == status.HTTP_200_OK
    assert detail_response.data["data"]["id"] == disbursement.pk
    assert summary_response.status_code == status.HTTP_200_OK
    assert summary_response.data["data"]["disbursable_amount"] == 90_000

"""Madadkar C5 verifiable donation receipt tests."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken

from apps.audit_logs import actions as audit_actions
from apps.madadkar.choices import PaymentStatus
from apps.madadkar.models import DonationReceipt
from apps.madadkar.services import issue_donation_receipt_for_payment, verify_donation_receipt
from tests.factories.auth import AdminUserFactory, UserFactory
from tests.factories.madadkar import (
    PaidParticipationFactory,
    PublishedCampaignFactory,
    SuccessPaymentFactory,
)

pytestmark = pytest.mark.django_db

_AUDIT_TASK_PATH = "apps.audit_logs.tasks.create_audit_log_task"


def _jwt_client(user) -> APIClient:
    """Build JWT-authenticated API client."""
    client = APIClient()
    refresh = RefreshToken.for_user(user)
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {refresh.access_token!s}")
    return client


def _success_payment(*, user=None, amount: int = 25_000):
    """Create a successful Madadkar payment eligible for receipt issuance."""
    campaign = PublishedCampaignFactory(total_amount=100_000, total_shares=10)
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
        status=PaymentStatus.SUCCESS,
    )
    return campaign, participation, payment


def test_issue_receipt_is_idempotent_and_verifiable() -> None:
    """Receipt issuance should be idempotent and hash-verifiable."""
    _campaign, _participation, payment = _success_payment(amount=25_000)

    first = issue_donation_receipt_for_payment(payment=payment)
    second = issue_donation_receipt_for_payment(payment=payment)
    is_valid, verified = verify_donation_receipt(
        receipt_number=first.receipt_number,
        receipt_hash=first.receipt_hash,
    )

    assert first.pk == second.pk
    assert first.receipt_number.startswith("MDK-")
    assert len(first.receipt_hash) == 64
    assert is_valid is True
    assert verified == first


def test_receipt_verification_rejects_tampered_hash() -> None:
    """A changed hash should not verify against the stored receipt payload."""
    _campaign, _participation, payment = _success_payment(amount=25_000)
    receipt = issue_donation_receipt_for_payment(payment=payment)

    is_valid, verified = verify_donation_receipt(
        receipt_number=receipt.receipt_number,
        receipt_hash="0" * 64,
    )

    assert is_valid is False
    assert verified == receipt


def test_user_receipt_list_and_detail_are_owner_scoped_and_audited() -> None:
    """Users should see only their own receipts and detail access should be audited."""
    user = UserFactory()
    other_user = UserFactory()
    _campaign, _participation, payment = _success_payment(user=user, amount=25_000)
    _other_campaign, _other_participation, other_payment = _success_payment(user=other_user, amount=30_000)
    receipt = issue_donation_receipt_for_payment(payment=payment)
    issue_donation_receipt_for_payment(payment=other_payment)
    client = _jwt_client(user)

    with patch(_AUDIT_TASK_PATH) as mock_task:
        mock_task.delay = MagicMock()
        list_response = client.get(reverse("madadkar:user-receipt-list"))
        detail_response = client.get(reverse("madadkar:user-receipt-detail", kwargs={"receipt_id": receipt.pk}))

    assert list_response.status_code == status.HTTP_200_OK
    assert list_response.data["data"]["count"] == 1
    assert detail_response.status_code == status.HTTP_200_OK
    assert detail_response.data["data"]["receipt_number"] == receipt.receipt_number
    called_actions = [call.kwargs.get("action") for call in mock_task.delay.call_args_list]
    assert audit_actions.MADADKAR_RECEIPT_ACCESSED in called_actions


def test_public_receipt_verify_endpoint_returns_public_safe_payload() -> None:
    """Public verify endpoint should return safe campaign/amount data only when hash matches."""
    _campaign, _participation, payment = _success_payment(amount=25_000)
    receipt = issue_donation_receipt_for_payment(payment=payment)
    client = APIClient()

    with patch(_AUDIT_TASK_PATH) as mock_task:
        mock_task.delay = MagicMock()
        response = client.post(
            reverse("madadkar:public-receipt-verify"),
            data={"receipt_number": receipt.receipt_number, "receipt_hash": receipt.receipt_hash},
            format="json",
        )

    assert response.status_code == status.HTTP_200_OK
    assert response.data["data"]["is_valid"] is True
    assert response.data["data"]["amount"] == receipt.amount
    assert response.data["data"]["campaign_title"] == receipt.campaign_snapshot["title"]
    called_actions = [call.kwargs.get("action") for call in mock_task.delay.call_args_list]
    assert audit_actions.MADADKAR_RECEIPT_VERIFIED in called_actions


def test_admin_receipt_resend_records_count_and_audit() -> None:
    """Admin resend action should not mutate payload but should record resend metadata and audit."""
    admin = AdminUserFactory()
    _campaign, _participation, payment = _success_payment(amount=25_000)
    receipt = issue_donation_receipt_for_payment(payment=payment)
    original_hash = receipt.receipt_hash
    client = _jwt_client(admin)

    with patch(_AUDIT_TASK_PATH) as mock_task:
        mock_task.delay = MagicMock()
        response = client.post(
            reverse("madadkar:admin-receipt-resend", kwargs={"receipt_id": receipt.pk}),
            data={"delivery_channel": "email"},
            format="json",
        )

    assert response.status_code == status.HTTP_200_OK
    receipt.refresh_from_db()
    assert receipt.resend_count == 1
    assert receipt.last_resent_at is not None
    assert receipt.receipt_hash == original_hash
    called_actions = [call.kwargs.get("action") for call in mock_task.delay.call_args_list]
    assert audit_actions.MADADKAR_RECEIPT_RESENT in called_actions


def test_receipt_payload_is_immutable_except_resend_metadata() -> None:
    """Receipt forensic payload should reject direct application-level mutation."""
    _campaign, _participation, payment = _success_payment(amount=25_000)
    receipt = issue_donation_receipt_for_payment(payment=payment)

    receipt.amount = 1
    with pytest.raises(PermissionError):
        receipt.save()

    receipt.refresh_from_db()
    receipt.resend_count = 1
    receipt.save(update_fields=["resend_count", "updated_at"])
    assert DonationReceipt.objects.get(pk=receipt.pk).resend_count == 1

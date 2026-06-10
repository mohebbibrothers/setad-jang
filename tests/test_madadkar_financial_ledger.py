"""
Madadkar financial ledger hardening tests.

Phase 7 هدفش نزدیک‌تر کردن مددکار به financial-grade است. Payment آخرین وضعیت
تراکنش را نگه می‌دارد؛ PaymentEvent یک ledger append-only از رویدادهای مالی
می‌سازد تا reconciliation و forensic review ممکن باشد.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest
from django.contrib.admin.sites import AdminSite
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient

from apps.madadkar.admin import ParticipationAdmin, PaymentAdmin, PaymentEventAdmin
from apps.madadkar.choices import PaymentEventKind, PaymentStatus
from apps.madadkar.models import Participation, Payment, PaymentEvent
from apps.madadkar.payment_providers.base import PaymentVerifyResult
from apps.madadkar.services import (
    PaymentAmountMismatchError,
    expire_stale_participation,
    verify_payment,
)
from tests.factories import UserFactory
from tests.factories.madadkar import PublishedCampaignFactory

pytestmark = pytest.mark.django_db

_AUDIT_TASK_PATH = "apps.audit_logs.tasks.create_audit_log_task"


def _initiate_via_api(*, campaign, user, share_count: int = 1) -> tuple[Participation, Payment]:
    """شروع مشارکت از HTTP layer برای تولید PaymentEvent.CREATED واقعی."""
    client = APIClient()
    client.force_authenticate(user=user)

    with patch(_AUDIT_TASK_PATH):
        response = client.post(
            reverse("madadkar:user-participate", kwargs={"slug": campaign.slug}),
            data={"share_count": share_count},
            format="json",
        )

    assert response.status_code == status.HTTP_201_CREATED, response.data
    participation = Participation.objects.get(user=user, campaign=campaign)
    return participation, participation.payment


def _event_kinds(payment: Payment) -> list[str]:
    """لیست event_kindهای یک پرداخت به ترتیب ایجاد."""
    return list(payment.events.order_by("created_at", "id").values_list("event_kind", flat=True))


class TestPaymentEventLedger:
    """تست‌های ledger رویدادهای پرداخت مددکار."""

    def test_initiate_participation_records_created_event(self) -> None:
        campaign = PublishedCampaignFactory(total_amount=10_000_000, total_shares=10)
        user = UserFactory()

        participation, payment = _initiate_via_api(campaign=campaign, user=user, share_count=2)

        event = payment.events.get(event_kind=PaymentEventKind.CREATED)
        assert event.previous_status == ""
        assert event.new_status == PaymentStatus.PENDING
        assert event.amount == payment.amount
        assert event.metadata == {
            "campaign_id": campaign.pk,
            "participation_id": participation.pk,
        }

    def test_successful_verify_records_success_event(self) -> None:
        campaign = PublishedCampaignFactory(total_amount=10_000_000, total_shares=10)
        user = UserFactory()
        _participation, payment = _initiate_via_api(campaign=campaign, user=user, share_count=1)

        with patch(_AUDIT_TASK_PATH):
            verify_payment(authority=payment.authority)

        payment.refresh_from_db()
        assert _event_kinds(payment) == [PaymentEventKind.CREATED, PaymentEventKind.VERIFY_SUCCESS]
        event = payment.events.get(event_kind=PaymentEventKind.VERIFY_SUCCESS)
        assert event.previous_status == PaymentStatus.PENDING
        assert event.new_status == PaymentStatus.SUCCESS
        assert event.ref_id == payment.ref_id
        assert event.gateway_status == payment.gateway_status

    def test_failed_verify_records_failed_event(self) -> None:
        campaign = PublishedCampaignFactory(total_amount=10_000_000, total_shares=10)
        user = UserFactory()
        _participation, payment = _initiate_via_api(campaign=campaign, user=user, share_count=1)
        fake_verify = PaymentVerifyResult(
            success=False,
            gateway_status="-1",
            error_message="user canceled",
        )

        with patch(
            "apps.madadkar.payment_providers.sandbox.SandboxProvider.verify_payment",
            return_value=fake_verify,
        ):
            verify_payment(authority=payment.authority)

        payment.refresh_from_db()
        assert _event_kinds(payment) == [PaymentEventKind.CREATED, PaymentEventKind.VERIFY_FAILED]
        event = payment.events.get(event_kind=PaymentEventKind.VERIFY_FAILED)
        assert event.previous_status == PaymentStatus.PENDING
        assert event.new_status == PaymentStatus.FAILED
        assert event.metadata == {"error_message": "user canceled"}

    def test_amount_mismatch_records_security_event_before_raising(self) -> None:
        campaign = PublishedCampaignFactory(total_amount=10_000_000, total_shares=10)
        user = UserFactory()
        _participation, payment = _initiate_via_api(campaign=campaign, user=user, share_count=1)
        fake_verify = PaymentVerifyResult(
            success=True,
            ref_id="TAMPERED",
            verified_amount=payment.amount + 1,
            gateway_status="100",
        )

        with patch(
            "apps.madadkar.payment_providers.sandbox.SandboxProvider.verify_payment",
            return_value=fake_verify,
        ), pytest.raises(PaymentAmountMismatchError):
            verify_payment(authority=payment.authority)

        payment.refresh_from_db()
        assert payment.status == PaymentStatus.FAILED
        event = payment.events.get(event_kind=PaymentEventKind.AMOUNT_MISMATCH)
        assert event.previous_status == PaymentStatus.PENDING
        assert event.new_status == PaymentStatus.FAILED
        assert event.metadata["stored_amount"] == payment.amount
        assert event.metadata["verified_amount"] == payment.amount + 1

    def test_expire_stale_participation_records_expired_event(self) -> None:
        campaign = PublishedCampaignFactory(total_amount=10_000_000, total_shares=10)
        user = UserFactory()
        participation, payment = _initiate_via_api(campaign=campaign, user=user, share_count=1)

        expire_stale_participation(participation=participation)

        payment.refresh_from_db()
        assert payment.status == PaymentStatus.FAILED
        assert _event_kinds(payment) == [PaymentEventKind.CREATED, PaymentEventKind.EXPIRED]


class TestPaymentEventImmutability:
    """PaymentEvent باید append-only باشد."""

    def test_payment_event_cannot_be_updated_or_deleted(self) -> None:
        campaign = PublishedCampaignFactory(total_amount=10_000_000, total_shares=10)
        user = UserFactory()
        _participation, payment = _initiate_via_api(campaign=campaign, user=user, share_count=1)
        event = payment.events.get(event_kind=PaymentEventKind.CREATED)

        event.new_status = PaymentStatus.SUCCESS
        with pytest.raises(PermissionError):
            event.save()

        with pytest.raises(PermissionError):
            event.delete()

        with pytest.raises(PermissionError):
            PaymentEvent.objects.filter(pk=event.pk).update(new_status=PaymentStatus.SUCCESS)

        with pytest.raises(PermissionError):
            PaymentEvent.objects.filter(pk=event.pk).delete()

        event.refresh_from_db()
        assert event.new_status == PaymentStatus.PENDING


class TestMadadkarFinancialAdminSafety:
    """Admin مالی مددکار نباید امکان mutation مستقیم بدهد."""

    def test_payment_participation_and_event_admin_are_read_only(self) -> None:
        site = AdminSite()
        request = APIClient().request().wsgi_request

        assert PaymentAdmin(Payment, site).has_add_permission(request) is False
        assert PaymentAdmin(Payment, site).has_change_permission(request) is False
        assert PaymentAdmin(Payment, site).has_delete_permission(request) is False

        assert ParticipationAdmin(Participation, site).has_add_permission(request) is False
        assert ParticipationAdmin(Participation, site).has_change_permission(request) is False
        assert ParticipationAdmin(Participation, site).has_delete_permission(request) is False

        assert PaymentEventAdmin(PaymentEvent, site).has_add_permission(request) is False
        assert PaymentEventAdmin(PaymentEvent, site).has_change_permission(request) is False
        assert PaymentEventAdmin(PaymentEvent, site).has_delete_permission(request) is False

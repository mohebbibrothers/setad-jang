"""
تست‌های Payment Verify Flow.

پوشش:
- Verify endpoint (GET + POST): happy path
- Idempotency: فراخوانی دوباره با همان authority
- Amount tampering protection
- Verify ناموفق → سهم آزاد می‌شود
- Auto-complete وقتی fully funded می‌شود
- Counter sync بعد از verify (purchased_amount, participant_count)
- Maintenance services: expire stale + close expired campaigns
- Provider error handling
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from django.urls import reverse
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APIClient

from apps.audit_logs import actions as audit_actions
from apps.madadkar.choices import (
    CampaignStatus,
    ParticipationStatus,
    PaymentStatus,
)
from apps.madadkar.models import Campaign, Participation, Payment
from apps.madadkar.payment_providers.base import PaymentVerifyResult
from apps.madadkar.services import (
    PaymentAmountMismatchError,
    PaymentNotFoundError,
    close_campaign_due_to_deadline,
    expire_stale_participation,
    get_stale_participations,
    verify_payment,
)
from tests.factories import UserFactory
from tests.factories.madadkar import (
    CampaignWithDeadlineFactory,
    PaidParticipationFactory,
    ParticipationFactory,
    PaymentFactory,
    PublishedCampaignFactory,
)

pytestmark = pytest.mark.django_db


_AUDIT_TASK_PATH = "apps.audit_logs.tasks.create_audit_log_task"
_VERIFY_URL_NAME = "madadkar:payment-verify"


def _auth(client: APIClient, user) -> None:
    client.force_authenticate(user=user)


def _initiate_via_api(*, campaign, user, share_count) -> tuple[Participation, Payment]:
    """
    helper برای initiate کردن یک participation کامل با درگاه واقعی (Sandbox).

    این تابع از HTTP layer استفاده می‌کند تا flow کامل (مثل واقعیت) باشد.
    """
    client = APIClient()
    _auth(client, user)
    url = reverse("madadkar:user-participate", kwargs={"slug": campaign.slug})

    with patch(_AUDIT_TASK_PATH):
        response = client.post(
            url, data={"share_count": share_count}, format="json",
        )

    assert response.status_code == status.HTTP_201_CREATED, (
        f"initiate failed: {response.data}"
    )

    participation = Participation.objects.filter(
        user=user, campaign=campaign,
    ).order_by("-pk").first()
    payment = participation.payment
    return participation, payment


# ============================================================
# Verify Endpoint — GET (Zarinpal-style)
# ============================================================


class TestVerifyEndpointGET:
    """GET /api/v1/madadkar/payment/verify/?authority=..."""

    def test_verify_success_happy_path(self):
        """flow کامل: initiate → verify → status=SUCCESS, participation=PAID."""
        campaign = PublishedCampaignFactory(
            total_amount=100_000_000,
            total_shares=10,  # هر سهم = 10 میلیون
        )
        user = UserFactory()
        participation, payment = _initiate_via_api(
            campaign=campaign, user=user, share_count=2,
        )

        # callback از سمت "درگاه"
        client = APIClient()
        url = reverse(_VERIFY_URL_NAME)

        with patch(_AUDIT_TASK_PATH):
            response = client.get(url, {"authority": payment.authority})

        assert response.status_code == status.HTTP_200_OK
        assert response.data["data"]["is_verified"] is True
        assert response.data["data"]["payment_status"] == PaymentStatus.SUCCESS

        # DB checks
        payment.refresh_from_db()
        assert payment.status == PaymentStatus.SUCCESS
        assert payment.ref_id.startswith("SBXREF-")
        assert payment.paid_at is not None
        assert payment.verified_at is not None

        participation.refresh_from_db()
        assert participation.status == ParticipationStatus.PAID
        assert participation.paid_at is not None

    def test_verify_updates_purchased_amount_after_success(self):
        """purchased_amount فقط بعد از verify موفق به‌روز می‌شود."""
        campaign = PublishedCampaignFactory(
            total_amount=100_000_000,
            total_shares=10,
        )
        user = UserFactory()
        _participation, payment = _initiate_via_api(
            campaign=campaign, user=user, share_count=3,
        )

        # قبل از verify
        campaign.refresh_from_db()
        assert campaign.purchased_amount == 0
        assert campaign.participant_count == 0

        # verify
        client = APIClient()
        url = reverse(_VERIFY_URL_NAME)
        with patch(_AUDIT_TASK_PATH):
            client.get(url, {"authority": payment.authority})

        # بعد از verify
        campaign.refresh_from_db()
        assert campaign.purchased_amount == 30_000_000  # 3 * 10M
        assert campaign.participant_count == 1

    def test_verify_dispatches_success_audit(self):
        campaign = PublishedCampaignFactory()
        user = UserFactory()
        _p, payment = _initiate_via_api(
            campaign=campaign, user=user, share_count=1,
        )

        client = APIClient()
        url = reverse(_VERIFY_URL_NAME)

        with patch(_AUDIT_TASK_PATH) as mock_task:
            mock_task.delay = MagicMock()
            client.get(url, {"authority": payment.authority})

        # حداقل یک بار با action SUCCESS فراخوانی شده
        actions_called = [
            call.kwargs.get("action")
            for call in mock_task.delay.call_args_list
        ]
        assert audit_actions.MADADKAR_PAYMENT_SUCCESS in actions_called

    def test_verify_404_for_unknown_authority(self):
        client = APIClient()
        url = reverse(_VERIFY_URL_NAME)

        with patch(_AUDIT_TASK_PATH):
            response = client.get(url, {"authority": "non-existent"})

        assert response.status_code == status.HTTP_404_NOT_FOUND

    def test_verify_400_when_authority_missing(self):
        client = APIClient()
        url = reverse(_VERIFY_URL_NAME)
        response = client.get(url)
        assert response.status_code == status.HTTP_400_BAD_REQUEST


# ============================================================
# Verify Endpoint — POST
# ============================================================


class TestVerifyEndpointPOST:
    """POST /api/v1/madadkar/payment/verify/"""

    def test_verify_via_post(self):
        campaign = PublishedCampaignFactory()
        user = UserFactory()
        _p, payment = _initiate_via_api(
            campaign=campaign, user=user, share_count=1,
        )

        client = APIClient()
        url = reverse(_VERIFY_URL_NAME)

        with patch(_AUDIT_TASK_PATH):
            response = client.post(
                url,
                data={"authority": payment.authority},
                format="json",
            )

        assert response.status_code == status.HTTP_200_OK
        assert response.data["data"]["is_verified"] is True


# ============================================================
# Idempotency
# ============================================================


class TestVerifyIdempotency:
    """فراخوانی دوباره verify نباید side effect ایجاد کند."""

    def test_double_verify_returns_same_result(self):
        campaign = PublishedCampaignFactory(
            total_amount=100_000_000,
            total_shares=10,
        )
        user = UserFactory()
        _p, payment = _initiate_via_api(
            campaign=campaign, user=user, share_count=2,
        )

        client = APIClient()
        url = reverse(_VERIFY_URL_NAME)

        # اولین verify
        with patch(_AUDIT_TASK_PATH):
            response_a = client.get(url, {"authority": payment.authority})
        assert response_a.status_code == status.HTTP_200_OK

        campaign.refresh_from_db()
        amount_after_first = campaign.purchased_amount
        count_after_first = campaign.participant_count

        # دومین verify — همان authority
        with patch(_AUDIT_TASK_PATH):
            response_b = client.get(url, {"authority": payment.authority})
        assert response_b.status_code == status.HTTP_200_OK

        # هیچ تغییری ایجاد نشده
        campaign.refresh_from_db()
        assert campaign.purchased_amount == amount_after_first
        assert campaign.participant_count == count_after_first

        # فقط یک Payment با ref_id
        payment.refresh_from_db()
        assert payment.status == PaymentStatus.SUCCESS

    def test_provider_not_called_on_double_verify(self):
        """در فراخوانی دوم نباید با provider تماس برقرار شود."""
        campaign = PublishedCampaignFactory()
        user = UserFactory()
        _p, payment = _initiate_via_api(
            campaign=campaign, user=user, share_count=1,
        )

        client = APIClient()
        url = reverse(_VERIFY_URL_NAME)

        # اولین verify
        with patch(_AUDIT_TASK_PATH):
            client.get(url, {"authority": payment.authority})

        # دومین verify — provider.verify_payment نباید فراخوانی شود
        with patch(
            "apps.madadkar.payment_providers.sandbox.SandboxProvider.verify_payment"
        ) as mock_verify, patch(_AUDIT_TASK_PATH):
            client.get(url, {"authority": payment.authority})

        mock_verify.assert_not_called()


# ============================================================
# Amount Tampering Protection
# ============================================================


class TestVerifyAmountTampering:
    """anti-tampering: اگر درگاه مبلغ متفاوت برگرداند، رد شود."""

    def test_amount_mismatch_marks_payment_failed(self):
        campaign = PublishedCampaignFactory(
            total_amount=100_000_000,
            total_shares=10,
        )
        user = UserFactory()
        participation, payment = _initiate_via_api(
            campaign=campaign, user=user, share_count=2,
        )

        original_amount = payment.amount

        # mock provider که مبلغ متفاوت برگرداند
        fake_verify = PaymentVerifyResult(
            success=True,
            ref_id="FAKE-REF",
            verified_amount=999,  # ≠ original_amount
            gateway_status="100",
        )

        with patch(
            "apps.madadkar.payment_providers.sandbox.SandboxProvider.verify_payment",
            return_value=fake_verify,
        ), patch(_AUDIT_TASK_PATH):
            response = verify_payment_via_api(payment.authority)

        assert response.status_code == status.HTTP_400_BAD_REQUEST

        payment.refresh_from_db()
        assert payment.status == PaymentStatus.FAILED
        assert payment.amount == original_amount  # دستکاری نشده

        participation.refresh_from_db()
        assert participation.status == ParticipationStatus.FAILED

        # سهم آزاد شد
        campaign.refresh_from_db()
        assert campaign.purchased_shares == 0

    def test_amount_mismatch_raises_in_service_layer(self):
        """تست مستقیم service بدون HTTP."""
        campaign = PublishedCampaignFactory(
            total_amount=10_000_000,
            total_shares=10,
        )
        user = UserFactory()
        _participation, payment = _initiate_via_api(
            campaign=campaign, user=user, share_count=1,
        )

        fake_verify = PaymentVerifyResult(
            success=True,
            verified_amount=payment.amount + 1,
            ref_id="X",
        )

        with patch(
            "apps.madadkar.payment_providers.sandbox.SandboxProvider.verify_payment",
            return_value=fake_verify,
        ), pytest.raises(PaymentAmountMismatchError):
            verify_payment(authority=payment.authority)


def verify_payment_via_api(authority: str):
    """helper برای فراخوانی verify از HTTP layer."""
    client = APIClient()
    url = reverse(_VERIFY_URL_NAME)
    with patch(_AUDIT_TASK_PATH):
        return client.get(url, {"authority": authority})


# ============================================================
# Verify Failure → Share Release
# ============================================================


class TestVerifyFailureReleasesShares:
    """در صورت verify ناموفق، سهم آزاد شود."""

    def test_failed_verify_releases_reserved_shares(self):
        campaign = PublishedCampaignFactory(
            total_amount=100_000_000,
            total_shares=10,
        )
        user = UserFactory()
        participation, payment = _initiate_via_api(
            campaign=campaign, user=user, share_count=3,
        )

        # قبل از verify: 3 سهم رزرو شده
        campaign.refresh_from_db()
        assert campaign.purchased_shares == 3

        # mock provider که شکست برمی‌گرداند
        fake_verify = PaymentVerifyResult(
            success=False,
            gateway_status="-1",
            error_message="user canceled",
        )

        with patch(
            "apps.madadkar.payment_providers.sandbox.SandboxProvider.verify_payment",
            return_value=fake_verify,
        ), patch(_AUDIT_TASK_PATH):
            response = verify_payment_via_api(payment.authority)

        assert response.status_code == status.HTTP_200_OK
        assert response.data["data"]["is_verified"] is False

        # سهم آزاد شد
        campaign.refresh_from_db()
        assert campaign.purchased_shares == 0
        assert campaign.purchased_amount == 0

        payment.refresh_from_db()
        assert payment.status == PaymentStatus.FAILED

        participation.refresh_from_db()
        assert participation.status == ParticipationStatus.FAILED


# ============================================================
# Auto-Complete on Fully Funded
# ============================================================


class TestAutoComplete:
    """وقتی تمام سهم‌ها فروخته شد، campaign به COMPLETED می‌رود."""

    def test_campaign_auto_completes_after_last_share_paid(self):
        campaign = PublishedCampaignFactory(
            total_amount=50_000_000,
            total_shares=5,
        )
        user = UserFactory()

        _p, payment = _initiate_via_api(
            campaign=campaign, user=user, share_count=5,
        )

        # هنوز PUBLISHED
        campaign.refresh_from_db()
        assert campaign.status == CampaignStatus.PUBLISHED

        # verify موفق
        with patch(_AUDIT_TASK_PATH):
            verify_payment_via_api(payment.authority)

        # حالا باید COMPLETED شود
        campaign.refresh_from_db()
        assert campaign.status == CampaignStatus.COMPLETED
        assert campaign.completed_at is not None

    def test_campaign_stays_published_if_not_fully_funded(self):
        campaign = PublishedCampaignFactory(
            total_amount=50_000_000,
            total_shares=10,
        )
        user = UserFactory()

        _p, payment = _initiate_via_api(
            campaign=campaign, user=user, share_count=5,
        )

        with patch(_AUDIT_TASK_PATH):
            verify_payment_via_api(payment.authority)

        campaign.refresh_from_db()
        assert campaign.status == CampaignStatus.PUBLISHED
        assert campaign.completed_at is None


# ============================================================
# Participant Count Sync
# ============================================================


class TestParticipantCountSync:
    """participant_count باید unique users شمارش کند."""

    def test_same_user_multiple_payments_counted_once(self):
        """یک کاربر با چند پرداخت موفق، یک بار شمارش می‌شود."""
        campaign = PublishedCampaignFactory(
            total_amount=100_000_000,
            total_shares=10,
        )
        user = UserFactory()

        # دو initiate جداگانه برای همان کاربر
        _p1, payment1 = _initiate_via_api(
            campaign=campaign, user=user, share_count=2,
        )
        _p2, payment2 = _initiate_via_api(
            campaign=campaign, user=user, share_count=3,
        )

        with patch(_AUDIT_TASK_PATH):
            verify_payment_via_api(payment1.authority)
            verify_payment_via_api(payment2.authority)

        campaign.refresh_from_db()
        assert campaign.participant_count == 1  # یک کاربر
        assert campaign.purchased_shares == 5
        assert campaign.purchased_amount == 50_000_000

    def test_multiple_users_counted_separately(self):
        campaign = PublishedCampaignFactory(
            total_amount=100_000_000,
            total_shares=10,
        )
        user_a = UserFactory()
        user_b = UserFactory()
        user_c = UserFactory()

        for user in (user_a, user_b, user_c):
            _p, payment = _initiate_via_api(
                campaign=campaign, user=user, share_count=1,
            )
            with patch(_AUDIT_TASK_PATH):
                verify_payment_via_api(payment.authority)

        campaign.refresh_from_db()
        assert campaign.participant_count == 3


# ============================================================
# Service Layer — Direct Tests
# ============================================================


class TestVerifyPaymentServiceLayer:
    """تست‌های مستقیم service بدون HTTP."""

    def test_raises_when_authority_not_found(self):
        with pytest.raises(PaymentNotFoundError):
            verify_payment(authority="does-not-exist")

    def test_idempotent_on_already_success_payment(self):
        """Payment که قبلاً SUCCESS بوده، بدون تماس برمی‌گردد."""
        from tests.factories.madadkar import SuccessPaymentFactory
        payment = SuccessPaymentFactory()

        # provider نباید فراخوانی شود
        with patch(
            "apps.madadkar.payment_providers.sandbox.SandboxProvider.verify_payment"
        ) as mock_verify:
            result = verify_payment(authority=payment.authority)

        mock_verify.assert_not_called()
        assert result.pk == payment.pk
        assert result.status == PaymentStatus.SUCCESS


# ============================================================
# Maintenance — expire_stale_participation
# ============================================================


class TestExpireStaleParticipation:
    """تست‌های منطق expire."""

    def test_expire_pending_participation_releases_share(self):
        campaign = PublishedCampaignFactory(
            total_amount=50_000_000,
            total_shares=10,
        )
        user = UserFactory()
        _p, payment = _initiate_via_api(
            campaign=campaign, user=user, share_count=3,
        )

        # رزرو شد
        campaign.refresh_from_db()
        assert campaign.purchased_shares == 3

        participation = payment.participation

        # expire
        result = expire_stale_participation(participation=participation)

        assert result.status == ParticipationStatus.EXPIRED
        campaign.refresh_from_db()
        assert campaign.purchased_shares == 0

        payment.refresh_from_db()
        assert payment.status == PaymentStatus.FAILED

    def test_expire_does_nothing_on_paid_participation(self):
        """PAID participation نباید expire شود."""
        participation = PaidParticipationFactory()
        original_status = participation.status

        result = expire_stale_participation(participation=participation)
        assert result.status == original_status


class TestGetStaleParticipations:
    """دریافت queryset of participations معطل."""

    def test_returns_pending_participations_older_than_timeout(self, settings):
        settings.MADADKAR_PAYMENT_TIMEOUT_MINUTES = 15

        old_participation = ParticipationFactory()
        # دستی created_at را به گذشته ببریم
        old_time = timezone.now() - timezone.timedelta(minutes=20)
        Participation.objects.filter(pk=old_participation.pk).update(
            created_at=old_time,
        )

        # یک participation تازه که نباید expire شود
        fresh_participation = ParticipationFactory()

        stale = list(get_stale_participations())
        stale_ids = {p.pk for p in stale}

        assert old_participation.pk in stale_ids
        assert fresh_participation.pk not in stale_ids

    def test_does_not_return_paid_participations(self):
        """PAID نباید در stale لیست باشد حتی اگر قدیمی باشد."""
        paid = PaidParticipationFactory()
        Participation.objects.filter(pk=paid.pk).update(
            created_at=timezone.now() - timezone.timedelta(hours=10),
        )

        stale_ids = {p.pk for p in get_stale_participations()}
        assert paid.pk not in stale_ids


# ============================================================
# Maintenance — close_campaign_due_to_deadline
# ============================================================


class TestCloseCampaignDueToDeadline:
    """تست‌های auto-close حرکت‌های با deadline منقضی."""

    def test_published_with_passed_deadline_gets_closed(self):
        campaign = CampaignWithDeadlineFactory()
        # deadline را به گذشته منتقل می‌کنیم
        Campaign.objects.filter(pk=campaign.pk).update(
            deadline=timezone.now() - timezone.timedelta(hours=1),
        )
        campaign.refresh_from_db()

        result = close_campaign_due_to_deadline(campaign=campaign)

        assert result.status == CampaignStatus.CLOSED
        assert result.closed_at is not None

    def test_published_with_future_deadline_not_closed(self):
        campaign = CampaignWithDeadlineFactory()  # deadline 30 days future

        result = close_campaign_due_to_deadline(campaign=campaign)
        assert result.status == CampaignStatus.PUBLISHED
        assert result.closed_at is None

    def test_draft_campaign_not_closed(self):
        """campaign DRAFT حتی با deadline گذشته نباید بسته شود."""
        from tests.factories.madadkar import CampaignFactory
        campaign = CampaignFactory()  # DRAFT

        result = close_campaign_due_to_deadline(campaign=campaign)
        assert result.status == CampaignStatus.DRAFT

    def test_campaign_without_deadline_not_closed(self):
        campaign = PublishedCampaignFactory(has_deadline=False)

        result = close_campaign_due_to_deadline(campaign=campaign)
        assert result.status == CampaignStatus.PUBLISHED


# Ensure Payment + PaymentFactory imports are used at module level
_ = Payment
_ = PaymentFactory

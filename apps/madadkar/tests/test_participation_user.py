"""
تست‌های User Participation endpoints + initiate flow.

پوشش:
- POST /campaigns/{slug}/participate/: happy path + validation + 404
- Permission boundaries: anonymous → 401, regular user → success
- Campaign accept rules: DRAFT/COMPLETED/CLOSED/invisible/expired → 400
- Share count validation: 0, negative, > remaining
- Share reservation: counters به‌روز می‌شوند بلافاصله بعد از initiate
- snapshot قیمت در لحظه initiate ثبت می‌شود
- audit dispatch verification
- GET /me/participations/: لیست + فیلتر
- GET /me/participations/{id}/: جزئیات + IDOR check
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
from apps.madadkar.models import Participation, Payment
from tests.factories import AdminUserFactory, UserFactory
from tests.factories.madadkar import (
    CampaignFactory,
    CampaignWithDeadlineFactory,
    CompletedCampaignFactory,
    PaidParticipationFactory,
    ParticipationFactory,
    PublishedCampaignFactory,
)

pytestmark = pytest.mark.django_db


_AUDIT_TASK_PATH = "apps.audit_logs.tasks.create_audit_log_task"


def _auth(client: APIClient, user) -> None:
    """احراز هویت سریع کاربر در client."""
    client.force_authenticate(user=user)


# ============================================================
# Initiate Participation — Permission Boundaries
# ============================================================


class TestParticipateAuth:
    """permission و authentication checks."""

    def test_participate_requires_authentication(self):
        campaign = PublishedCampaignFactory()
        client = APIClient()
        url = reverse(
            "madadkar:user-participate",
            kwargs={"slug": campaign.slug},
        )
        response = client.post(url, data={"share_count": 1}, format="json")
        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    def test_participate_works_for_regular_user(self):
        """کاربر عادی (لاگین معمولی) می‌تواند مشارکت کند."""
        campaign = PublishedCampaignFactory(
            total_amount=100_000_000,
            total_shares=100,
        )

        client = APIClient()
        _auth(client, UserFactory())
        url = reverse(
            "madadkar:user-participate",
            kwargs={"slug": campaign.slug},
        )

        with patch(_AUDIT_TASK_PATH) as mock_task:
            mock_task.delay = MagicMock()
            response = client.post(url, data={"share_count": 2}, format="json")

        assert response.status_code == status.HTTP_201_CREATED

    def test_participate_works_for_admin_too(self):
        """ادمین هم می‌تواند به‌عنوان کاربر مشارکت کند."""
        campaign = PublishedCampaignFactory()

        client = APIClient()
        _auth(client, AdminUserFactory())
        url = reverse(
            "madadkar:user-participate",
            kwargs={"slug": campaign.slug},
        )

        with patch(_AUDIT_TASK_PATH):
            response = client.post(url, data={"share_count": 1}, format="json")

        assert response.status_code == status.HTTP_201_CREATED


# ============================================================
# Initiate Participation — Happy Path
# ============================================================


class TestParticipateHappyPath:
    """flow کامل initiate مشارکت."""

    def test_initiate_creates_participation_and_payment(self):
        campaign = PublishedCampaignFactory(
            total_amount=1_000_000_000,
            total_shares=100,  # هر سهم = 10 میلیون
        )

        client = APIClient()
        user = UserFactory()
        _auth(client, user)
        url = reverse(
            "madadkar:user-participate",
            kwargs={"slug": campaign.slug},
        )

        with patch(_AUDIT_TASK_PATH):
            response = client.post(url, data={"share_count": 3}, format="json")

        assert response.status_code == status.HTTP_201_CREATED

        # DB checks
        participation = Participation.objects.filter(
            user=user,
            campaign=campaign,
        ).first()
        assert participation is not None
        assert participation.share_count == 3
        assert participation.share_price_snapshot == 10_000_000
        assert participation.total_amount == 30_000_000
        assert participation.status == ParticipationStatus.PENDING_PAYMENT

        payment = Payment.objects.filter(participation=participation).first()
        assert payment is not None
        assert payment.amount == 30_000_000
        assert payment.gateway_name == "sandbox"
        assert payment.status == PaymentStatus.PENDING
        assert payment.authority.startswith("SBX-")

    def test_initiate_response_includes_gateway_url(self):
        campaign = PublishedCampaignFactory()
        client = APIClient()
        _auth(client, UserFactory())
        url = reverse(
            "madadkar:user-participate",
            kwargs={"slug": campaign.slug},
        )

        with patch(_AUDIT_TASK_PATH):
            response = client.post(url, data={"share_count": 1}, format="json")

        data = response.data["data"]
        assert "gateway_url" in data
        assert "authority" in data
        assert "participation" in data
        assert data["gateway_url"].startswith("http")
        assert data["authority"].startswith("SBX-")

    def test_initiate_reserves_shares_immediately(self):
        """سهم‌ها بلافاصله بعد از initiate در purchased_shares ظاهر می‌شوند."""
        campaign = PublishedCampaignFactory(
            total_amount=1_000_000,
            total_shares=100,
        )
        assert campaign.purchased_shares == 0

        client = APIClient()
        _auth(client, UserFactory())
        url = reverse(
            "madadkar:user-participate",
            kwargs={"slug": campaign.slug},
        )

        with patch(_AUDIT_TASK_PATH):
            client.post(url, data={"share_count": 5}, format="json")

        campaign.refresh_from_db()
        assert campaign.purchased_shares == 5
        assert campaign.remaining_shares == 95

    def test_initiate_does_not_increment_purchased_amount_yet(self):
        """purchased_amount فقط بعد از verify موفق زیاد می‌شود، نه بعد از initiate."""
        campaign = PublishedCampaignFactory()
        client = APIClient()
        _auth(client, UserFactory())
        url = reverse(
            "madadkar:user-participate",
            kwargs={"slug": campaign.slug},
        )

        with patch(_AUDIT_TASK_PATH):
            client.post(url, data={"share_count": 2}, format="json")

        campaign.refresh_from_db()
        assert campaign.purchased_amount == 0  # هنوز پرداخت تأیید نشده

    def test_initiate_dispatches_audit_log(self):
        campaign = PublishedCampaignFactory()
        client = APIClient()
        _auth(client, UserFactory())
        url = reverse(
            "madadkar:user-participate",
            kwargs={"slug": campaign.slug},
        )

        with patch(_AUDIT_TASK_PATH) as mock_task:
            mock_task.delay = MagicMock()
            client.post(url, data={"share_count": 1}, format="json")

        mock_task.delay.assert_called_once()
        kwargs = mock_task.delay.call_args.kwargs
        assert kwargs["action"] == audit_actions.MADADKAR_PARTICIPATION_INITIATED

    def test_snapshot_is_taken_from_current_share_price(self):
        """share_price_snapshot دقیقاً برابر قیمت لحظه initiate است."""
        campaign = PublishedCampaignFactory(
            total_amount=5_000_000_000,
            total_shares=500,  # 10 میلیون
        )
        client = APIClient()
        _auth(client, UserFactory())
        url = reverse(
            "madadkar:user-participate",
            kwargs={"slug": campaign.slug},
        )

        with patch(_AUDIT_TASK_PATH):
            client.post(url, data={"share_count": 2}, format="json")

        participation = Participation.objects.filter(campaign=campaign).first()
        assert participation.share_price_snapshot == 10_000_000
        assert participation.total_amount == 20_000_000


# ============================================================
# Initiate Participation — Validation / Errors
# ============================================================


class TestParticipateValidation:
    """validation و error scenarios."""

    def test_404_for_nonexistent_campaign(self):
        client = APIClient()
        _auth(client, UserFactory())
        url = reverse(
            "madadkar:user-participate",
            kwargs={"slug": "non-existent"},
        )
        response = client.post(url, data={"share_count": 1}, format="json")
        assert response.status_code == status.HTTP_404_NOT_FOUND

    def test_404_for_draft_campaign(self):
        """campaign DRAFT برای کاربر در دسترس نیست."""
        campaign = CampaignFactory()  # DRAFT
        client = APIClient()
        _auth(client, UserFactory())
        url = reverse(
            "madadkar:user-participate",
            kwargs={"slug": campaign.slug},
        )
        response = client.post(url, data={"share_count": 1}, format="json")
        assert response.status_code == status.HTTP_404_NOT_FOUND

    def test_404_for_invisible_campaign(self):
        campaign = PublishedCampaignFactory(is_visible=False)
        client = APIClient()
        _auth(client, UserFactory())
        url = reverse(
            "madadkar:user-participate",
            kwargs={"slug": campaign.slug},
        )
        response = client.post(url, data={"share_count": 1}, format="json")
        assert response.status_code == status.HTTP_404_NOT_FOUND

    def test_400_for_zero_share_count(self):
        campaign = PublishedCampaignFactory()
        client = APIClient()
        _auth(client, UserFactory())
        url = reverse(
            "madadkar:user-participate",
            kwargs={"slug": campaign.slug},
        )
        response = client.post(url, data={"share_count": 0}, format="json")
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_400_for_negative_share_count(self):
        campaign = PublishedCampaignFactory()
        client = APIClient()
        _auth(client, UserFactory())
        url = reverse(
            "madadkar:user-participate",
            kwargs={"slug": campaign.slug},
        )
        response = client.post(url, data={"share_count": -5}, format="json")
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_400_when_share_count_exceeds_remaining(self):
        campaign = PublishedCampaignFactory(
            total_amount=1_000_000,
            total_shares=10,
        )
        client = APIClient()
        _auth(client, UserFactory())
        url = reverse(
            "madadkar:user-participate",
            kwargs={"slug": campaign.slug},
        )

        with patch(_AUDIT_TASK_PATH):
            response = client.post(
                url,
                data={"share_count": 11},
                format="json",
            )

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        # هیچ Participation ساخته نشده
        assert Participation.objects.filter(campaign=campaign).count() == 0

    def test_400_for_completed_campaign(self):
        campaign = CompletedCampaignFactory()
        client = APIClient()
        _auth(client, UserFactory())
        url = reverse(
            "madadkar:user-participate",
            kwargs={"slug": campaign.slug},
        )

        with patch(_AUDIT_TASK_PATH):
            response = client.post(url, data={"share_count": 1}, format="json")

        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_400_for_closed_campaign(self):
        campaign = PublishedCampaignFactory()
        campaign.status = CampaignStatus.CLOSED
        campaign.closed_at = timezone.now()
        campaign.save()

        client = APIClient()
        _auth(client, UserFactory())
        url = reverse(
            "madadkar:user-participate",
            kwargs={"slug": campaign.slug},
        )

        with patch(_AUDIT_TASK_PATH):
            response = client.post(url, data={"share_count": 1}, format="json")

        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_400_when_deadline_passed(self):
        """campaign با deadline منقضی شده، حتی اگر PUBLISHED باشد، رد می‌شود."""
        campaign = CampaignWithDeadlineFactory()
        # deadline را به گذشته منتقل می‌کنیم
        campaign.deadline = timezone.now() - timezone.timedelta(hours=1)
        campaign.save()

        client = APIClient()
        _auth(client, UserFactory())
        url = reverse(
            "madadkar:user-participate",
            kwargs={"slug": campaign.slug},
        )

        with patch(_AUDIT_TASK_PATH):
            response = client.post(url, data={"share_count": 1}, format="json")

        assert response.status_code == status.HTTP_400_BAD_REQUEST


# ============================================================
# Share Reservation Edge Cases
# ============================================================


class TestShareReservation:
    """edge cases مهم رزرو سهم."""

    def test_last_share_reservation(self):
        """رزرو آخرین سهم باید کار کند."""
        campaign = PublishedCampaignFactory(
            total_amount=10_000_000,
            total_shares=10,
        )
        # 9 سهم قبلاً رزرو شده
        campaign.purchased_shares = 9
        campaign.save()

        client = APIClient()
        _auth(client, UserFactory())
        url = reverse(
            "madadkar:user-participate",
            kwargs={"slug": campaign.slug},
        )

        with patch(_AUDIT_TASK_PATH):
            response = client.post(url, data={"share_count": 1}, format="json")

        assert response.status_code == status.HTTP_201_CREATED

    def test_reservation_after_last_share_taken_fails(self):
        """درخواست بعد از پر شدن همه سهم‌ها رد می‌شود."""
        campaign = PublishedCampaignFactory(
            total_amount=10_000_000,
            total_shares=10,
        )

        client = APIClient()
        _auth(client, UserFactory())
        url = reverse(
            "madadkar:user-participate",
            kwargs={"slug": campaign.slug},
        )

        # درخواست اول — تمام 10 سهم
        with patch(_AUDIT_TASK_PATH):
            response_a = client.post(
                url,
                data={"share_count": 10},
                format="json",
            )
        assert response_a.status_code == status.HTTP_201_CREATED

        # درخواست دوم باید fail شود
        client2 = APIClient()
        _auth(client2, UserFactory())
        with patch(_AUDIT_TASK_PATH):
            response_b = client2.post(
                url,
                data={"share_count": 1},
                format="json",
            )
        assert response_b.status_code == status.HTTP_400_BAD_REQUEST

    def test_pending_participations_count_as_reserved(self):
        """PENDING participations هم به‌عنوان رزرو شمارش می‌شوند."""
        campaign = PublishedCampaignFactory(
            total_amount=100_000,
            total_shares=10,
        )

        # یک Participation PENDING ساخته می‌شود → 3 سهم رزرو
        ParticipationFactory(
            campaign=campaign,
            share_count=3,
            status=ParticipationStatus.PENDING_PAYMENT,
        )

        # حالا sync کنیم تا counter به‌روز شود
        from apps.madadkar.services import _sync_campaign_counters

        _sync_campaign_counters(campaign=campaign)
        campaign.refresh_from_db()
        assert campaign.purchased_shares == 3

        # کاربر دیگر باید فقط حداکثر 7 سهم بتواند بگیرد
        client = APIClient()
        _auth(client, UserFactory())
        url = reverse(
            "madadkar:user-participate",
            kwargs={"slug": campaign.slug},
        )

        with patch(_AUDIT_TASK_PATH):
            response = client.post(url, data={"share_count": 8}, format="json")

        assert response.status_code == status.HTTP_400_BAD_REQUEST


# ============================================================
# My Participations — List
# ============================================================


class TestMyParticipationsList:
    """GET /api/v1/madadkar/me/participations/"""

    def test_requires_authentication(self):
        client = APIClient()
        url = reverse("madadkar:user-my-participations-list")
        response = client.get(url)
        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    def test_returns_only_my_participations(self):
        """IDOR: کاربر فقط participationهای خودش را می‌بیند."""
        user_a = UserFactory()
        user_b = UserFactory()

        ParticipationFactory(user=user_a, share_count=2)
        ParticipationFactory(user=user_a, share_count=3)
        ParticipationFactory(user=user_b, share_count=5)  # نباید بیاید

        client = APIClient()
        _auth(client, user_a)
        url = reverse("madadkar:user-my-participations-list")
        response = client.get(url)

        assert response.status_code == status.HTTP_200_OK
        results = response.data["data"]["results"]
        assert len(results) == 2
        share_counts = {r["share_count"] for r in results}
        assert share_counts == {2, 3}

    def test_empty_list_for_new_user(self):
        client = APIClient()
        _auth(client, UserFactory())
        url = reverse("madadkar:user-my-participations-list")
        response = client.get(url)

        assert response.status_code == status.HTTP_200_OK
        assert response.data["data"]["results"] == []

    def test_filter_by_status_paid(self):
        user = UserFactory()
        PaidParticipationFactory(user=user, share_count=1)
        ParticipationFactory(user=user, share_count=2)  # PENDING

        client = APIClient()
        _auth(client, user)
        url = reverse("madadkar:user-my-participations-list")
        response = client.get(url, {"status": ParticipationStatus.PAID})

        results = response.data["data"]["results"]
        assert len(results) == 1
        assert results[0]["status"] == ParticipationStatus.PAID

    def test_filter_by_campaign(self):
        user = UserFactory()
        camp_a = PublishedCampaignFactory()
        camp_b = PublishedCampaignFactory()
        ParticipationFactory(user=user, campaign=camp_a)
        ParticipationFactory(user=user, campaign=camp_b)

        client = APIClient()
        _auth(client, user)
        url = reverse("madadkar:user-my-participations-list")
        response = client.get(url, {"campaign": camp_a.pk})

        results = response.data["data"]["results"]
        assert len(results) == 1
        assert results[0]["campaign"]["id"] == camp_a.pk

    def test_list_includes_campaign_summary(self):
        user = UserFactory()
        ParticipationFactory(user=user)

        client = APIClient()
        _auth(client, user)
        url = reverse("madadkar:user-my-participations-list")
        response = client.get(url)

        item = response.data["data"]["results"][0]
        assert "campaign" in item
        assert "title" in item["campaign"]
        assert "sponsor" in item["campaign"]


# ============================================================
# My Participation Detail
# ============================================================


class TestMyParticipationDetail:
    """GET /api/v1/madadkar/me/participations/{id}/"""

    def test_requires_authentication(self):
        participation = ParticipationFactory()
        client = APIClient()
        url = reverse(
            "madadkar:user-my-participation-detail",
            kwargs={"participation_id": participation.pk},
        )
        response = client.get(url)
        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    def test_owner_can_view_own_participation(self):
        user = UserFactory()
        participation = ParticipationFactory(user=user)

        client = APIClient()
        _auth(client, user)
        url = reverse(
            "madadkar:user-my-participation-detail",
            kwargs={"participation_id": participation.pk},
        )
        response = client.get(url)

        assert response.status_code == status.HTTP_200_OK
        assert response.data["data"]["id"] == participation.pk

    def test_idor_protection_other_user(self):
        """IDOR: کاربر B نباید participation کاربر A را ببیند."""
        user_a = UserFactory()
        user_b = UserFactory()
        participation_a = ParticipationFactory(user=user_a)

        client = APIClient()
        _auth(client, user_b)
        url = reverse(
            "madadkar:user-my-participation-detail",
            kwargs={"participation_id": participation_a.pk},
        )
        response = client.get(url)

        assert response.status_code == status.HTTP_404_NOT_FOUND

    def test_404_for_nonexistent_participation(self):
        client = APIClient()
        _auth(client, UserFactory())
        url = reverse(
            "madadkar:user-my-participation-detail",
            kwargs={"participation_id": 999_999},
        )
        response = client.get(url)
        assert response.status_code == status.HTTP_404_NOT_FOUND

    def test_detail_includes_payment(self):
        user = UserFactory()
        participation = PaidParticipationFactory(user=user)
        # ساخت Payment مرتبط
        from tests.factories.madadkar import SuccessPaymentFactory

        SuccessPaymentFactory(participation=participation, user=user)

        client = APIClient()
        _auth(client, user)
        url = reverse(
            "madadkar:user-my-participation-detail",
            kwargs={"participation_id": participation.pk},
        )
        response = client.get(url)

        data = response.data["data"]
        assert "payment" in data
        assert data["payment"] is not None
        assert data["payment"]["status"] == PaymentStatus.SUCCESS

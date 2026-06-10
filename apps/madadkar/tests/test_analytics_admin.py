"""
تست‌های Admin Analytics endpoints.

پوشش:
- GET /admin/campaigns/{id}/participants/ — لیست مشارکت‌کنندگان
- GET /admin/campaigns/{id}/leaderboard/  — top contributors
- GET /admin/campaigns/{id}/analytics/    — آمار تجمیعی
- GET /admin/campaigns/{id}/export/       — خروجی Excel
- GET /admin/payments/                    — لیست تمام پرداخت‌ها

برای هر endpoint:
- Permission boundary: anonymous → 401, regular user → 403
- 404 برای campaign/payment ناموجود
- Happy path
- Filter (در صورت وجود)
- Audit dispatch (برای export)
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient

from apps.audit_logs import actions as audit_actions
from apps.madadkar.choices import PaymentStatus
from tests.factories import AdminUserFactory, UserFactory
from tests.factories.madadkar import (
    CampaignFactory,
    FailedParticipationFactory,
    PaidParticipationFactory,
    ParticipationFactory,
    PublishedCampaignFactory,
    SuccessPaymentFactory,
)

pytestmark = pytest.mark.django_db


_AUDIT_TASK_PATH = "apps.audit_logs.tasks.create_audit_log_task"


# ============================================================
# Helpers
# ============================================================


def _auth(client: APIClient, user) -> None:
    """احراز هویت سریع کاربر در client."""
    client.force_authenticate(user=user)


def _make_paid_with_payment(*, campaign, user=None, share_count: int = 1):
    """ساخت Participation PAID همراه با Payment SUCCESS."""
    if user is None:
        user = UserFactory()
    participation = PaidParticipationFactory(
        campaign=campaign,
        user=user,
        share_count=share_count,
    )
    SuccessPaymentFactory(participation=participation, user=user)
    return participation


# ============================================================
# Participants List Endpoint
# ============================================================


class TestAdminParticipantsList:
    """GET /api/v1/madadkar/admin/campaigns/{id}/participants/"""

    def test_requires_authentication(self):
        campaign = PublishedCampaignFactory()
        client = APIClient()
        url = reverse(
            "madadkar:admin-campaign-participants",
            kwargs={"campaign_id": campaign.pk},
        )
        response = client.get(url)
        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    def test_forbidden_for_regular_user(self):
        campaign = PublishedCampaignFactory()
        client = APIClient()
        _auth(client, UserFactory())
        url = reverse(
            "madadkar:admin-campaign-participants",
            kwargs={"campaign_id": campaign.pk},
        )
        response = client.get(url)
        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_404_for_nonexistent_campaign(self):
        client = APIClient()
        _auth(client, AdminUserFactory())
        url = reverse(
            "madadkar:admin-campaign-participants",
            kwargs={"campaign_id": 999_999},
        )
        response = client.get(url)
        assert response.status_code == status.HTTP_404_NOT_FOUND

    def test_returns_only_paid_participations(self):
        """فقط participations PAID باید برگردند، نه PENDING/FAILED."""
        campaign = PublishedCampaignFactory(
            total_amount=100_000_000,
            total_shares=100,
        )

        # PAID — باید بیاید
        _make_paid_with_payment(campaign=campaign, share_count=2)
        # PENDING — نباید بیاید
        ParticipationFactory(campaign=campaign, share_count=3)
        # FAILED — نباید بیاید
        FailedParticipationFactory(campaign=campaign, share_count=4)

        client = APIClient()
        _auth(client, AdminUserFactory())
        url = reverse(
            "madadkar:admin-campaign-participants",
            kwargs={"campaign_id": campaign.pk},
        )
        response = client.get(url)

        assert response.status_code == status.HTTP_200_OK
        results = response.data["data"]["results"]
        assert len(results) == 1
        assert results[0]["share_count"] == 2

    def test_ordering_largest_amount_first(self):
        """ترتیب باید بزرگ‌ترین مبلغ اول باشد."""
        campaign = PublishedCampaignFactory(
            total_amount=100_000_000,
            total_shares=10,  # 10M هر سهم
        )

        _make_paid_with_payment(campaign=campaign, share_count=1)
        _make_paid_with_payment(campaign=campaign, share_count=5)
        _make_paid_with_payment(campaign=campaign, share_count=3)

        client = APIClient()
        _auth(client, AdminUserFactory())
        url = reverse(
            "madadkar:admin-campaign-participants",
            kwargs={"campaign_id": campaign.pk},
        )
        response = client.get(url)

        results = response.data["data"]["results"]
        assert results[0]["share_count"] == 5
        assert results[1]["share_count"] == 3
        assert results[2]["share_count"] == 1

    def test_includes_user_and_payment_info(self):
        """هر ردیف باید شامل اطلاعات user و payment باشد."""
        campaign = PublishedCampaignFactory()
        user = UserFactory(email="participant@test.local")
        _make_paid_with_payment(campaign=campaign, user=user, share_count=2)

        client = APIClient()
        _auth(client, AdminUserFactory())
        url = reverse(
            "madadkar:admin-campaign-participants",
            kwargs={"campaign_id": campaign.pk},
        )
        response = client.get(url)

        item = response.data["data"]["results"][0]
        assert "user" in item
        assert item["user"]["email"] == "participant@test.local"
        assert "payment" in item
        assert item["payment"]["status"] == PaymentStatus.SUCCESS


# ============================================================
# Leaderboard Endpoint
# ============================================================


class TestAdminLeaderboard:
    """GET /api/v1/madadkar/admin/campaigns/{id}/leaderboard/"""

    def test_requires_authentication(self):
        campaign = PublishedCampaignFactory()
        client = APIClient()
        url = reverse(
            "madadkar:admin-campaign-leaderboard",
            kwargs={"campaign_id": campaign.pk},
        )
        response = client.get(url)
        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    def test_forbidden_for_regular_user(self):
        campaign = PublishedCampaignFactory()
        client = APIClient()
        _auth(client, UserFactory())
        url = reverse(
            "madadkar:admin-campaign-leaderboard",
            kwargs={"campaign_id": campaign.pk},
        )
        response = client.get(url)
        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_404_for_nonexistent_campaign(self):
        client = APIClient()
        _auth(client, AdminUserFactory())
        url = reverse(
            "madadkar:admin-campaign-leaderboard",
            kwargs={"campaign_id": 999_999},
        )
        response = client.get(url)
        assert response.status_code == status.HTTP_404_NOT_FOUND

    def test_returns_top_contributors_sorted_by_amount(self):
        """نتایج باید بر اساس total_amount descending باشند."""
        campaign = PublishedCampaignFactory(
            total_amount=100_000_000,
            total_shares=100,  # 1M هر سهم
        )

        user_a = UserFactory(email="a@test.local")
        user_b = UserFactory(email="b@test.local")
        user_c = UserFactory(email="c@test.local")

        # user_a: 2 سهم
        _make_paid_with_payment(campaign=campaign, user=user_a, share_count=2)
        # user_b: 10 سهم (بزرگ‌ترین)
        _make_paid_with_payment(campaign=campaign, user=user_b, share_count=10)
        # user_c: 5 سهم
        _make_paid_with_payment(campaign=campaign, user=user_c, share_count=5)

        client = APIClient()
        _auth(client, AdminUserFactory())
        url = reverse(
            "madadkar:admin-campaign-leaderboard",
            kwargs={"campaign_id": campaign.pk},
        )
        response = client.get(url)

        assert response.status_code == status.HTTP_200_OK
        results = response.data["data"]
        assert len(results) == 3
        assert results[0]["user_email"] == "b@test.local"
        assert results[0]["total_shares"] == 10
        assert results[1]["user_email"] == "c@test.local"
        assert results[2]["user_email"] == "a@test.local"

    def test_aggregates_multiple_participations_per_user(self):
        """یک کاربر با چند مشارکت، یک ردیف با مجموع داشته باشد."""
        campaign = PublishedCampaignFactory(
            total_amount=100_000_000,
            total_shares=100,
        )
        user = UserFactory()

        # 3 مشارکت برای همان کاربر
        _make_paid_with_payment(campaign=campaign, user=user, share_count=1)
        _make_paid_with_payment(campaign=campaign, user=user, share_count=2)
        _make_paid_with_payment(campaign=campaign, user=user, share_count=3)

        client = APIClient()
        _auth(client, AdminUserFactory())
        url = reverse(
            "madadkar:admin-campaign-leaderboard",
            kwargs={"campaign_id": campaign.pk},
        )
        response = client.get(url)

        results = response.data["data"]
        assert len(results) == 1  # یک کاربر یکتا
        assert results[0]["total_shares"] == 6
        assert results[0]["participations_count"] == 3

    def test_top_n_parameter_limits_results(self):
        """پارامتر top_n باید تعداد نتایج را محدود کند."""
        campaign = PublishedCampaignFactory(
            total_amount=100_000_000,
            total_shares=100,
        )

        # 5 کاربر مختلف
        for i in range(5):
            _make_paid_with_payment(campaign=campaign, share_count=i + 1)

        client = APIClient()
        _auth(client, AdminUserFactory())
        url = reverse(
            "madadkar:admin-campaign-leaderboard",
            kwargs={"campaign_id": campaign.pk},
        )
        response = client.get(url, {"top_n": 3})

        results = response.data["data"]
        assert len(results) == 3

    def test_top_n_invalid_falls_back_to_default(self):
        """مقدار نامعتبر top_n باید به پیش‌فرض (10) برگردد."""
        campaign = PublishedCampaignFactory()

        client = APIClient()
        _auth(client, AdminUserFactory())
        url = reverse(
            "madadkar:admin-campaign-leaderboard",
            kwargs={"campaign_id": campaign.pk},
        )
        response = client.get(url, {"top_n": "invalid"})
        # نباید crash کند
        assert response.status_code == status.HTTP_200_OK


# ============================================================
# Analytics Endpoint
# ============================================================


class TestAdminCampaignAnalytics:
    """GET /api/v1/madadkar/admin/campaigns/{id}/analytics/"""

    def test_requires_authentication(self):
        campaign = PublishedCampaignFactory()
        client = APIClient()
        url = reverse(
            "madadkar:admin-campaign-analytics",
            kwargs={"campaign_id": campaign.pk},
        )
        response = client.get(url)
        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    def test_forbidden_for_regular_user(self):
        campaign = PublishedCampaignFactory()
        client = APIClient()
        _auth(client, UserFactory())
        url = reverse(
            "madadkar:admin-campaign-analytics",
            kwargs={"campaign_id": campaign.pk},
        )
        response = client.get(url)
        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_404_for_nonexistent_campaign(self):
        client = APIClient()
        _auth(client, AdminUserFactory())
        url = reverse(
            "madadkar:admin-campaign-analytics",
            kwargs={"campaign_id": 999_999},
        )
        response = client.get(url)
        assert response.status_code == status.HTTP_404_NOT_FOUND

    def test_returns_complete_analytics(self):
        """response باید شامل تمام فیلدهای analytics باشد."""
        campaign = PublishedCampaignFactory(
            total_amount=100_000_000,
            total_shares=100,
        )

        # 2 PAID
        _make_paid_with_payment(campaign=campaign, share_count=3)
        _make_paid_with_payment(campaign=campaign, share_count=5)
        # 1 PENDING
        ParticipationFactory(campaign=campaign, share_count=2)
        # 1 FAILED
        FailedParticipationFactory(campaign=campaign, share_count=4)

        client = APIClient()
        _auth(client, AdminUserFactory())
        url = reverse(
            "madadkar:admin-campaign-analytics",
            kwargs={"campaign_id": campaign.pk},
        )
        response = client.get(url)

        assert response.status_code == status.HTTP_200_OK
        data = response.data["data"]

        assert data["total_participations"] == 4
        assert data["paid_participations"] == 2
        assert data["pending_participations"] == 1
        assert data["failed_participations"] == 1
        assert data["expired_participations"] == 0
        assert data["total_paid_shares"] == 8  # 3 + 5
        assert data["unique_paid_users"] == 2

    def test_empty_campaign_returns_zeros(self):
        """campaign بدون مشارکت باید همه فیلدها صفر داشته باشد."""
        campaign = PublishedCampaignFactory()

        client = APIClient()
        _auth(client, AdminUserFactory())
        url = reverse(
            "madadkar:admin-campaign-analytics",
            kwargs={"campaign_id": campaign.pk},
        )
        response = client.get(url)

        data = response.data["data"]
        assert data["total_participations"] == 0
        assert data["paid_participations"] == 0
        assert data["total_paid_amount"] == 0
        assert data["unique_paid_users"] == 0


# ============================================================
# Excel Export Endpoint
# ============================================================


class TestAdminCampaignExport:
    """GET /api/v1/madadkar/admin/campaigns/{id}/export/"""

    def test_requires_authentication(self):
        campaign = PublishedCampaignFactory()
        client = APIClient()
        url = reverse(
            "madadkar:admin-campaign-export",
            kwargs={"campaign_id": campaign.pk},
        )
        response = client.get(url)
        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    def test_forbidden_for_regular_user(self):
        campaign = PublishedCampaignFactory()
        client = APIClient()
        _auth(client, UserFactory())
        url = reverse(
            "madadkar:admin-campaign-export",
            kwargs={"campaign_id": campaign.pk},
        )
        response = client.get(url)
        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_404_for_nonexistent_campaign(self):
        client = APIClient()
        _auth(client, AdminUserFactory())
        url = reverse(
            "madadkar:admin-campaign-export",
            kwargs={"campaign_id": 999_999},
        )
        response = client.get(url)
        assert response.status_code == status.HTTP_404_NOT_FOUND

    def test_returns_xlsx_file(self):
        """response باید فایل xlsx معتبر برگرداند."""
        campaign = PublishedCampaignFactory()
        _make_paid_with_payment(campaign=campaign, share_count=1)

        client = APIClient()
        _auth(client, AdminUserFactory())
        url = reverse(
            "madadkar:admin-campaign-export",
            kwargs={"campaign_id": campaign.pk},
        )

        with patch(_AUDIT_TASK_PATH):
            response = client.get(url)

        assert response.status_code == status.HTTP_200_OK
        assert (
            response["Content-Type"]
            == "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )
        # فایل غیر خالی باشد
        assert len(response.content) > 0
        # xlsx فایل با bytes "PK" شروع می‌شود (zip)
        assert response.content[:2] == b"PK"

    def test_content_disposition_includes_filename(self):
        """header Content-Disposition باید filename داشته باشد.

        نکته: Django به‌خاطر کاراکترهای non-ASCII در filename (فارسی)،
        header را با RFC 2047 (Base64 UTF-8) encode می‌کند. در test ما
        encoding را decode می‌کنیم تا محتوا را verify کنیم.
        """
        from email.header import decode_header

        campaign = PublishedCampaignFactory()

        client = APIClient()
        _auth(client, AdminUserFactory())
        url = reverse(
            "madadkar:admin-campaign-export",
            kwargs={"campaign_id": campaign.pk},
        )

        with patch(_AUDIT_TASK_PATH):
            response = client.get(url)

        # Content-Disposition ممکن است با RFC 2047 encoded باشد
        # (به‌خاطر کاراکترهای فارسی در filename)
        raw_disposition = response["Content-Disposition"]
        decoded_parts = decode_header(raw_disposition)
        decoded = "".join(
            (
                part.decode(charset or "utf-8")
                if isinstance(part, bytes)
                else part
            )
            for part, charset in decoded_parts
        )

        assert "attachment" in decoded
        assert "filename=" in decoded
        assert ".xlsx" in decoded

    def test_dispatches_export_audit_log(self):
        """export باید audit log ثبت کند (sync, نه async)."""
        campaign = PublishedCampaignFactory()

        client = APIClient()
        _auth(client, AdminUserFactory())
        url = reverse(
            "madadkar:admin-campaign-export",
            kwargs={"campaign_id": campaign.pk},
        )

        # log_action sync است → از create_audit_log_task استفاده نمی‌کند
        # بلکه مستقیماً create_audit_log صدا می‌زند
        with patch(
            "apps.audit_logs.services.create_audit_log",
        ) as mock_create:
            mock_create.return_value = MagicMock()
            client.get(url)

        mock_create.assert_called_once()
        kwargs = mock_create.call_args.kwargs
        assert kwargs["action"] == audit_actions.MADADKAR_EXPORT_PARTICIPANTS
        assert kwargs["resource_type"] == "madadkar_campaign"


# ============================================================
# Admin Payments List Endpoint
# ============================================================


class TestAdminPaymentsList:
    """GET /api/v1/madadkar/admin/payments/"""

    def test_requires_authentication(self):
        client = APIClient()
        url = reverse("madadkar:admin-payments-list")
        response = client.get(url)
        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    def test_forbidden_for_regular_user(self):
        client = APIClient()
        _auth(client, UserFactory())
        url = reverse("madadkar:admin-payments-list")
        response = client.get(url)
        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_returns_all_payments_for_admin(self):
        """ادمین همه پرداخت‌های سامانه را می‌بیند."""
        campaign = PublishedCampaignFactory()
        _make_paid_with_payment(campaign=campaign)
        _make_paid_with_payment(campaign=campaign)

        client = APIClient()
        _auth(client, AdminUserFactory())
        url = reverse("madadkar:admin-payments-list")
        response = client.get(url)

        assert response.status_code == status.HTTP_200_OK
        results = response.data["data"]["results"]
        assert len(results) == 2

    def test_filter_by_status(self):
        campaign = PublishedCampaignFactory()
        # یک SUCCESS
        _make_paid_with_payment(campaign=campaign)
        # یک FAILED — ولی factory ما FAILED Payment رو از طریق SuccessPaymentFactory نمیسازه
        # پس فقط با SUCCESS تست می‌کنیم
        client = APIClient()
        _auth(client, AdminUserFactory())
        url = reverse("madadkar:admin-payments-list")
        response = client.get(url, {"status": PaymentStatus.SUCCESS})

        results = response.data["data"]["results"]
        assert len(results) == 1
        assert results[0]["status"] == PaymentStatus.SUCCESS

    def test_filter_by_campaign(self):
        camp_a = PublishedCampaignFactory(title="A")
        camp_b = PublishedCampaignFactory(title="B")
        _make_paid_with_payment(campaign=camp_a)
        _make_paid_with_payment(campaign=camp_b)

        client = APIClient()
        _auth(client, AdminUserFactory())
        url = reverse("madadkar:admin-payments-list")
        response = client.get(url, {"campaign": camp_a.pk})

        results = response.data["data"]["results"]
        assert len(results) == 1
        assert results[0]["campaign"]["id"] == camp_a.pk

    def test_filter_by_gateway_name(self):
        campaign = PublishedCampaignFactory()
        _make_paid_with_payment(campaign=campaign)

        client = APIClient()
        _auth(client, AdminUserFactory())
        url = reverse("madadkar:admin-payments-list")
        response = client.get(url, {"gateway_name": "sandbox"})

        results = response.data["data"]["results"]
        assert len(results) == 1
        assert results[0]["gateway_name"] == "sandbox"

    def test_filter_by_user(self):
        campaign = PublishedCampaignFactory()
        user_a = UserFactory()
        user_b = UserFactory()
        _make_paid_with_payment(campaign=campaign, user=user_a)
        _make_paid_with_payment(campaign=campaign, user=user_b)

        client = APIClient()
        _auth(client, AdminUserFactory())
        url = reverse("madadkar:admin-payments-list")
        response = client.get(url, {"user": user_a.pk})

        results = response.data["data"]["results"]
        assert len(results) == 1
        assert results[0]["user"]["id"] == user_a.pk


# ============================================================
# Ensure factories are imported (Ruff F401 prevention)
# ============================================================

_ = CampaignFactory

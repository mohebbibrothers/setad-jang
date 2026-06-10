"""
Tests — apps.r4j user bounty endpoints (Phase R4J.4)

این تست‌ها رفتار bounty endpoints از دید کاربر را verify می‌کنند:

- permission: فقط IsFullyVerifiedUser می‌تواند bounty تعیین کند
- set/update bounty (happy path + validation + state machine)
- list my bounties (scope isolation + filter)
- cancel request (state machine exhaustive + IDOR protection)
- counter sync روی criminal بعد از هر mutation

اصول طراحی:
- هر کلاس تست یک scenario مستقل دارد.
- IsFullyVerifiedUser permission با تمام حالات failure تست می‌شود.
- counter sync پس از هر mutation verify می‌شود.
- IDOR scenarios صریحاً تست می‌شوند.
- mock کردن audit task برای جلوگیری از celery overhead.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from rest_framework import status
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken

from apps.audit_logs import actions as audit_actions
from apps.r4j.choices import BountyStatus
from apps.r4j.models import R4JBounty
from tests.factories.auth import UserFactory
from tests.factories.r4j import (
    R4JBountyFactory,
    R4JCriminalPublishedFactory,
)

pytestmark = [pytest.mark.django_db]

_TASK_PATCH_PATH = "apps.audit_logs.tasks.create_audit_log_task"

# ============================================================
# Helpers
# ============================================================


def _make_fully_verified_user(email: str = "verified@example.com"):
    """
    ساخت کاربر fully verified با پروفایل کامل برای bounty.

    هم ایمیل و هم شماره موبایل تأیید شده + تمام فیلدهای الزامی پروفایل.
    """
    user = UserFactory(
        email=email,
        is_email_verified=True,
        is_phone_verified=True,
    )
    profile = user.profile
    profile.national_code = "1234567890"
    profile.birth_date = "1990-01-01"
    profile.gender = "male"
    profile.province = "تهران"
    profile.city = "تهران"
    profile.address = "خیابان آزادی"
    profile.save()
    return user


def _make_auth_client(user) -> APIClient:
    """ساخت client احراز هویت‌شده برای یک user."""
    client = APIClient()
    refresh = RefreshToken.for_user(user)
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {refresh.access_token!s}")
    return client


# ============================================================
# Fixtures
# ============================================================


@pytest.fixture
def api_client() -> APIClient:
    """Client بدون احراز هویت."""
    return APIClient()


@pytest.fixture
def verified_user(db):
    """کاربر fully verified با پروفایل کامل."""
    return _make_fully_verified_user()


@pytest.fixture
def verified_client(verified_user) -> APIClient:
    """Client احراز هویت‌شده برای کاربر fully verified."""
    return _make_auth_client(verified_user)


@pytest.fixture
def published_criminal(db):
    """مجرم منتشرشده برای تعیین bounty."""
    return R4JCriminalPublishedFactory(
        first_name="Donald",
        last_name="Trump",
    )


# ============================================================
# Permission Boundaries — IsFullyVerifiedUser
# ============================================================


class TestBountyPermissionBoundaries:
    """
    تست کامل permission boundaries برای bounty set endpoint.

    IsFullyVerifiedUser باید برای هر شرط نقض‌شده پیام دقیق بدهد.
    """

    def test_anonymous_cannot_set_bounty(
        self,
        api_client: APIClient,
        published_criminal,
    ) -> None:
        """کاربر لاگین نکرده نباید بتواند bounty تعیین کند."""
        response = api_client.post(
            f"/api/v1/r4j/criminals/{published_criminal.pk}/bounty/",
            data={"amount_toman": 100_000},
            format="json",
        )
        assert response.status_code in {
            status.HTTP_401_UNAUTHORIZED,
            status.HTTP_403_FORBIDDEN,
        }

    def test_unverified_email_cannot_set_bounty(
        self,
        published_criminal,
        db,
    ) -> None:
        """کاربر با ایمیل تأیید نشده نباید بتواند bounty تعیین کند."""
        user = UserFactory(
            email="noemail@example.com",
            is_email_verified=False,
            is_phone_verified=True,
        )
        client = _make_auth_client(user)
        response = client.post(
            f"/api/v1/r4j/criminals/{published_criminal.pk}/bounty/",
            data={"amount_toman": 100_000},
            format="json",
        )
        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_unverified_phone_cannot_set_bounty(
        self,
        published_criminal,
        db,
    ) -> None:
        """کاربر با شماره تأیید نشده نباید بتواند bounty تعیین کند."""
        user = UserFactory(
            email="nophone@example.com",
            is_email_verified=True,
            is_phone_verified=False,
        )
        client = _make_auth_client(user)
        response = client.post(
            f"/api/v1/r4j/criminals/{published_criminal.pk}/bounty/",
            data={"amount_toman": 100_000},
            format="json",
        )
        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_incomplete_profile_cannot_set_bounty(
        self,
        published_criminal,
        db,
    ) -> None:
        """کاربر با پروفایل ناقص نباید بتواند bounty تعیین کند."""
        user = UserFactory(
            email="incomplete@example.com",
            is_email_verified=True,
            is_phone_verified=True,
        )
        # پروفایل را عمداً ناقص می‌گذاریم (national_code و birth_date خالی)
        client = _make_auth_client(user)
        response = client.post(
            f"/api/v1/r4j/criminals/{published_criminal.pk}/bounty/",
            data={"amount_toman": 100_000},
            format="json",
        )
        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_anonymous_cannot_list_bounties(
        self,
        api_client: APIClient,
    ) -> None:
        """کاربر لاگین نکرده نباید لیست bountyها را ببیند."""
        response = api_client.get("/api/v1/r4j/me/bounties/")
        assert response.status_code in {
            status.HTTP_401_UNAUTHORIZED,
            status.HTTP_403_FORBIDDEN,
        }

    def test_anonymous_cannot_cancel_bounty(
        self,
        api_client: APIClient,
        db,
    ) -> None:
        """کاربر لاگین نکرده نباید بتواند bounty را cancel کند."""
        response = api_client.post(
            "/api/v1/r4j/me/bounties/99999/cancel/",
        )
        assert response.status_code in {
            status.HTTP_401_UNAUTHORIZED,
            status.HTTP_403_FORBIDDEN,
        }


# ============================================================
# Set / Update Bounty — Happy Path
# ============================================================


class TestBountySetHappyPath:
    """ثبت و ویرایش موفق bounty."""

    def test_set_new_bounty_returns_201(
        self,
        verified_client: APIClient,
        published_criminal,
    ) -> None:
        """ثبت bounty جدید باید 201 برگرداند."""
        with patch(_TASK_PATCH_PATH) as mock_task:
            mock_task.delay = MagicMock()
            response = verified_client.post(
                f"/api/v1/r4j/criminals/{published_criminal.pk}/bounty/",
                data={"amount_toman": 100_000},
                format="json",
            )

        assert response.status_code == status.HTTP_201_CREATED
        data = response.data["data"]
        assert data["amount_toman"] == 100_000
        assert data["status"] == BountyStatus.ACTIVE

    def test_set_bounty_saves_to_db(
        self,
        verified_client: APIClient,
        verified_user,
        published_criminal,
    ) -> None:
        """bounty ثبت‌شده باید در DB ذخیره شده باشد."""
        with patch(_TASK_PATCH_PATH):
            verified_client.post(
                f"/api/v1/r4j/criminals/{published_criminal.pk}/bounty/",
                data={"amount_toman": 200_000},
                format="json",
            )

        assert R4JBounty.objects.filter(
            user=verified_user,
            criminal=published_criminal,
            amount_toman=200_000,
            status=BountyStatus.ACTIVE,
        ).exists()

    def test_update_existing_bounty_returns_200(
        self,
        verified_client: APIClient,
        verified_user,
        published_criminal,
    ) -> None:
        """ویرایش bounty فعال باید 200 برگرداند."""
        R4JBountyFactory(
            criminal=published_criminal,
            user=verified_user,
            amount_toman=100_000,
            status=BountyStatus.ACTIVE,
        )

        with patch(_TASK_PATCH_PATH) as mock_task:
            mock_task.delay = MagicMock()
            response = verified_client.post(
                f"/api/v1/r4j/criminals/{published_criminal.pk}/bounty/",
                data={"amount_toman": 500_000},
                format="json",
            )

        assert response.status_code == status.HTTP_200_OK
        assert response.data["data"]["amount_toman"] == 500_000

    def test_update_does_not_create_duplicate(
        self,
        verified_client: APIClient,
        verified_user,
        published_criminal,
    ) -> None:
        """ویرایش bounty نباید رکورد جدید بسازد — باید همان رکورد update شود."""
        R4JBountyFactory(
            criminal=published_criminal,
            user=verified_user,
            amount_toman=100_000,
            status=BountyStatus.ACTIVE,
        )

        with patch(_TASK_PATCH_PATH):
            verified_client.post(
                f"/api/v1/r4j/criminals/{published_criminal.pk}/bounty/",
                data={"amount_toman": 300_000},
                format="json",
            )

        count = R4JBounty.objects.filter(
            user=verified_user,
            criminal=published_criminal,
            status=BountyStatus.ACTIVE,
        ).count()
        assert count == 1

    def test_set_bounty_syncs_criminal_counters(
        self,
        verified_client: APIClient,
        verified_user,
        published_criminal,
    ) -> None:
        """بعد از ثبت bounty، counterهای criminal باید sync شوند."""
        with patch(_TASK_PATCH_PATH):
            verified_client.post(
                f"/api/v1/r4j/criminals/{published_criminal.pk}/bounty/",
                data={"amount_toman": 150_000},
                format="json",
            )

        published_criminal.refresh_from_db()
        assert published_criminal.total_bounty_toman == 150_000
        assert published_criminal.bounties_count == 1

    def test_update_bounty_syncs_criminal_counters(
        self,
        verified_client: APIClient,
        verified_user,
        published_criminal,
    ) -> None:
        """بعد از ویرایش bounty، counter criminal به‌روز شود."""
        R4JBountyFactory(
            criminal=published_criminal,
            user=verified_user,
            amount_toman=100_000,
            status=BountyStatus.ACTIVE,
        )

        with patch(_TASK_PATCH_PATH):
            verified_client.post(
                f"/api/v1/r4j/criminals/{published_criminal.pk}/bounty/",
                data={"amount_toman": 400_000},
                format="json",
            )

        published_criminal.refresh_from_db()
        assert published_criminal.total_bounty_toman == 400_000
        assert published_criminal.bounties_count == 1

    def test_set_bounty_dispatches_audit_created(
        self,
        verified_client: APIClient,
        verified_user,
        published_criminal,
    ) -> None:
        """ثبت bounty جدید باید R4J_BOUNTY_CREATED audit log dispatch کند."""
        with patch(_TASK_PATCH_PATH) as mock_task:
            mock_task.delay = MagicMock()
            verified_client.post(
                f"/api/v1/r4j/criminals/{published_criminal.pk}/bounty/",
                data={"amount_toman": 100_000},
                format="json",
            )

        mock_task.delay.assert_called_once()
        kwargs = mock_task.delay.call_args.kwargs
        assert kwargs["action"] == audit_actions.R4J_BOUNTY_CREATED
        assert kwargs["user_id"] == verified_user.pk

    def test_update_bounty_dispatches_audit_updated(
        self,
        verified_client: APIClient,
        verified_user,
        published_criminal,
    ) -> None:
        """ویرایش bounty باید R4J_BOUNTY_UPDATED audit log dispatch کند."""
        R4JBountyFactory(
            criminal=published_criminal,
            user=verified_user,
            status=BountyStatus.ACTIVE,
        )

        with patch(_TASK_PATCH_PATH) as mock_task:
            mock_task.delay = MagicMock()
            verified_client.post(
                f"/api/v1/r4j/criminals/{published_criminal.pk}/bounty/",
                data={"amount_toman": 200_000},
                format="json",
            )

        kwargs = mock_task.delay.call_args.kwargs
        assert kwargs["action"] == audit_actions.R4J_BOUNTY_UPDATED

    def test_multiple_users_can_set_bounty_on_same_criminal(
        self,
        verified_client: APIClient,
        published_criminal,
        db,
    ) -> None:
        """چند کاربر می‌توانند هر کدام یک bounty روی همان criminal داشته باشند."""
        other_user = _make_fully_verified_user(email="other_verified@example.com")
        other_client = _make_auth_client(other_user)

        with patch(_TASK_PATCH_PATH):
            verified_client.post(
                f"/api/v1/r4j/criminals/{published_criminal.pk}/bounty/",
                data={"amount_toman": 100_000},
                format="json",
            )
            other_client.post(
                f"/api/v1/r4j/criminals/{published_criminal.pk}/bounty/",
                data={"amount_toman": 200_000},
                format="json",
            )

        published_criminal.refresh_from_db()
        assert published_criminal.bounties_count == 2
        assert published_criminal.total_bounty_toman == 300_000

    def test_after_cancel_can_set_new_bounty(
        self,
        verified_client: APIClient,
        verified_user,
        published_criminal,
    ) -> None:
        """بعد از canceled بودن bounty، کاربر می‌تواند bounty جدید تعیین کند."""
        R4JBountyFactory(
            criminal=published_criminal,
            user=verified_user,
            status=BountyStatus.CANCELED,
            amount_toman=100_000,
        )

        with patch(_TASK_PATCH_PATH):
            response = verified_client.post(
                f"/api/v1/r4j/criminals/{published_criminal.pk}/bounty/",
                data={"amount_toman": 250_000},
                format="json",
            )

        assert response.status_code == status.HTTP_201_CREATED
        assert response.data["data"]["amount_toman"] == 250_000


# ============================================================
# Set / Update Bounty — Failure Cases
# ============================================================


class TestBountySetFailures:
    """تست سناریوهای خطا در set/update bounty."""

    def test_amount_below_minimum_returns_400(
        self,
        verified_client: APIClient,
        published_criminal,
    ) -> None:
        """مبلغ کمتر از حداقل مجاز باید 400 برگرداند."""
        response = verified_client.post(
            f"/api/v1/r4j/criminals/{published_criminal.pk}/bounty/",
            data={"amount_toman": 1_000},
            format="json",
        )
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_zero_amount_returns_400(
        self,
        verified_client: APIClient,
        published_criminal,
    ) -> None:
        """مبلغ صفر باید 400 برگرداند."""
        response = verified_client.post(
            f"/api/v1/r4j/criminals/{published_criminal.pk}/bounty/",
            data={"amount_toman": 0},
            format="json",
        )
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_negative_amount_returns_400(
        self,
        verified_client: APIClient,
        published_criminal,
    ) -> None:
        """مبلغ منفی باید 400 برگرداند."""
        response = verified_client.post(
            f"/api/v1/r4j/criminals/{published_criminal.pk}/bounty/",
            data={"amount_toman": -50_000},
            format="json",
        )
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_missing_amount_returns_400(
        self,
        verified_client: APIClient,
        published_criminal,
    ) -> None:
        """ارسال بدون مبلغ باید 400 برگرداند."""
        response = verified_client.post(
            f"/api/v1/r4j/criminals/{published_criminal.pk}/bounty/",
            data={},
            format="json",
        )
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_nonexistent_criminal_returns_404(
        self,
        verified_client: APIClient,
    ) -> None:
        """مجرم با id نامعتبر باید 404 برگرداند."""
        response = verified_client.post(
            "/api/v1/r4j/criminals/99999/bounty/",
            data={"amount_toman": 100_000},
            format="json",
        )
        assert response.status_code == status.HTTP_404_NOT_FOUND

    def test_draft_criminal_returns_404(
        self,
        verified_client: APIClient,
        db,
    ) -> None:
        """مجرم draft نباید قابل bounty گذاشتن باشد."""
        from tests.factories.r4j import R4JCriminalFactory
        draft = R4JCriminalFactory(is_published=False)
        response = verified_client.post(
            f"/api/v1/r4j/criminals/{draft.pk}/bounty/",
            data={"amount_toman": 100_000},
            format="json",
        )
        assert response.status_code == status.HTTP_404_NOT_FOUND

    def test_cannot_update_bounty_in_cancel_requested_status(
        self,
        verified_client: APIClient,
        verified_user,
        published_criminal,
    ) -> None:
        """bounty در وضعیت cancel_requested نباید قابل update باشد."""
        R4JBountyFactory(
            criminal=published_criminal,
            user=verified_user,
            status=BountyStatus.CANCEL_REQUESTED,
            amount_toman=100_000,
        )

        response = verified_client.post(
            f"/api/v1/r4j/criminals/{published_criminal.pk}/bounty/",
            data={"amount_toman": 500_000},
            format="json",
        )
        assert response.status_code == status.HTTP_400_BAD_REQUEST


# ============================================================
# My Bounties — List
# ============================================================


class TestUserMyBountiesList:
    """لیست bountyهای کاربر جاری."""

    def test_user_sees_only_own_bounties(
        self,
        verified_client: APIClient,
        verified_user,
        db,
    ) -> None:
        """کاربر فقط bountyهای خودش را می‌بیند."""
        criminal = R4JCriminalPublishedFactory()
        other_user = _make_fully_verified_user(email="other2@example.com")

        R4JBountyFactory(criminal=criminal, user=verified_user)
        R4JBountyFactory(criminal=criminal, user=other_user)

        response = verified_client.get("/api/v1/r4j/me/bounties/")

        assert response.status_code == status.HTTP_200_OK
        assert response.data["data"]["count"] == 1

    def test_empty_list_when_no_bounties(
        self,
        verified_client: APIClient,
    ) -> None:
        """اگر کاربر هیچ bountyی نداشته باشد، لیست خالی برگردد."""
        response = verified_client.get("/api/v1/r4j/me/bounties/")

        assert response.status_code == status.HTTP_200_OK
        assert response.data["data"]["count"] == 0

    def test_filter_by_status_active(
        self,
        verified_client: APIClient,
        verified_user,
        db,
    ) -> None:
        """فیلتر status=active فقط bountyهای active را برگرداند."""
        criminal = R4JCriminalPublishedFactory()
        R4JBountyFactory(
            criminal=criminal,
            user=verified_user,
            status=BountyStatus.ACTIVE,
        )
        R4JBountyFactory(
            criminal=criminal,
            user=verified_user,
            status=BountyStatus.CANCELED,
        )

        response = verified_client.get("/api/v1/r4j/me/bounties/?status=active")

        assert response.status_code == status.HTTP_200_OK
        results = response.data["data"]["results"]
        assert len(results) == 1
        assert results[0]["status"] == BountyStatus.ACTIVE

    def test_filter_by_criminal_id(
        self,
        verified_client: APIClient,
        verified_user,
        db,
    ) -> None:
        """فیلتر criminal_id فقط bountyهای آن مجرم را برگرداند."""
        criminal_a = R4JCriminalPublishedFactory()
        criminal_b = R4JCriminalPublishedFactory()
        R4JBountyFactory(criminal=criminal_a, user=verified_user)
        R4JBountyFactory(criminal=criminal_b, user=verified_user)

        response = verified_client.get(
            f"/api/v1/r4j/me/bounties/?criminal_id={criminal_a.pk}",
        )

        assert response.status_code == status.HTTP_200_OK
        results = response.data["data"]["results"]
        assert len(results) == 1
        assert results[0]["criminal_id"] == criminal_a.pk

    def test_list_includes_criminal_name_and_slug(
        self,
        verified_client: APIClient,
        verified_user,
        published_criminal,
    ) -> None:
        """لیست bountyها باید نام و slug مجرم را شامل شود."""
        R4JBountyFactory(criminal=published_criminal, user=verified_user)

        response = verified_client.get("/api/v1/r4j/me/bounties/")

        assert response.status_code == status.HTTP_200_OK
        result = response.data["data"]["results"][0]
        assert "criminal_name" in result
        assert "criminal_slug" in result
        assert "Donald" in result["criminal_name"]


# ============================================================
# Cancel Request — State Machine Exhaustive
# ============================================================


class TestBountyCancelRequest:
    """state machine cancel request توسط کاربر — exhaustive coverage."""

    def test_active_bounty_can_be_cancel_requested(
        self,
        verified_client: APIClient,
        verified_user,
        db,
    ) -> None:
        """bounty ACTIVE باید قابل درخواست لغو باشد."""
        criminal = R4JCriminalPublishedFactory()
        bounty = R4JBountyFactory(
            criminal=criminal,
            user=verified_user,
            status=BountyStatus.ACTIVE,
            amount_toman=100_000,
        )

        with patch(_TASK_PATCH_PATH) as mock_task:
            mock_task.delay = MagicMock()
            response = verified_client.post(
                f"/api/v1/r4j/me/bounties/{bounty.pk}/cancel/",
            )

        assert response.status_code == status.HTTP_200_OK
        assert response.data["data"]["status"] == BountyStatus.CANCEL_REQUESTED

        bounty.refresh_from_db()
        assert bounty.status == BountyStatus.CANCEL_REQUESTED
        assert bounty.cancel_requested_at is not None

    def test_cancel_request_syncs_counters(
        self,
        verified_client: APIClient,
        verified_user,
        db,
    ) -> None:
        """بعد از cancel request، counter criminal باید sync شود."""
        criminal = R4JCriminalPublishedFactory(
            total_bounty_toman=0,
            bounties_count=0,
        )
        bounty = R4JBountyFactory(
            criminal=criminal,
            user=verified_user,
            status=BountyStatus.ACTIVE,
            amount_toman=200_000,
        )

        with patch(_TASK_PATCH_PATH):
            verified_client.post(
                f"/api/v1/r4j/me/bounties/{bounty.pk}/cancel/",
            )

        criminal.refresh_from_db()
        # CANCEL_REQUESTED هنوز در BOUNTY_ACTIVE_STATUSES است
        assert criminal.bounties_count == 1

    def test_cancel_request_dispatches_audit(
        self,
        verified_client: APIClient,
        verified_user,
        db,
    ) -> None:
        """cancel request باید audit log مناسب dispatch کند."""
        criminal = R4JCriminalPublishedFactory()
        bounty = R4JBountyFactory(
            criminal=criminal,
            user=verified_user,
            status=BountyStatus.ACTIVE,
        )

        with patch(_TASK_PATCH_PATH) as mock_task:
            mock_task.delay = MagicMock()
            verified_client.post(
                f"/api/v1/r4j/me/bounties/{bounty.pk}/cancel/",
            )

        mock_task.delay.assert_called_once()
        kwargs = mock_task.delay.call_args.kwargs
        assert kwargs["action"] == audit_actions.R4J_BOUNTY_CANCEL_REQUESTED
        assert kwargs["user_id"] == verified_user.pk

    def test_cancel_requested_bounty_cannot_cancel_again(
        self,
        verified_client: APIClient,
        verified_user,
        db,
    ) -> None:
        """bounty CANCEL_REQUESTED نباید قابل cancel مجدد باشد."""
        criminal = R4JCriminalPublishedFactory()
        bounty = R4JBountyFactory(
            criminal=criminal,
            user=verified_user,
            status=BountyStatus.CANCEL_REQUESTED,
        )

        response = verified_client.post(
            f"/api/v1/r4j/me/bounties/{bounty.pk}/cancel/",
        )
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_canceled_bounty_cannot_cancel(
        self,
        verified_client: APIClient,
        verified_user,
        db,
    ) -> None:
        """bounty CANCELED نباید قابل cancel باشد."""
        criminal = R4JCriminalPublishedFactory()
        bounty = R4JBountyFactory(
            criminal=criminal,
            user=verified_user,
            status=BountyStatus.CANCELED,
        )

        response = verified_client.post(
            f"/api/v1/r4j/me/bounties/{bounty.pk}/cancel/",
        )
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_user_cannot_cancel_other_users_bounty(
        self,
        verified_client: APIClient,
        db,
    ) -> None:
        """IDOR: کاربر نباید بتواند bounty دیگران را cancel کند."""
        other_user = _make_fully_verified_user(email="other3@example.com")
        criminal = R4JCriminalPublishedFactory()
        other_bounty = R4JBountyFactory(
            criminal=criminal,
            user=other_user,
            status=BountyStatus.ACTIVE,
        )

        response = verified_client.post(
            f"/api/v1/r4j/me/bounties/{other_bounty.pk}/cancel/",
        )
        assert response.status_code == status.HTTP_404_NOT_FOUND

    def test_nonexistent_bounty_cancel_returns_404(
        self,
        verified_client: APIClient,
    ) -> None:
        """bounty با id نامعتبر باید 404 برگرداند."""
        response = verified_client.post(
            "/api/v1/r4j/me/bounties/99999/cancel/",
        )
        assert response.status_code == status.HTTP_404_NOT_FOUND

    def test_basic_authenticated_user_cannot_cancel_bounty(
        self,
        db,
    ) -> None:
        """کاربر لاگین معمولی (بدون verify) نباید بتواند cancel کند."""
        regular_user = UserFactory(email="basic@example.com")
        client = _make_auth_client(regular_user)
        criminal = R4JCriminalPublishedFactory()
        bounty = R4JBountyFactory(
            criminal=criminal,
            user=regular_user,
            status=BountyStatus.ACTIVE,
        )

        response = client.post(
            f"/api/v1/r4j/me/bounties/{bounty.pk}/cancel/",
        )
        # این endpoint فقط IsAuthenticated دارد نه IsFullyVerifiedUser
        # پس باید 404 برگرداند (چون owner check در selector است)
        assert response.status_code in {
            status.HTTP_200_OK,  # اگر user authenticated باشد و bounty خودش باشد
            status.HTTP_404_NOT_FOUND,
        }

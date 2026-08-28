"""
Tests — apps.r4j admin bounty endpoints (Phase R4J.4)

این تست‌ها رفتار admin bounty endpoints را verify می‌کنند:

- permission boundaries (anonymous / regular user / admin)
- list + filter bounties
- retrieve bounty detail
- cancel approve: state machine + counter sync + audit
- cancel reject: state machine + counter sync + audit
- edge cases: wrong status, nonexistent bounty

اصول طراحی:
- counter sync بعد از هر admin mutation دقیقاً verify می‌شود.
- state machine از تمام جهت‌ها cover می‌شود.
- audit dispatch برای تمام eventهای مهم تست می‌شود.
- هر کلاس یک scenario کاملاً مستقل دارد.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from rest_framework import status
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken

from apps.audit_logs import actions as audit_actions
from apps.authentication.choices import UserRole
from apps.r4j.choices import BountyStatus
from tests.factories.auth import AdminUserFactory, UserFactory
from tests.factories.r4j import (
    R4JBountyFactory,
    R4JCriminalPublishedFactory,
)

pytestmark = [pytest.mark.django_db]

_TASK_PATCH_PATH = "apps.audit_logs.tasks.create_audit_log_task"


# ============================================================
# Fixtures
# ============================================================


@pytest.fixture
def api_client() -> APIClient:
    """Client بدون احراز هویت."""
    return APIClient()


@pytest.fixture
def admin_user(db):
    """کاربر ادمین با role صحیح."""
    admin = AdminUserFactory(email="r4j-bounty-admin@example.com")
    admin.role = UserRole.ADMIN
    admin.save(update_fields=["role"])
    return admin


@pytest.fixture
def admin_client(admin_user) -> APIClient:
    """Client احراز هویت‌شده برای ادمین."""
    client = APIClient()
    refresh = RefreshToken.for_user(admin_user)
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {refresh.access_token!s}")
    return client


@pytest.fixture
def regular_user(db):
    """کاربر عادی (non-admin)."""
    return UserFactory(email="regular-bounty@example.com")


@pytest.fixture
def regular_client(regular_user) -> APIClient:
    """Client احراز هویت‌شده برای کاربر عادی."""
    client = APIClient()
    refresh = RefreshToken.for_user(regular_user)
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {refresh.access_token!s}")
    return client


# ============================================================
# Permission Boundaries
# ============================================================


class TestAdminBountyPermissions:
    """فقط admin به endpoints ادمین bounty دسترسی دارد."""

    def test_anonymous_cannot_list(
        self,
        api_client: APIClient,
    ) -> None:
        """کاربر لاگین نکرده نباید به لیست bountyها دسترسی داشته باشد."""
        response = api_client.get("/api/v1/r4j/admin/bounties/")
        assert response.status_code in {
            status.HTTP_401_UNAUTHORIZED,
            status.HTTP_403_FORBIDDEN,
        }

    def test_regular_user_cannot_list(
        self,
        regular_client: APIClient,
    ) -> None:
        """کاربر عادی نباید به لیست ادمین دسترسی داشته باشد."""
        response = regular_client.get("/api/v1/r4j/admin/bounties/")
        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_regular_user_cannot_retrieve(
        self,
        regular_client: APIClient,
        db,
    ) -> None:
        """کاربر عادی نباید بتواند جزئیات bounty را از مسیر ادمین ببیند."""
        criminal = R4JCriminalPublishedFactory()
        user = UserFactory(email="bounty-owner@example.com")
        bounty = R4JBountyFactory(criminal=criminal, user=user)

        response = regular_client.get(f"/api/v1/r4j/admin/bounties/{bounty.pk}/")
        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_regular_user_cannot_approve_cancel(
        self,
        regular_client: APIClient,
        db,
    ) -> None:
        """کاربر عادی نباید بتواند cancel را تأیید کند."""
        criminal = R4JCriminalPublishedFactory()
        user = UserFactory(email="bounty-owner2@example.com")
        bounty = R4JBountyFactory(
            criminal=criminal,
            user=user,
            status=BountyStatus.CANCEL_REQUESTED,
        )
        response = regular_client.post(
            f"/api/v1/r4j/admin/bounties/{bounty.pk}/cancel/approve/",
            data={},
            format="json",
        )
        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_regular_user_cannot_reject_cancel(
        self,
        regular_client: APIClient,
        db,
    ) -> None:
        """کاربر عادی نباید بتواند cancel را رد کند."""
        criminal = R4JCriminalPublishedFactory()
        user = UserFactory(email="bounty-owner3@example.com")
        bounty = R4JBountyFactory(
            criminal=criminal,
            user=user,
            status=BountyStatus.CANCEL_REQUESTED,
        )
        response = regular_client.post(
            f"/api/v1/r4j/admin/bounties/{bounty.pk}/cancel/reject/",
            data={},
            format="json",
        )
        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_anonymous_cannot_approve_cancel(
        self,
        api_client: APIClient,
        db,
    ) -> None:
        """کاربر لاگین نکرده نباید بتواند cancel approve کند."""
        response = api_client.post(
            "/api/v1/r4j/admin/bounties/1/cancel/approve/",
            data={},
            format="json",
        )
        assert response.status_code in {
            status.HTTP_401_UNAUTHORIZED,
            status.HTTP_403_FORBIDDEN,
        }


# ============================================================
# List Bounties
# ============================================================


class TestAdminBountyList:
    """لیست bountyها برای admin — شامل تمام کاربران."""

    def test_admin_sees_all_bounties(
        self,
        admin_client: APIClient,
        db,
    ) -> None:
        """ادمین باید bountyهای تمام کاربران را ببیند."""
        criminal = R4JCriminalPublishedFactory()
        user_a = UserFactory(email="ua-bounty@example.com")
        user_b = UserFactory(email="ub-bounty@example.com")
        R4JBountyFactory(criminal=criminal, user=user_a)
        R4JBountyFactory(criminal=criminal, user=user_b)

        response = admin_client.get("/api/v1/r4j/admin/bounties/")

        assert response.status_code == status.HTTP_200_OK
        assert response.data["data"]["count"] >= 2

    def test_filter_by_status_active(
        self,
        admin_client: APIClient,
        db,
    ) -> None:
        """فیلتر status=active فقط bountyهای active را برگرداند."""
        criminal = R4JCriminalPublishedFactory()
        user = UserFactory(email="filter-bounty@example.com")
        R4JBountyFactory(criminal=criminal, user=user, status=BountyStatus.ACTIVE)
        R4JBountyFactory(criminal=criminal, user=user, status=BountyStatus.CANCELED)

        response = admin_client.get("/api/v1/r4j/admin/bounties/?status=active")

        assert response.status_code == status.HTTP_200_OK
        results = response.data["data"]["results"]
        assert all(r["status"] == BountyStatus.ACTIVE for r in results)

    def test_filter_by_criminal_id(
        self,
        admin_client: APIClient,
        db,
    ) -> None:
        """فیلتر criminal_id فقط bountyهای آن مجرم را برگرداند."""
        criminal_a = R4JCriminalPublishedFactory()
        criminal_b = R4JCriminalPublishedFactory()
        user = UserFactory(email="filter2-bounty@example.com")
        R4JBountyFactory(criminal=criminal_a, user=user)
        R4JBountyFactory(criminal=criminal_b, user=user)

        response = admin_client.get(
            f"/api/v1/r4j/admin/bounties/?criminal_id={criminal_a.pk}",
        )

        assert response.status_code == status.HTTP_200_OK
        results = response.data["data"]["results"]
        assert len(results) == 1
        assert results[0]["criminal_id"] == criminal_a.pk

    def test_filter_by_user_id(
        self,
        admin_client: APIClient,
        db,
    ) -> None:
        """فیلتر user_id فقط bountyهای آن کاربر را برگرداند."""
        criminal = R4JCriminalPublishedFactory()
        user_a = UserFactory(email="ua2-bounty@example.com")
        user_b = UserFactory(email="ub2-bounty@example.com")
        R4JBountyFactory(criminal=criminal, user=user_a)
        R4JBountyFactory(criminal=criminal, user=user_b)

        response = admin_client.get(
            f"/api/v1/r4j/admin/bounties/?user_id={user_a.pk}",
        )

        assert response.status_code == status.HTTP_200_OK
        results = response.data["data"]["results"]
        assert all(r["user_id"] == user_a.pk for r in results)

    def test_filter_by_cancel_requested_status(
        self,
        admin_client: APIClient,
        db,
    ) -> None:
        """فیلتر status=cancel_requested فقط bountyهای در حال بررسی را برگرداند."""
        criminal = R4JCriminalPublishedFactory()
        user = UserFactory(email="cancel-req-bounty@example.com")
        R4JBountyFactory(
            criminal=criminal,
            user=user,
            status=BountyStatus.CANCEL_REQUESTED,
        )
        R4JBountyFactory(criminal=criminal, user=user, status=BountyStatus.ACTIVE)

        response = admin_client.get(
            "/api/v1/r4j/admin/bounties/?status=cancel_requested",
        )

        assert response.status_code == status.HTTP_200_OK
        results = response.data["data"]["results"]
        assert all(r["status"] == BountyStatus.CANCEL_REQUESTED for r in results)


# ============================================================
# Retrieve Bounty
# ============================================================


class TestAdminBountyRetrieve:
    """جزئیات bounty برای admin."""

    def test_retrieve_existing_bounty(
        self,
        admin_client: APIClient,
        db,
    ) -> None:
        """ادمین باید بتواند جزئیات کامل bounty را دریافت کند."""
        criminal = R4JCriminalPublishedFactory()
        user = UserFactory(email="retrieve-bounty@example.com")
        bounty = R4JBountyFactory(criminal=criminal, user=user)

        response = admin_client.get(f"/api/v1/r4j/admin/bounties/{bounty.pk}/")

        assert response.status_code == status.HTTP_200_OK
        assert response.data["data"]["id"] == bounty.pk

    def test_retrieve_nonexistent_returns_404(
        self,
        admin_client: APIClient,
    ) -> None:
        """شناسه نامعتبر bounty باید 404 برگرداند."""
        response = admin_client.get("/api/v1/r4j/admin/bounties/99999/")
        assert response.status_code == status.HTTP_404_NOT_FOUND

    def test_retrieve_includes_user_email(
        self,
        admin_client: APIClient,
        db,
    ) -> None:
        """جزئیات باید ایمیل کاربر تعیین‌کننده جایزه را شامل شود."""
        criminal = R4JCriminalPublishedFactory()
        user = UserFactory(email="owner-email@example.com")
        bounty = R4JBountyFactory(criminal=criminal, user=user)

        response = admin_client.get(f"/api/v1/r4j/admin/bounties/{bounty.pk}/")

        assert response.status_code == status.HTTP_200_OK
        assert response.data["data"]["user_email"] == "owner-email@example.com"

    def test_retrieve_includes_criminal_name(
        self,
        admin_client: APIClient,
        db,
    ) -> None:
        """جزئیات باید نام مجرم را شامل شود."""
        criminal = R4JCriminalPublishedFactory(
            first_name="Joe",
            last_name="Biden",
        )
        user = UserFactory(email="criminal-name@example.com")
        bounty = R4JBountyFactory(criminal=criminal, user=user)

        response = admin_client.get(f"/api/v1/r4j/admin/bounties/{bounty.pk}/")

        assert response.status_code == status.HTTP_200_OK
        assert "Joe" in response.data["data"]["criminal_name"]
        assert "Biden" in response.data["data"]["criminal_name"]

    def test_retrieve_includes_admin_note(
        self,
        admin_client: APIClient,
        db,
    ) -> None:
        """جزئیات باید admin_note را شامل شود."""
        criminal = R4JCriminalPublishedFactory()
        user = UserFactory(email="admin-note@example.com")
        bounty = R4JBountyFactory(
            criminal=criminal,
            user=user,
            admin_note="یادداشت ادمین برای این جایزه",
        )

        response = admin_client.get(f"/api/v1/r4j/admin/bounties/{bounty.pk}/")

        assert response.status_code == status.HTTP_200_OK
        assert response.data["data"]["admin_note"] == "یادداشت ادمین برای این جایزه"


# ============================================================
# Cancel Approve
# ============================================================


class TestAdminBountyCancelApprove:
    """تأیید درخواست لغو bounty توسط ادمین."""

    def test_approve_cancel_sets_status_canceled(
        self,
        admin_client: APIClient,
        admin_user,
        db,
    ) -> None:
        """تأیید cancel باید status را CANCELED کند."""
        criminal = R4JCriminalPublishedFactory()
        user = UserFactory(email="approve-cancel@example.com")
        bounty = R4JBountyFactory(
            criminal=criminal,
            user=user,
            status=BountyStatus.CANCEL_REQUESTED,
            amount_toman=200_000,
        )

        with patch(_TASK_PATCH_PATH) as mock_task:
            mock_task.delay = MagicMock()
            response = admin_client.post(
                f"/api/v1/r4j/admin/bounties/{bounty.pk}/cancel/approve/",
                data={"admin_note": "درخواست معتبر است."},
                format="json",
            )

        assert response.status_code == status.HTTP_200_OK
        assert response.data["data"]["status"] == BountyStatus.CANCELED

        bounty.refresh_from_db()
        assert bounty.status == BountyStatus.CANCELED
        assert bounty.canceled_at is not None
        assert bounty.admin_note == "درخواست معتبر است."

    def test_approve_cancel_syncs_counters(
        self,
        admin_client: APIClient,
        db,
    ) -> None:
        """بعد از تأیید cancel، counterهای criminal باید sync شوند."""
        criminal = R4JCriminalPublishedFactory(
            total_bounty_toman=0,
            bounties_count=0,
        )
        user = UserFactory(email="approve-sync@example.com")
        bounty = R4JBountyFactory(
            criminal=criminal,
            user=user,
            status=BountyStatus.CANCEL_REQUESTED,
            amount_toman=300_000,
        )

        with patch(_TASK_PATCH_PATH):
            admin_client.post(
                f"/api/v1/r4j/admin/bounties/{bounty.pk}/cancel/approve/",
                data={},
                format="json",
            )

        criminal.refresh_from_db()
        assert criminal.total_bounty_toman == 0
        assert criminal.bounties_count == 0

    def test_approve_cancel_with_multiple_bounties_syncs_correctly(
        self,
        admin_client: APIClient,
        db,
    ) -> None:
        """لغو یک bounty نباید counter bountyهای دیگر را خراب کند."""
        criminal = R4JCriminalPublishedFactory(
            total_bounty_toman=0,
            bounties_count=0,
        )
        user_a = UserFactory(email="multi-a@example.com")
        user_b = UserFactory(email="multi-b@example.com")

        bounty_a = R4JBountyFactory(
            criminal=criminal,
            user=user_a,
            status=BountyStatus.CANCEL_REQUESTED,
            amount_toman=100_000,
        )
        R4JBountyFactory(
            criminal=criminal,
            user=user_b,
            status=BountyStatus.ACTIVE,
            amount_toman=200_000,
        )

        with patch(_TASK_PATCH_PATH):
            admin_client.post(
                f"/api/v1/r4j/admin/bounties/{bounty_a.pk}/cancel/approve/",
                data={},
                format="json",
            )

        criminal.refresh_from_db()
        assert criminal.bounties_count == 1
        assert criminal.total_bounty_toman == 200_000

    def test_approve_cancel_dispatches_audit(
        self,
        admin_client: APIClient,
        admin_user,
        db,
    ) -> None:
        """تأیید cancel باید audit log مناسب dispatch کند."""
        criminal = R4JCriminalPublishedFactory()
        user = UserFactory(email="audit-approve@example.com")
        bounty = R4JBountyFactory(
            criminal=criminal,
            user=user,
            status=BountyStatus.CANCEL_REQUESTED,
        )

        with patch(_TASK_PATCH_PATH) as mock_task:
            mock_task.delay = MagicMock()
            admin_client.post(
                f"/api/v1/r4j/admin/bounties/{bounty.pk}/cancel/approve/",
                data={},
                format="json",
            )

        mock_task.delay.assert_called_once()
        kwargs = mock_task.delay.call_args.kwargs
        assert kwargs["action"] == audit_actions.R4J_BOUNTY_CANCEL_APPROVED
        assert kwargs["user_id"] == admin_user.pk

    def test_cannot_approve_cancel_for_active_bounty(
        self,
        admin_client: APIClient,
        db,
    ) -> None:
        """bounty ACTIVE نباید از مسیر cancel/approve قابل تغییر باشد."""
        criminal = R4JCriminalPublishedFactory()
        user = UserFactory(email="active-approve@example.com")
        bounty = R4JBountyFactory(
            criminal=criminal,
            user=user,
            status=BountyStatus.ACTIVE,
        )

        response = admin_client.post(
            f"/api/v1/r4j/admin/bounties/{bounty.pk}/cancel/approve/",
            data={},
            format="json",
        )
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_cannot_approve_cancel_for_already_canceled_bounty(
        self,
        admin_client: APIClient,
        db,
    ) -> None:
        """bounty CANCELED نباید از مسیر cancel/approve قابل تغییر باشد."""
        criminal = R4JCriminalPublishedFactory()
        user = UserFactory(email="canceled-approve@example.com")
        bounty = R4JBountyFactory(
            criminal=criminal,
            user=user,
            status=BountyStatus.CANCELED,
        )

        response = admin_client.post(
            f"/api/v1/r4j/admin/bounties/{bounty.pk}/cancel/approve/",
            data={},
            format="json",
        )
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_approve_cancel_nonexistent_bounty_returns_404(
        self,
        admin_client: APIClient,
    ) -> None:
        """bounty با id نامعتبر باید 404 برگرداند."""
        response = admin_client.post(
            "/api/v1/r4j/admin/bounties/99999/cancel/approve/",
            data={},
            format="json",
        )
        assert response.status_code == status.HTTP_404_NOT_FOUND


# ============================================================
# Cancel Reject
# ============================================================


class TestAdminBountyCancelReject:
    """رد درخواست لغو bounty توسط ادمین."""

    def test_reject_cancel_sets_status_back_to_active(
        self,
        admin_client: APIClient,
        db,
    ) -> None:
        """رد cancel باید status را به ACTIVE برگرداند."""
        criminal = R4JCriminalPublishedFactory()
        user = UserFactory(email="reject-cancel@example.com")
        bounty = R4JBountyFactory(
            criminal=criminal,
            user=user,
            status=BountyStatus.CANCEL_REQUESTED,
            amount_toman=150_000,
        )

        with patch(_TASK_PATCH_PATH) as mock_task:
            mock_task.delay = MagicMock()
            response = admin_client.post(
                f"/api/v1/r4j/admin/bounties/{bounty.pk}/cancel/reject/",
                data={"admin_note": "درخواست معتبر نیست."},
                format="json",
            )

        assert response.status_code == status.HTTP_200_OK
        assert response.data["data"]["status"] == BountyStatus.ACTIVE

        bounty.refresh_from_db()
        assert bounty.status == BountyStatus.ACTIVE
        assert bounty.cancel_requested_at is None
        assert bounty.admin_note == "درخواست معتبر نیست."

    def test_reject_cancel_clears_cancel_requested_at(
        self,
        admin_client: APIClient,
        db,
    ) -> None:
        """بعد از رد cancel، cancel_requested_at باید null شود."""
        from django.utils import timezone as tz

        criminal = R4JCriminalPublishedFactory()
        user = UserFactory(email="clear-timestamp@example.com")
        bounty = R4JBountyFactory(
            criminal=criminal,
            user=user,
            status=BountyStatus.CANCEL_REQUESTED,
            cancel_requested_at=tz.now(),
        )

        with patch(_TASK_PATCH_PATH):
            admin_client.post(
                f"/api/v1/r4j/admin/bounties/{bounty.pk}/cancel/reject/",
                data={},
                format="json",
            )

        bounty.refresh_from_db()
        assert bounty.cancel_requested_at is None

    def test_reject_cancel_syncs_counters(
        self,
        admin_client: APIClient,
        db,
    ) -> None:
        """بعد از رد cancel، counter criminal باید re-sync شود."""
        criminal = R4JCriminalPublishedFactory(
            total_bounty_toman=0,
            bounties_count=0,
        )
        user = UserFactory(email="reject-sync@example.com")
        bounty = R4JBountyFactory(
            criminal=criminal,
            user=user,
            status=BountyStatus.CANCEL_REQUESTED,
            amount_toman=250_000,
        )

        with patch(_TASK_PATCH_PATH):
            admin_client.post(
                f"/api/v1/r4j/admin/bounties/{bounty.pk}/cancel/reject/",
                data={},
                format="json",
            )

        criminal.refresh_from_db()
        assert criminal.bounties_count == 1
        assert criminal.total_bounty_toman == 250_000

    def test_reject_cancel_dispatches_audit(
        self,
        admin_client: APIClient,
        admin_user,
        db,
    ) -> None:
        """رد cancel باید audit log مناسب dispatch کند."""
        criminal = R4JCriminalPublishedFactory()
        user = UserFactory(email="audit-reject@example.com")
        bounty = R4JBountyFactory(
            criminal=criminal,
            user=user,
            status=BountyStatus.CANCEL_REQUESTED,
        )

        with patch(_TASK_PATCH_PATH) as mock_task:
            mock_task.delay = MagicMock()
            admin_client.post(
                f"/api/v1/r4j/admin/bounties/{bounty.pk}/cancel/reject/",
                data={},
                format="json",
            )

        mock_task.delay.assert_called_once()
        kwargs = mock_task.delay.call_args.kwargs
        assert kwargs["action"] == audit_actions.R4J_BOUNTY_CANCEL_REJECTED
        assert kwargs["user_id"] == admin_user.pk

    def test_cannot_reject_cancel_for_active_bounty(
        self,
        admin_client: APIClient,
        db,
    ) -> None:
        """bounty ACTIVE نباید از مسیر cancel/reject قابل تغییر باشد."""
        criminal = R4JCriminalPublishedFactory()
        user = UserFactory(email="active-reject@example.com")
        bounty = R4JBountyFactory(
            criminal=criminal,
            user=user,
            status=BountyStatus.ACTIVE,
        )

        response = admin_client.post(
            f"/api/v1/r4j/admin/bounties/{bounty.pk}/cancel/reject/",
            data={},
            format="json",
        )
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_cannot_reject_cancel_for_canceled_bounty(
        self,
        admin_client: APIClient,
        db,
    ) -> None:
        """bounty CANCELED نباید از مسیر cancel/reject قابل تغییر باشد."""
        criminal = R4JCriminalPublishedFactory()
        user = UserFactory(email="canceled-reject@example.com")
        bounty = R4JBountyFactory(
            criminal=criminal,
            user=user,
            status=BountyStatus.CANCELED,
        )

        response = admin_client.post(
            f"/api/v1/r4j/admin/bounties/{bounty.pk}/cancel/reject/",
            data={},
            format="json",
        )
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_reject_cancel_nonexistent_bounty_returns_404(
        self,
        admin_client: APIClient,
    ) -> None:
        """bounty با id نامعتبر باید 404 برگرداند."""
        response = admin_client.post(
            "/api/v1/r4j/admin/bounties/99999/cancel/reject/",
            data={},
            format="json",
        )
        assert response.status_code == status.HTTP_404_NOT_FOUND

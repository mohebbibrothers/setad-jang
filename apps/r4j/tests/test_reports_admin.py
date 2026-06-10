"""
Tests — apps.r4j admin report endpoints (Phase R4J.3)

این تست‌ها رفتار admin report endpoints را verify می‌کنند:

- permission boundaries (anonymous / regular user / admin)
- list + filter reports
- retrieve report detail
- review: approve all / partial / reject all
- review: apply changes to criminal (type-safe)
- review: گزارش CANCEL_REQUESTED نباید از این مسیر قابل review باشد
- cancel approve / reject (state machine exhaustive)
- audit dispatch برای همه eventهای مهم

اصول طراحی:
- apply changes روی criminal به‌صورت دقیق با مقادیر واقعی تست می‌شود.
- state machine از تمام جهت‌ها cover می‌شود.
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
from apps.r4j.choices import ReportFieldChangeStatus, ReportStatus
from tests.factories.auth import AdminUserFactory, UserFactory
from tests.factories.r4j import (
    R4JCriminalFactory,
    R4JReportFactory,
    R4JReportFieldChangeFactory,
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
    admin = AdminUserFactory(email="r4j-admin-report@example.com")
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
    return UserFactory(email="user-for-report@example.com")


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


class TestAdminReportPermissions:
    """فقط admin به endpoints ادمین دسترسی دارد."""

    def test_anonymous_cannot_list(
        self,
        api_client: APIClient,
    ) -> None:
        """کاربر لاگین نکرده نباید به لیست دسترسی داشته باشد."""
        response = api_client.get("/api/v1/r4j/admin/reports/")
        assert response.status_code in {
            status.HTTP_401_UNAUTHORIZED,
            status.HTTP_403_FORBIDDEN,
        }

    def test_regular_user_cannot_list(
        self,
        regular_client: APIClient,
    ) -> None:
        """کاربر عادی نباید به لیست ادمین دسترسی داشته باشد."""
        response = regular_client.get("/api/v1/r4j/admin/reports/")
        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_regular_user_cannot_retrieve(
        self,
        regular_client: APIClient,
        db,
    ) -> None:
        """کاربر عادی نباید بتواند جزئیات گزارش را از مسیر ادمین ببیند."""
        report = R4JReportFactory()
        response = regular_client.get(f"/api/v1/r4j/admin/reports/{report.pk}/")
        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_regular_user_cannot_review(
        self,
        regular_client: APIClient,
        db,
    ) -> None:
        """کاربر عادی نباید بتواند گزارش را review کند."""
        report = R4JReportFactory()
        response = regular_client.post(
            f"/api/v1/r4j/admin/reports/{report.pk}/review/",
            data={},
            format="json",
        )
        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_regular_user_cannot_approve_cancel(
        self,
        regular_client: APIClient,
        db,
    ) -> None:
        """کاربر عادی نباید بتواند cancel را تأیید کند."""
        report = R4JReportFactory(status=ReportStatus.CANCEL_REQUESTED)
        response = regular_client.post(
            f"/api/v1/r4j/admin/reports/{report.pk}/cancel/approve/",
            data={},
            format="json",
        )
        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_anonymous_cannot_review(
        self,
        api_client: APIClient,
        db,
    ) -> None:
        """کاربر لاگین نکرده نباید بتواند review کند."""
        report = R4JReportFactory()
        response = api_client.post(
            f"/api/v1/r4j/admin/reports/{report.pk}/review/",
            data={},
            format="json",
        )
        assert response.status_code in {
            status.HTTP_401_UNAUTHORIZED,
            status.HTTP_403_FORBIDDEN,
        }


# ============================================================
# List Reports
# ============================================================


class TestAdminReportList:
    """لیست گزارشات برای admin — شامل تمام کاربران."""

    def test_admin_sees_all_reports(
        self,
        admin_client: APIClient,
        db,
    ) -> None:
        """ادمین باید گزارشات تمام کاربران را ببیند."""
        criminal = R4JCriminalFactory()
        user1 = UserFactory(email="u1@example.com")
        user2 = UserFactory(email="u2@example.com")
        R4JReportFactory(criminal=criminal, submitted_by=user1)
        R4JReportFactory(criminal=criminal, submitted_by=user2)

        response = admin_client.get("/api/v1/r4j/admin/reports/")

        assert response.status_code == status.HTTP_200_OK
        assert response.data["data"]["count"] >= 2

    def test_filter_by_status_pending(
        self,
        admin_client: APIClient,
        db,
    ) -> None:
        """فیلتر status=pending فقط گزارشات pending را برگرداند."""
        criminal = R4JCriminalFactory()
        user = UserFactory(email="u3@example.com")
        R4JReportFactory(
            criminal=criminal,
            submitted_by=user,
            status=ReportStatus.PENDING,
        )
        R4JReportFactory(
            criminal=criminal,
            submitted_by=user,
            status=ReportStatus.APPROVED,
        )

        response = admin_client.get("/api/v1/r4j/admin/reports/?status=pending")

        assert response.status_code == status.HTTP_200_OK
        results = response.data["data"]["results"]
        assert all(r["status"] == ReportStatus.PENDING for r in results)

    def test_filter_by_criminal_id(
        self,
        admin_client: APIClient,
        db,
    ) -> None:
        """فیلتر criminal_id فقط گزارشات آن مجرم را برگرداند."""
        criminal_a = R4JCriminalFactory()
        criminal_b = R4JCriminalFactory()
        user = UserFactory(email="u4@example.com")
        R4JReportFactory(criminal=criminal_a, submitted_by=user)
        R4JReportFactory(criminal=criminal_b, submitted_by=user)

        response = admin_client.get(
            f"/api/v1/r4j/admin/reports/?criminal_id={criminal_a.pk}",
        )

        assert response.status_code == status.HTTP_200_OK
        results = response.data["data"]["results"]
        assert len(results) == 1
        assert results[0]["criminal_id"] == criminal_a.pk

    def test_filter_by_submitted_by_id(
        self,
        admin_client: APIClient,
        db,
    ) -> None:
        """فیلتر submitted_by_id فقط گزارشات آن کاربر را برگرداند."""
        criminal = R4JCriminalFactory()
        user_a = UserFactory(email="ua@example.com")
        user_b = UserFactory(email="ub@example.com")
        R4JReportFactory(criminal=criminal, submitted_by=user_a)
        R4JReportFactory(criminal=criminal, submitted_by=user_b)

        response = admin_client.get(
            f"/api/v1/r4j/admin/reports/?submitted_by_id={user_a.pk}",
        )

        assert response.status_code == status.HTTP_200_OK
        results = response.data["data"]["results"]
        assert all(r["submitted_by_id"] == user_a.pk for r in results)


# ============================================================
# Retrieve Report
# ============================================================


class TestAdminReportRetrieve:
    """جزئیات گزارش برای admin."""

    def test_retrieve_existing_report(
        self,
        admin_client: APIClient,
        db,
    ) -> None:
        """ادمین باید بتواند جزئیات کامل گزارش را دریافت کند."""
        report = R4JReportFactory()
        response = admin_client.get(f"/api/v1/r4j/admin/reports/{report.pk}/")

        assert response.status_code == status.HTTP_200_OK
        assert response.data["data"]["id"] == report.pk

    def test_retrieve_nonexistent_returns_404(
        self,
        admin_client: APIClient,
    ) -> None:
        """شناسه نامعتبر گزارش باید 404 برگرداند."""
        response = admin_client.get("/api/v1/r4j/admin/reports/99999/")
        assert response.status_code == status.HTTP_404_NOT_FOUND

    def test_retrieve_includes_field_changes(
        self,
        admin_client: APIClient,
        db,
    ) -> None:
        """جزئیات گزارش باید field_changes را شامل شود."""
        report = R4JReportFactory()
        R4JReportFieldChangeFactory(report=report, field_name="country")
        R4JReportFieldChangeFactory(report=report, field_name="city")

        response = admin_client.get(f"/api/v1/r4j/admin/reports/{report.pk}/")

        assert response.status_code == status.HTTP_200_OK
        assert len(response.data["data"]["field_changes"]) == 2

    def test_retrieve_includes_submitted_by_email(
        self,
        admin_client: APIClient,
        db,
    ) -> None:
        """جزئیات باید ایمیل گزارش‌دهنده را شامل شود."""
        user = UserFactory(email="reporter2@example.com")
        report = R4JReportFactory(submitted_by=user)

        response = admin_client.get(f"/api/v1/r4j/admin/reports/{report.pk}/")

        assert response.status_code == status.HTTP_200_OK
        assert response.data["data"]["submitted_by_email"] == "reporter2@example.com"


# ============================================================
# Review — Approve All
# ============================================================


class TestAdminReportReviewApproveAll:
    """review با تأیید تمام field_changeها."""

    def test_approve_all_sets_status_approved(
        self,
        admin_client: APIClient,
        admin_user,
        db,
    ) -> None:
        """تأیید همه field_changeها باید status گزارش را APPROVED کند."""
        criminal = R4JCriminalFactory(city="Tehran")
        report = R4JReportFactory(
            criminal=criminal,
            status=ReportStatus.PENDING,
        )
        fc = R4JReportFieldChangeFactory(
            report=report,
            field_name="city",
            suggested_value="Mashhad",
            status=ReportFieldChangeStatus.PENDING,
        )

        with patch(_TASK_PATCH_PATH) as mock_task:
            mock_task.delay = MagicMock()
            response = admin_client.post(
                f"/api/v1/r4j/admin/reports/{report.pk}/review/",
                data={
                    "field_decisions": [
                        {
                            "field_change_id": fc.pk,
                            "status": ReportFieldChangeStatus.APPROVED,
                            "admin_note": "",
                        },
                    ],
                    "admin_note": "تأیید شد.",
                },
                format="json",
            )

        assert response.status_code == status.HTTP_200_OK
        assert response.data["data"]["status"] == ReportStatus.APPROVED

        report.refresh_from_db()
        assert report.status == ReportStatus.APPROVED
        assert report.reviewed_by_id == admin_user.pk

    def test_approve_all_applies_changes_to_criminal(
        self,
        admin_client: APIClient,
        db,
    ) -> None:
        """بعد از تأیید، مقدار پیشنهادی باید روی criminal اعمال شود."""
        criminal = R4JCriminalFactory(city="Tehran", country="Iran")
        report = R4JReportFactory(
            criminal=criminal,
            status=ReportStatus.PENDING,
        )
        fc1 = R4JReportFieldChangeFactory(
            report=report,
            field_name="city",
            suggested_value="Mashhad",
        )
        fc2 = R4JReportFieldChangeFactory(
            report=report,
            field_name="country",
            suggested_value="USA",
        )

        with patch(_TASK_PATCH_PATH):
            admin_client.post(
                f"/api/v1/r4j/admin/reports/{report.pk}/review/",
                data={
                    "field_decisions": [
                        {
                            "field_change_id": fc1.pk,
                            "status": ReportFieldChangeStatus.APPROVED,
                        },
                        {
                            "field_change_id": fc2.pk,
                            "status": ReportFieldChangeStatus.APPROVED,
                        },
                    ],
                },
                format="json",
            )

        criminal.refresh_from_db()
        assert criminal.city == "Mashhad"
        assert criminal.country == "USA"

    def test_approve_applies_birth_date_correctly(
        self,
        admin_client: APIClient,
        db,
    ) -> None:
        """field_applicator باید birth_date را از string به date تبدیل کند."""
        criminal = R4JCriminalFactory(birth_date=None)
        report = R4JReportFactory(criminal=criminal, status=ReportStatus.PENDING)
        fc = R4JReportFieldChangeFactory(
            report=report,
            field_name="birth_date",
            suggested_value="1985-06-15",
        )

        with patch(_TASK_PATCH_PATH):
            response = admin_client.post(
                f"/api/v1/r4j/admin/reports/{report.pk}/review/",
                data={
                    "field_decisions": [
                        {
                            "field_change_id": fc.pk,
                            "status": ReportFieldChangeStatus.APPROVED,
                        },
                    ],
                },
                format="json",
            )

        assert response.status_code == status.HTTP_200_OK
        criminal.refresh_from_db()
        assert criminal.birth_date is not None
        assert str(criminal.birth_date) == "1985-06-15"

    def test_approve_applies_gender_correctly(
        self,
        admin_client: APIClient,
        db,
    ) -> None:
        """field_applicator باید gender را validate و اعمال کند."""
        from apps.r4j.choices import Gender

        criminal = R4JCriminalFactory(gender=Gender.UNKNOWN)
        report = R4JReportFactory(criminal=criminal, status=ReportStatus.PENDING)
        fc = R4JReportFieldChangeFactory(
            report=report,
            field_name="gender",
            suggested_value="male",
        )

        with patch(_TASK_PATCH_PATH):
            admin_client.post(
                f"/api/v1/r4j/admin/reports/{report.pk}/review/",
                data={
                    "field_decisions": [
                        {
                            "field_change_id": fc.pk,
                            "status": ReportFieldChangeStatus.APPROVED,
                        },
                    ],
                },
                format="json",
            )

        criminal.refresh_from_db()
        assert criminal.gender == Gender.MALE

    def test_invalid_birth_date_auto_rejects_field_change(
        self,
        admin_client: APIClient,
        db,
    ) -> None:
        """birth_date نامعتبر باید field_change را auto-reject کند و report را خراب نکند."""
        criminal = R4JCriminalFactory(birth_date=None)
        report = R4JReportFactory(criminal=criminal, status=ReportStatus.PENDING)
        fc = R4JReportFieldChangeFactory(
            report=report,
            field_name="birth_date",
            suggested_value="not-a-date",
        )

        with patch(_TASK_PATCH_PATH):
            response = admin_client.post(
                f"/api/v1/r4j/admin/reports/{report.pk}/review/",
                data={
                    "field_decisions": [
                        {
                            "field_change_id": fc.pk,
                            "status": ReportFieldChangeStatus.APPROVED,
                        },
                    ],
                },
                format="json",
            )

        # endpoint باید 200 برگرداند (نه 500)
        assert response.status_code == status.HTTP_200_OK

        # field_change باید auto-rejected شده باشد
        fc.refresh_from_db()
        assert fc.status == ReportFieldChangeStatus.REJECTED

        # criminal تغییری نکرده
        criminal.refresh_from_db()
        assert criminal.birth_date is None

    def test_approve_all_dispatches_audit(
        self,
        admin_client: APIClient,
        admin_user,
        db,
    ) -> None:
        """review موفق باید audit log مناسب dispatch کند."""
        report = R4JReportFactory(status=ReportStatus.PENDING)

        with patch(_TASK_PATCH_PATH) as mock_task:
            mock_task.delay = MagicMock()
            admin_client.post(
                f"/api/v1/r4j/admin/reports/{report.pk}/review/",
                data={"field_decisions": [], "admin_note": "بررسی شد."},
                format="json",
            )

        mock_task.delay.assert_called_once()
        kwargs = mock_task.delay.call_args.kwargs
        assert kwargs["action"] == audit_actions.R4J_REPORT_REVIEWED
        assert kwargs["user_id"] == admin_user.pk


# ============================================================
# Review — Partial Approve
# ============================================================


class TestAdminReportReviewPartialApprove:
    """review با تأیید برخی field_changeها."""

    def test_partial_approve_sets_status_partially_approved(
        self,
        admin_client: APIClient,
        db,
    ) -> None:
        """تأیید برخی field_changeها باید status را PARTIALLY_APPROVED کند."""
        criminal = R4JCriminalFactory()
        report = R4JReportFactory(criminal=criminal, status=ReportStatus.PENDING)
        fc1 = R4JReportFieldChangeFactory(
            report=report,
            field_name="city",
            suggested_value="Mashhad",
        )
        fc2 = R4JReportFieldChangeFactory(
            report=report,
            field_name="country",
            suggested_value="USA",
        )

        with patch(_TASK_PATCH_PATH):
            response = admin_client.post(
                f"/api/v1/r4j/admin/reports/{report.pk}/review/",
                data={
                    "field_decisions": [
                        {
                            "field_change_id": fc1.pk,
                            "status": ReportFieldChangeStatus.APPROVED,
                        },
                        {
                            "field_change_id": fc2.pk,
                            "status": ReportFieldChangeStatus.REJECTED,
                        },
                    ],
                },
                format="json",
            )

        assert response.status_code == status.HTTP_200_OK
        assert response.data["data"]["status"] == ReportStatus.PARTIALLY_APPROVED

    def test_partial_approve_only_applies_approved_fields(
        self,
        admin_client: APIClient,
        db,
    ) -> None:
        """فقط field_changeهای approved باید روی criminal اعمال شوند."""
        criminal = R4JCriminalFactory(city="Tehran", country="Iran")
        report = R4JReportFactory(criminal=criminal, status=ReportStatus.PENDING)
        fc1 = R4JReportFieldChangeFactory(
            report=report,
            field_name="city",
            suggested_value="Mashhad",
        )
        fc2 = R4JReportFieldChangeFactory(
            report=report,
            field_name="country",
            suggested_value="USA",
        )

        with patch(_TASK_PATCH_PATH):
            admin_client.post(
                f"/api/v1/r4j/admin/reports/{report.pk}/review/",
                data={
                    "field_decisions": [
                        {
                            "field_change_id": fc1.pk,
                            "status": ReportFieldChangeStatus.APPROVED,
                        },
                        {
                            "field_change_id": fc2.pk,
                            "status": ReportFieldChangeStatus.REJECTED,
                        },
                    ],
                },
                format="json",
            )

        criminal.refresh_from_db()
        # فقط city اعمال شده
        assert criminal.city == "Mashhad"
        # country تغییر نکرده
        assert criminal.country == "Iran"


# ============================================================
# Review — Reject All
# ============================================================


class TestAdminReportReviewRejectAll:
    """review با رد همه field_changeها."""

    def test_reject_all_sets_status_rejected(
        self,
        admin_client: APIClient,
        db,
    ) -> None:
        """رد همه field_changeها باید status را REJECTED کند."""
        criminal = R4JCriminalFactory(city="Tehran")
        report = R4JReportFactory(criminal=criminal, status=ReportStatus.PENDING)
        fc = R4JReportFieldChangeFactory(
            report=report,
            field_name="city",
            suggested_value="Mashhad",
        )

        with patch(_TASK_PATCH_PATH):
            response = admin_client.post(
                f"/api/v1/r4j/admin/reports/{report.pk}/review/",
                data={
                    "field_decisions": [
                        {
                            "field_change_id": fc.pk,
                            "status": ReportFieldChangeStatus.REJECTED,
                            "admin_note": "اطلاعات اشتباه است.",
                        },
                    ],
                },
                format="json",
            )

        assert response.status_code == status.HTTP_200_OK
        assert response.data["data"]["status"] == ReportStatus.REJECTED

    def test_reject_all_does_not_change_criminal(
        self,
        admin_client: APIClient,
        db,
    ) -> None:
        """رد همه field_changeها نباید هیچ تغییری روی criminal ایجاد کند."""
        criminal = R4JCriminalFactory(city="Tehran")
        report = R4JReportFactory(criminal=criminal, status=ReportStatus.PENDING)
        fc = R4JReportFieldChangeFactory(
            report=report,
            field_name="city",
            suggested_value="Mashhad",
        )

        with patch(_TASK_PATCH_PATH):
            admin_client.post(
                f"/api/v1/r4j/admin/reports/{report.pk}/review/",
                data={
                    "field_decisions": [
                        {
                            "field_change_id": fc.pk,
                            "status": ReportFieldChangeStatus.REJECTED,
                        },
                    ],
                },
                format="json",
            )

        criminal.refresh_from_db()
        assert criminal.city == "Tehran"

    def test_review_notes_only_report_sets_approved(
        self,
        admin_client: APIClient,
        db,
    ) -> None:
        """گزارش فقط با notes (بدون field_change) بعد از review باید APPROVED شود."""
        report = R4JReportFactory(
            notes="اطلاعات تکمیلی مهم",
            status=ReportStatus.PENDING,
        )

        with patch(_TASK_PATCH_PATH):
            response = admin_client.post(
                f"/api/v1/r4j/admin/reports/{report.pk}/review/",
                data={
                    "field_decisions": [],
                    "admin_note": "یادداشت دیده شد.",
                },
                format="json",
            )

        assert response.status_code == status.HTTP_200_OK
        assert response.data["data"]["status"] == ReportStatus.APPROVED


# ============================================================
# Review — State Machine Edge Cases
# ============================================================


class TestAdminReportReviewEdgeCases:
    """edge caseهای review — state machine boundaries."""

    def test_cannot_review_already_approved_report(
        self,
        admin_client: APIClient,
        db,
    ) -> None:
        """گزارش APPROVED نباید قابل review مجدد باشد."""
        report = R4JReportFactory(status=ReportStatus.APPROVED)

        response = admin_client.post(
            f"/api/v1/r4j/admin/reports/{report.pk}/review/",
            data={"field_decisions": [], "admin_note": ""},
            format="json",
        )

        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_cannot_review_rejected_report(
        self,
        admin_client: APIClient,
        db,
    ) -> None:
        """گزارش REJECTED نباید قابل review مجدد باشد."""
        report = R4JReportFactory(status=ReportStatus.REJECTED)

        response = admin_client.post(
            f"/api/v1/r4j/admin/reports/{report.pk}/review/",
            data={"field_decisions": [], "admin_note": ""},
            format="json",
        )

        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_cannot_review_canceled_report(
        self,
        admin_client: APIClient,
        db,
    ) -> None:
        """گزارش CANCELED نباید قابل review باشد."""
        report = R4JReportFactory(status=ReportStatus.CANCELED)

        response = admin_client.post(
            f"/api/v1/r4j/admin/reports/{report.pk}/review/",
            data={"field_decisions": [], "admin_note": ""},
            format="json",
        )

        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_cannot_review_cancel_requested_report(
        self,
        admin_client: APIClient,
        db,
    ) -> None:
        """گزارش CANCEL_REQUESTED نباید از مسیر review بررسی شود.
        باید از مسیر cancel/approve یا cancel/reject برگردد.
        """
        report = R4JReportFactory(status=ReportStatus.CANCEL_REQUESTED)

        response = admin_client.post(
            f"/api/v1/r4j/admin/reports/{report.pk}/review/",
            data={"field_decisions": [], "admin_note": ""},
            format="json",
        )

        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_review_nonexistent_report_returns_404(
        self,
        admin_client: APIClient,
    ) -> None:
        """review روی گزارش ناموجود باید 404 برگرداند."""
        response = admin_client.post(
            "/api/v1/r4j/admin/reports/99999/review/",
            data={"field_decisions": []},
            format="json",
        )
        assert response.status_code == status.HTTP_404_NOT_FOUND


# ============================================================
# Cancel Approve
# ============================================================


class TestAdminReportCancelApprove:
    """تأیید درخواست لغو توسط ادمین."""

    def test_approve_cancel_sets_status_canceled(
        self,
        admin_client: APIClient,
        admin_user,
        db,
    ) -> None:
        """تأیید cancel باید status را CANCELED کند."""
        report = R4JReportFactory(status=ReportStatus.CANCEL_REQUESTED)

        with patch(_TASK_PATCH_PATH) as mock_task:
            mock_task.delay = MagicMock()
            response = admin_client.post(
                f"/api/v1/r4j/admin/reports/{report.pk}/cancel/approve/",
                data={"admin_note": "درخواست معتبر است."},
                format="json",
            )

        assert response.status_code == status.HTTP_200_OK
        assert response.data["data"]["status"] == ReportStatus.CANCELED

        report.refresh_from_db()
        assert report.status == ReportStatus.CANCELED
        assert report.canceled_at is not None
        assert report.reviewed_by_id == admin_user.pk

    def test_approve_cancel_dispatches_audit(
        self,
        admin_client: APIClient,
        admin_user,
        db,
    ) -> None:
        """تأیید cancel باید audit log مناسب dispatch کند."""
        report = R4JReportFactory(status=ReportStatus.CANCEL_REQUESTED)

        with patch(_TASK_PATCH_PATH) as mock_task:
            mock_task.delay = MagicMock()
            admin_client.post(
                f"/api/v1/r4j/admin/reports/{report.pk}/cancel/approve/",
                data={},
                format="json",
            )

        mock_task.delay.assert_called_once()
        kwargs = mock_task.delay.call_args.kwargs
        assert kwargs["action"] == audit_actions.R4J_REPORT_CANCEL_APPROVED
        assert kwargs["user_id"] == admin_user.pk

    def test_cannot_approve_cancel_for_pending_report(
        self,
        admin_client: APIClient,
        db,
    ) -> None:
        """گزارش PENDING نباید از مسیر cancel/approve قابل تغییر باشد."""
        report = R4JReportFactory(status=ReportStatus.PENDING)

        response = admin_client.post(
            f"/api/v1/r4j/admin/reports/{report.pk}/cancel/approve/",
            data={},
            format="json",
        )
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_cannot_approve_cancel_for_approved_report(
        self,
        admin_client: APIClient,
        db,
    ) -> None:
        """گزارش APPROVED نباید از مسیر cancel/approve قابل تغییر باشد."""
        report = R4JReportFactory(status=ReportStatus.APPROVED)

        response = admin_client.post(
            f"/api/v1/r4j/admin/reports/{report.pk}/cancel/approve/",
            data={},
            format="json",
        )
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_approve_cancel_nonexistent_report_returns_404(
        self,
        admin_client: APIClient,
    ) -> None:
        """گزارش ناموجود باید 404 برگرداند."""
        response = admin_client.post(
            "/api/v1/r4j/admin/reports/99999/cancel/approve/",
            data={},
            format="json",
        )
        assert response.status_code == status.HTTP_404_NOT_FOUND


# ============================================================
# Cancel Reject
# ============================================================


class TestAdminReportCancelReject:
    """رد درخواست لغو توسط ادمین."""

    def test_reject_cancel_sets_status_back_to_pending(
        self,
        admin_client: APIClient,
        db,
    ) -> None:
        """رد cancel باید status را به PENDING برگرداند."""
        report = R4JReportFactory(status=ReportStatus.CANCEL_REQUESTED)

        with patch(_TASK_PATCH_PATH) as mock_task:
            mock_task.delay = MagicMock()
            response = admin_client.post(
                f"/api/v1/r4j/admin/reports/{report.pk}/cancel/reject/",
                data={"admin_note": "درخواست معتبر نیست."},
                format="json",
            )

        assert response.status_code == status.HTTP_200_OK
        assert response.data["data"]["status"] == ReportStatus.PENDING

        report.refresh_from_db()
        assert report.status == ReportStatus.PENDING
        assert report.cancel_requested_at is None

    def test_reject_cancel_clears_cancel_requested_at(
        self,
        admin_client: APIClient,
        db,
    ) -> None:
        """بعد از رد cancel، cancel_requested_at باید null شود."""
        from django.utils import timezone

        report = R4JReportFactory(
            status=ReportStatus.CANCEL_REQUESTED,
            cancel_requested_at=timezone.now(),
        )

        with patch(_TASK_PATCH_PATH):
            admin_client.post(
                f"/api/v1/r4j/admin/reports/{report.pk}/cancel/reject/",
                data={},
                format="json",
            )

        report.refresh_from_db()
        assert report.cancel_requested_at is None

    def test_reject_cancel_dispatches_audit(
        self,
        admin_client: APIClient,
        admin_user,
        db,
    ) -> None:
        """رد cancel باید audit log مناسب dispatch کند."""
        report = R4JReportFactory(status=ReportStatus.CANCEL_REQUESTED)

        with patch(_TASK_PATCH_PATH) as mock_task:
            mock_task.delay = MagicMock()
            admin_client.post(
                f"/api/v1/r4j/admin/reports/{report.pk}/cancel/reject/",
                data={},
                format="json",
            )

        mock_task.delay.assert_called_once()
        kwargs = mock_task.delay.call_args.kwargs
        assert kwargs["action"] == audit_actions.R4J_REPORT_CANCEL_REJECTED
        assert kwargs["user_id"] == admin_user.pk

    def test_cannot_reject_cancel_for_pending_report(
        self,
        admin_client: APIClient,
        db,
    ) -> None:
        """گزارش PENDING نباید از مسیر cancel/reject قابل تغییر باشد."""
        report = R4JReportFactory(status=ReportStatus.PENDING)

        response = admin_client.post(
            f"/api/v1/r4j/admin/reports/{report.pk}/cancel/reject/",
            data={},
            format="json",
        )
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_cannot_reject_cancel_for_canceled_report(
        self,
        admin_client: APIClient,
        db,
    ) -> None:
        """گزارش CANCELED نباید از مسیر cancel/reject قابل تغییر باشد."""
        report = R4JReportFactory(status=ReportStatus.CANCELED)

        response = admin_client.post(
            f"/api/v1/r4j/admin/reports/{report.pk}/cancel/reject/",
            data={},
            format="json",
        )
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_reject_cancel_nonexistent_report_returns_404(
        self,
        admin_client: APIClient,
    ) -> None:
        """گزارش ناموجود باید 404 برگرداند."""
        response = admin_client.post(
            "/api/v1/r4j/admin/reports/99999/cancel/reject/",
            data={},
            format="json",
        )
        assert response.status_code == status.HTTP_404_NOT_FOUND

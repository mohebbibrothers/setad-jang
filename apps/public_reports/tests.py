"""
Tests for Public Reports — Phase Audit.4.

این فایل شامل تست‌های integration برای:
- audit wiring روی report creation و admin mutations
- CRUD operations — happy path و edge cases
- sensitive data redaction

اصول تست:
- هر تست یک scenario واحد را cover می‌کند.
- async audit dispatch با patch task تست می‌شود.
- sync audit با بررسی DB مستقیم تست می‌شود.
- factory-boy برای ساخت داده تست استفاده می‌شود.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken

from apps.audit_logs import actions as audit_actions
from apps.audit_logs.models import AuditLog
from apps.public_reports.choices import ReportStatus
from tests.factories.auth import AdminUserFactory, UserFactory
from tests.factories.public_reports import ReportFactory, ReportSubjectFactory

# ============================================================
# Constants
# ============================================================

_TASK_PATCH_PATH = "apps.audit_logs.tasks.create_audit_log_task"


# ============================================================
# Fixtures
# ============================================================


@pytest.fixture
def api_client() -> APIClient:
    """APIClient بدون احراز هویت."""
    return APIClient()


@pytest.fixture
def admin_user(db):
    """کاربر ادمین فعال."""
    return AdminUserFactory(email="reports-admin@example.com")


@pytest.fixture
def admin_client(admin_user) -> APIClient:
    """APIClient احراز هویت شده با کاربر ادمین."""
    client = APIClient()
    refresh = RefreshToken.for_user(admin_user)
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {refresh.access_token!s}")
    return client


@pytest.fixture
def subject(db):
    """یک موضوع گزارش فعال."""
    return ReportSubjectFactory(title="موضوع پیش‌فرض")


@pytest.fixture
def report(db, subject):
    """یک گزارش مردمی ثبت‌شده."""
    return ReportFactory(subject=subject)


# ============================================================
# Tests — Report Creation (Public)
# ============================================================


@pytest.mark.django_db
class TestReportCreationAudit:
    """Audit wiring برای ReportCreateAPIView."""

    def test_report_create_dispatches_async_audit(self, api_client, subject):
        """ثبت گزارش باید REPORT_CREATED را async dispatch کند."""
        with patch(_TASK_PATCH_PATH) as mock_task:
            mock_task.delay = MagicMock()
            response = api_client.post(
                reverse("public_reports:report-create"),
                data={
                    "full_name": "علی محمدی",
                    "phone_number": "09121234567",
                    "subject_id": subject.pk,
                    "description": "توضیحات تست گزارش",
                },
                format="json",
            )

        assert response.status_code == status.HTTP_201_CREATED
        mock_task.delay.assert_called_once()
        call_kwargs = mock_task.delay.call_args.kwargs
        assert call_kwargs["action"] == audit_actions.REPORT_CREATED
        assert call_kwargs["resource_type"] == "report"
        assert call_kwargs["user_id"] is None  # anonymous user
        assert call_kwargs["extra_data"]["subject_id"] == subject.pk

    def test_report_create_by_authenticated_user_has_user_id(
        self,
        subject,
        db,
    ):
        """اگر کاربر لاگین کرده باشد، user_id باید ثبت شود."""
        user = UserFactory(email="reporter@example.com", is_email_verified=True)
        client = APIClient()
        refresh = RefreshToken.for_user(user)
        client.credentials(HTTP_AUTHORIZATION=f"Bearer {refresh.access_token!s}")

        with patch(_TASK_PATCH_PATH) as mock_task:
            mock_task.delay = MagicMock()
            response = client.post(
                reverse("public_reports:report-create"),
                data={
                    "full_name": "حسین احمدی",
                    "subject_id": subject.pk,
                    "description": "گزارش کاربر لاگین کرده",
                },
                format="json",
            )

        assert response.status_code == status.HTTP_201_CREATED
        call_kwargs = mock_task.delay.call_args.kwargs
        assert call_kwargs["user_id"] == user.pk

    def test_report_create_request_id_propagated(self, api_client, subject):
        """request_id باید در audit ثبت شود."""
        with patch(_TASK_PATCH_PATH) as mock_task:
            mock_task.delay = MagicMock()
            api_client.post(
                reverse("public_reports:report-create"),
                data={
                    "full_name": "تست",
                    "subject_id": subject.pk,
                    "description": "تست request_id",
                },
                format="json",
                HTTP_X_REQUEST_ID="req-reports-001",
            )

        call_kwargs = mock_task.delay.call_args.kwargs
        assert call_kwargs["request_id"] == "req-reports-001"


# ============================================================
# Tests — Subject CRUD (Admin)
# ============================================================


@pytest.mark.django_db
class TestSubjectCRUDAudit:
    """Audit wiring برای admin subject endpoints."""

    def test_subject_create_dispatches_async_audit(self, admin_client, admin_user):
        """ساخت موضوع باید SUBJECT_CREATED را async dispatch کند."""
        with patch(_TASK_PATCH_PATH) as mock_task:
            mock_task.delay = MagicMock()
            response = admin_client.post(
                reverse("public_reports:admin-subject-list-create"),
                data={
                    "title": "موضوع جدید تست",
                    "description": "توضیحات",
                    "order": 5,
                },
                format="json",
            )

        assert response.status_code == status.HTTP_201_CREATED
        mock_task.delay.assert_called_once()
        call_kwargs = mock_task.delay.call_args.kwargs
        assert call_kwargs["action"] == audit_actions.SUBJECT_CREATED
        assert call_kwargs["resource_type"] == "report_subject"
        assert call_kwargs["user_id"] == admin_user.pk
        assert call_kwargs["extra_data"]["title"] == "موضوع جدید تست"

    def test_subject_update_dispatches_async_audit(
        self,
        admin_client,
        admin_user,
        subject,
    ):
        """ویرایش موضوع باید SUBJECT_UPDATED را async dispatch کند."""
        with patch(_TASK_PATCH_PATH) as mock_task:
            mock_task.delay = MagicMock()
            response = admin_client.patch(
                reverse(
                    "public_reports:admin-subject-detail",
                    kwargs={"subject_id": subject.pk},
                ),
                data={"title": "موضوع ویرایش‌شده"},
                format="json",
            )

        assert response.status_code == status.HTTP_200_OK
        mock_task.delay.assert_called_once()
        call_kwargs = mock_task.delay.call_args.kwargs
        assert call_kwargs["action"] == audit_actions.SUBJECT_UPDATED
        assert call_kwargs["resource_id"] == str(subject.pk)
        assert call_kwargs["changes"]["title"] == "موضوع ویرایش‌شده"

    def test_subject_delete_creates_sync_audit(
        self,
        admin_client,
        admin_user,
        subject,
    ):
        """
        حذف موضوع باید SUBJECT_DELETED را SYNCHRONOUSLY ثبت کند
        چون compliance-critical است.
        """
        response = admin_client.delete(
            reverse(
                "public_reports:admin-subject-detail",
                kwargs={"subject_id": subject.pk},
            ),
        )

        assert response.status_code == status.HTTP_200_OK

        # باید مستقیم در DB ثبت شده باشد (sync)
        audit = AuditLog.objects.filter(
            action=audit_actions.SUBJECT_DELETED,
            resource_type="report_subject",
            resource_id=str(subject.pk),
        ).first()

        assert audit is not None
        assert audit.user_id == admin_user.pk
        assert audit.extra_data["title"] == subject.title


# ============================================================
# Tests — Report Status Change (Admin)
# ============================================================


@pytest.mark.django_db
class TestReportStatusChangeAudit:
    """Audit wiring برای AdminReportStatusUpdateAPIView."""

    def test_status_change_creates_sync_audit(
        self,
        admin_client,
        admin_user,
        report,
    ):
        """
        تغییر وضعیت گزارش باید REPORT_STATUS_CHANGED را
        SYNCHRONOUSLY ثبت کند.
        """
        response = admin_client.patch(
            reverse(
                "public_reports:admin-report-status",
                kwargs={"report_id": report.pk},
            ),
            data={
                "status": ReportStatus.APPROVED,
                "admin_note": "تأیید شد.",
            },
            format="json",
        )

        assert response.status_code == status.HTTP_200_OK

        audit = AuditLog.objects.filter(
            action=audit_actions.REPORT_STATUS_CHANGED,
            resource_type="report",
            resource_id=str(report.pk),
        ).first()

        assert audit is not None
        assert audit.user_id == admin_user.pk
        assert audit.changes["status"]["before"] == ReportStatus.PENDING
        assert audit.changes["status"]["after"] == ReportStatus.APPROVED

    def test_status_change_audit_has_no_sensitive_data(
        self,
        admin_client,
        admin_user,
        report,
    ):
        """Audit log تغییر وضعیت نباید هیچ sensitive data داشته باشد."""
        admin_client.patch(
            reverse(
                "public_reports:admin-report-status",
                kwargs={"report_id": report.pk},
            ),
            data={"status": ReportStatus.REVIEWING},
            format="json",
        )

        audit = AuditLog.objects.filter(
            action=audit_actions.REPORT_STATUS_CHANGED,
            resource_id=str(report.pk),
        ).first()

        assert audit is not None
        audit_str = str(audit.changes) + str(audit.extra_data)
        assert "pbkdf2" not in audit_str.lower()
        assert "eyj" not in audit_str.lower()


# ============================================================
# Tests — Public Endpoints (CRUD — basic happy path)
# ============================================================


@pytest.mark.django_db
class TestPublicEndpoints:
    """تست‌های پایه برای endpointهای عمومی."""

    def test_subject_list_returns_active_subjects(self, api_client, db):
        """لیست موضوعات فقط موضوعات فعال را برگرداند."""
        ReportSubjectFactory(title="فعال", is_active=True)
        ReportSubjectFactory(title="غیرفعال", is_active=False)

        response = api_client.get(reverse("public_reports:subject-list"))

        assert response.status_code == status.HTTP_200_OK
        titles = [s["title"] for s in response.data["data"]]
        assert "فعال" in titles
        assert "غیرفعال" not in titles

    def test_report_create_with_invalid_subject_fails(self, api_client, db):
        """ثبت گزارش با موضوع نامعتبر باید 400 برگرداند."""
        response = api_client.post(
            reverse("public_reports:report-create"),
            data={
                "full_name": "تست",
                "subject_id": 99999,
                "description": "توضیحات",
            },
            format="json",
        )

        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_report_create_without_required_fields_fails(self, api_client, db):
        """ثبت گزارش بدون فیلدهای الزامی باید 400 برگرداند."""
        response = api_client.post(
            reverse("public_reports:report-create"),
            data={},
            format="json",
        )

        assert response.status_code == status.HTTP_400_BAD_REQUEST


# ============================================================
# Tests — Admin Endpoints (CRUD — basic happy path)
# ============================================================


@pytest.mark.django_db
class TestAdminEndpoints:
    """تست‌های پایه برای endpointهای ادمین."""

    def test_admin_subject_list(self, admin_client, db):
        """لیست ادمین باید شامل موضوعات فعال و غیرفعال باشد."""
        ReportSubjectFactory(title="فعال ادمین", is_active=True)
        ReportSubjectFactory(title="غیرفعال ادمین", is_active=False)

        response = admin_client.get(
            reverse("public_reports:admin-subject-list-create"),
        )

        assert response.status_code == status.HTTP_200_OK
        titles = [s["title"] for s in response.data["data"]]
        assert "فعال ادمین" in titles
        assert "غیرفعال ادمین" in titles

    def test_admin_report_detail(self, admin_client, report):
        """جزئیات گزارش باید 200 برگرداند."""
        response = admin_client.get(
            reverse(
                "public_reports:admin-report-detail",
                kwargs={"report_id": report.pk},
            ),
        )

        assert response.status_code == status.HTTP_200_OK
        assert response.data["data"]["id"] == report.pk

    def test_admin_report_not_found(self, admin_client, db):
        """جزئیات گزارش نامعتبر باید 404 برگرداند."""
        response = admin_client.get(
            reverse(
                "public_reports:admin-report-detail",
                kwargs={"report_id": 99999},
            ),
        )

        assert response.status_code == status.HTTP_404_NOT_FOUND

    def test_admin_subject_not_found(self, admin_client, db):
        """جزئیات موضوع نامعتبر باید 404 برگرداند."""
        response = admin_client.get(
            reverse(
                "public_reports:admin-subject-detail",
                kwargs={"subject_id": 99999},
            ),
        )

        assert response.status_code == status.HTTP_404_NOT_FOUND

    def test_unauthenticated_admin_access_forbidden(self, api_client, db):
        """دسترسی بدون auth به admin endpoints باید 401 برگرداند."""
        response = api_client.get(
            reverse("public_reports:admin-subject-list-create"),
        )

        assert response.status_code == status.HTTP_401_UNAUTHORIZED

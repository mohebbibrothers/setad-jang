"""
Audit forensic hardening tests.

Phase 5 هدفش این است که audit trail واقعاً append-only، غنی از metadata و
قابل اتکا برای incident review باشد. این تست‌ها guard می‌گذارند که:
- audit log بعد از ایجاد قابل update/delete نباشد.
- metadata عملیاتی request کامل استخراج و ذخیره شود.
- task async همان metadata را به service منتقل کند.
- API ادمین metadata جدید را نمایش و فیلتر کند.
"""

from __future__ import annotations

import pytest
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient, APIRequestFactory
from rest_framework_simplejwt.tokens import RefreshToken

from apps.audit_logs import actions as audit_actions
from apps.audit_logs.helpers import extract_audit_metadata
from apps.audit_logs.models import AuditLog, AuditLogImmutableError
from apps.audit_logs.services import create_audit_log
from apps.audit_logs.tasks import create_audit_log_task
from tests.factories.audit_logs import AuditLogFactory
from tests.factories.auth import AdminUserFactory, UserFactory

pytestmark = pytest.mark.django_db


def _admin_client() -> APIClient:
    """ساخت APIClient احرازشده با ادمین."""
    admin = AdminUserFactory(email="audit-forensic-admin@example.com")
    refresh = RefreshToken.for_user(admin)
    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {refresh.access_token!s}")
    return client


class TestAuditLogAppendOnlyModel:
    """تست‌های append-only بودن model/manager لاگ فعالیت."""

    def test_existing_audit_log_cannot_be_saved_again(self) -> None:
        audit = AuditLogFactory(action=audit_actions.LOGIN_SUCCESS)
        audit.action = audit_actions.LOGOUT

        with pytest.raises(AuditLogImmutableError):
            audit.save()

        audit.refresh_from_db()
        assert audit.action == audit_actions.LOGIN_SUCCESS

    def test_existing_audit_log_cannot_be_hard_deleted(self) -> None:
        audit = AuditLogFactory()

        with pytest.raises(AuditLogImmutableError):
            audit.delete()

        assert AuditLog.objects.filter(pk=audit.pk).exists()

    def test_existing_audit_log_cannot_be_soft_deleted_or_restored(self) -> None:
        audit = AuditLogFactory()

        with pytest.raises(AuditLogImmutableError):
            audit.soft_delete()

        with pytest.raises(AuditLogImmutableError):
            audit.restore()

    def test_bulk_update_and_delete_are_blocked(self) -> None:
        audit = AuditLogFactory(action=audit_actions.LOGIN_SUCCESS)

        with pytest.raises(AuditLogImmutableError):
            AuditLog.objects.filter(pk=audit.pk).update(action=audit_actions.LOGOUT)

        with pytest.raises(AuditLogImmutableError):
            AuditLog.objects.filter(pk=audit.pk).delete()

        audit.refresh_from_db()
        assert audit.action == audit_actions.LOGIN_SUCCESS


class TestAuditMetadataExtractionAndPersistence:
    """تست‌های metadata عملیاتی request برای forensic tracing."""

    def test_extract_audit_metadata_includes_method_path_user_agent_ip_and_request_id(self) -> None:
        # XFF ورودی عمداً «جعل‌شده» فرستاده می‌شود: با NUM_PROXIES=0
        # (پیش‌فرض پروژه) باید نادیده گرفته شود و REMOTE_ADDR ثبت گردد
        # (یافتهٔ P1 ممیزی — XFF قابل جعل audit trail را آلوده می‌کند).
        request = APIRequestFactory().post(
            "/api/v1/example/path/?debug=1",
            HTTP_X_FORWARDED_FOR="203.0.113.5, 10.0.0.1",
            HTTP_X_REQUEST_ID="req-forensic-001",
            HTTP_USER_AGENT="Mozilla/5.0 forensic-test",
        )

        metadata = extract_audit_metadata(request)

        assert metadata == {
            "ip_address": "127.0.0.1",
            "request_id": "req-forensic-001",
            "user_agent": "Mozilla/5.0 forensic-test",
            "path": "/api/v1/example/path/",
            "method": "POST",
        }

    def test_create_audit_log_persists_forensic_metadata(self) -> None:
        user = UserFactory(email="forensic-user@example.com")

        audit = create_audit_log(
            user_id=user.pk,
            action=audit_actions.LOGIN_SUCCESS,
            resource_type="user",
            resource_id=str(user.pk),
            ip_address="198.51.100.10",
            request_id="req-persist-001",
            user_agent="pytest-agent/forensic",
            path="/api/v1/auth/login/password/",
            method="POST",
            extra_data={"method": "password"},
        )

        assert audit.ip_address == "198.51.100.10"
        assert audit.request_id == "req-persist-001"
        assert audit.user_agent == "pytest-agent/forensic"
        assert audit.path == "/api/v1/auth/login/password/"
        assert audit.method == "POST"

    def test_async_task_persists_forensic_metadata(self) -> None:
        create_audit_log_task(
            user_id=None,
            action=audit_actions.REPORT_CREATED,
            resource_type="report",
            resource_id="42",
            ip_address="198.51.100.20",
            request_id="req-task-001",
            user_agent="pytest-agent/task",
            path="/api/v1/public-reports/reports/",
            method="POST",
        )

        audit = AuditLog.objects.get(action=audit_actions.REPORT_CREATED)
        assert audit.ip_address == "198.51.100.20"
        assert audit.request_id == "req-task-001"
        assert audit.user_agent == "pytest-agent/task"
        assert audit.path == "/api/v1/public-reports/reports/"
        assert audit.method == "POST"


class TestAuditLogAdminAPIForensicMetadata:
    """تست‌های API ادمین برای مشاهده و فیلتر metadata جدید."""

    def test_detail_includes_forensic_metadata(self) -> None:
        client = _admin_client()
        audit = AuditLogFactory(
            action=audit_actions.LOGIN_SUCCESS,
            method="POST",
            path="/api/v1/auth/login/password/",
            user_agent="pytest-agent/detail",
        )

        response = client.get(
            reverse(
                "audit_logs:admin-log-detail",
                kwargs={"audit_log_id": audit.pk},
            ),
        )

        assert response.status_code == status.HTTP_200_OK
        data = response.data["data"]
        assert data["method"] == "POST"
        assert data["path"] == "/api/v1/auth/login/password/"
        assert data["user_agent"] == "pytest-agent/detail"

    def test_list_filters_by_method_and_path(self) -> None:
        client = _admin_client()
        expected = AuditLogFactory(
            action=audit_actions.LOGIN_SUCCESS,
            method="POST",
            path="/api/v1/auth/login/password/",
        )
        AuditLogFactory(
            action=audit_actions.LOGOUT,
            method="GET",
            path="/api/v1/auth/logout/",
        )

        response = client.get(
            reverse("audit_logs:admin-log-list"),
            data={"method": "post", "path": "login/password"},
        )

        assert response.status_code == status.HTTP_200_OK
        results = response.data["data"]["results"]
        assert len(results) == 1
        assert results[0]["id"] == expected.pk
        assert results[0]["method"] == "POST"
        assert results[0]["path"] == "/api/v1/auth/login/password/"

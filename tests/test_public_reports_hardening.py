"""
Public reports hardening tests.

این تست‌ها regression guardهای فاز modernization گزارشات مردمی هستند:
- response عمومی ثبت گزارش نباید metadata داخلی مثل submitter_ip/admin_note را leak کند.
- state machine تغییر وضعیت باید terminal states را محافظت کند.
- محدودیت تعداد attachmentها باید با مستندات endpoint هم‌خوان باشد.
"""

from __future__ import annotations

import io
from unittest.mock import MagicMock, patch

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse
from PIL import Image
from rest_framework import status
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken

from apps.audit_logs import actions as audit_actions
from apps.audit_logs.models import AuditLog
from apps.public_reports.choices import ReportStatus
from apps.public_reports.serializers import ReportCreateSerializer
from apps.public_reports.validators import MAX_ATTACHMENTS_PER_REPORT
from tests.factories.auth import AdminUserFactory
from tests.factories.public_reports import ReportFactory, ReportSubjectFactory

pytestmark = pytest.mark.django_db

_TASK_PATCH_PATH = "apps.audit_logs.tasks.create_audit_log_task"


def _make_image_file(name: str = "report.png") -> SimpleUploadedFile:
    """ساخت فایل تصویر معتبر با Pillow برای تست upload/serializer."""
    buffer = io.BytesIO()
    Image.new("RGB", (12, 12), color=(255, 0, 0)).save(buffer, format="PNG")
    return SimpleUploadedFile(name, buffer.getvalue(), content_type="image/png")


def _admin_client() -> APIClient:
    """ساخت APIClient احرازشده با ادمین."""
    admin = AdminUserFactory(email="public-report-hardening-admin@example.com")
    refresh = RefreshToken.for_user(admin)
    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {refresh.access_token!s}")
    return client


class TestPublicReportResponsePrivacy:
    """تست‌های عدم افشای metadata داخلی در endpoint عمومی ثبت گزارش."""

    def test_report_create_response_does_not_expose_submitter_ip_or_admin_note(self) -> None:
        subject = ReportSubjectFactory(title="حریم خصوصی")
        client = APIClient()

        with patch(_TASK_PATCH_PATH) as mock_task:
            mock_task.delay = MagicMock()
            response = client.post(
                reverse("public_reports:report-create"),
                data={
                    "full_name": "گزارشگر تست",
                    "phone_number": "09121234567",
                    "subject_id": subject.pk,
                    "description": "گزارش تستی با metadata داخلی",
                },
                format="json",
                REMOTE_ADDR="203.0.113.10",
            )

        assert response.status_code == status.HTTP_201_CREATED
        data = response.data["data"]
        assert "submitter_ip" not in data
        assert "admin_note" not in data
        assert data["status"] == ReportStatus.PENDING
        mock_task.delay.assert_called_once()
        assert mock_task.delay.call_args.kwargs["action"] == audit_actions.REPORT_CREATED


class TestPublicReportStatusStateMachine:
    """تست‌های state machine وضعیت گزارش مردمی."""

    def test_terminal_approved_report_cannot_move_back_to_reviewing(self) -> None:
        report = ReportFactory(status=ReportStatus.APPROVED)
        client = _admin_client()

        response = client.patch(
            reverse(
                "public_reports:admin-report-status",
                kwargs={"report_id": report.pk},
            ),
            data={"status": ReportStatus.REVIEWING},
            format="json",
        )

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        report.refresh_from_db()
        assert report.status == ReportStatus.APPROVED
        assert not AuditLog.objects.filter(
            action=audit_actions.REPORT_STATUS_CHANGED,
            resource_id=str(report.pk),
        ).exists()

    def test_reviewing_report_can_be_approved(self) -> None:
        report = ReportFactory(status=ReportStatus.REVIEWING)
        client = _admin_client()

        response = client.patch(
            reverse(
                "public_reports:admin-report-status",
                kwargs={"report_id": report.pk},
            ),
            data={"status": ReportStatus.APPROVED},
            format="json",
        )

        assert response.status_code == status.HTTP_200_OK
        report.refresh_from_db()
        assert report.status == ReportStatus.APPROVED


class TestPublicReportAttachmentLimits:
    """تست‌های محدودیت تعداد پیوست برای گزارش مردمی."""

    def test_report_create_serializer_rejects_more_than_five_attachments(self) -> None:
        subject = ReportSubjectFactory(title="پیوست‌ها")
        attachments = [
            _make_image_file(f"report-{index}.png")
            for index in range(MAX_ATTACHMENTS_PER_REPORT + 1)
        ]

        serializer = ReportCreateSerializer(
            data={
                "full_name": "گزارشگر تست",
                "subject_id": subject.pk,
                "description": "گزارش با پیوست زیاد",
                "attachments": attachments,
            }
        )

        assert serializer.is_valid() is False
        assert "attachments" in serializer.errors
        assert MAX_ATTACHMENTS_PER_REPORT == 5

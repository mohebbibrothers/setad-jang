"""
Public reports completion hardening tests.

این تست‌ها ادامه‌ی modernization اپ گزارشات مردمی هستند و سناریوهایی را پوشش
می‌دهند که برای production مهم‌اند:
- upload واقعی multipart با تصویر معتبر Pillow-generated
- boundary دقیق تعداد attachmentها
- validation فرمت فایل
- فیلتر و pagination پنل ادمین
- state transitionهای service layer به‌صورت مستقیم
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

from apps.public_reports.choices import ReportStatus
from apps.public_reports.models import ReportAttachment
from apps.public_reports.services import InvalidReportStatusTransition, update_report_status
from apps.public_reports.validators import MAX_ATTACHMENTS_PER_REPORT
from tests.factories.auth import AdminUserFactory
from tests.factories.public_reports import ReportFactory, ReportSubjectFactory

pytestmark = pytest.mark.django_db

_TASK_PATCH_PATH = "apps.audit_logs.tasks.create_audit_log_task"


def _make_image_file(name: str = "report.png") -> SimpleUploadedFile:
    """ساخت تصویر معتبر با Pillow برای multipart upload تست‌ها."""
    buffer = io.BytesIO()
    Image.new("RGB", (16, 16), color=(0, 128, 255)).save(buffer, format="PNG")
    return SimpleUploadedFile(name, buffer.getvalue(), content_type="image/png")


def _make_text_file(name: str = "bad.txt") -> SimpleUploadedFile:
    """ساخت فایل غیرتصویری برای تست validation فرمت/محتوا."""
    return SimpleUploadedFile(name, b"not an image", content_type="text/plain")


def _admin_client() -> APIClient:
    """ساخت APIClient احرازشده با ادمین."""
    admin = AdminUserFactory(email="public-report-completion-admin@example.com")
    refresh = RefreshToken.for_user(admin)
    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {refresh.access_token!s}")
    return client


class TestPublicReportMultipartUpload:
    """تست‌های end-to-end برای upload پیوست گزارش مردمی."""

    def test_report_create_accepts_exactly_five_valid_images(self) -> None:
        subject = ReportSubjectFactory(title="آپلود پنج تصویر")
        client = APIClient()
        attachments = [
            _make_image_file(f"evidence-{index}.png")
            for index in range(MAX_ATTACHMENTS_PER_REPORT)
        ]

        with patch(_TASK_PATCH_PATH) as mock_task:
            mock_task.delay = MagicMock()
            response = client.post(
                reverse("public_reports:report-create"),
                data={
                    "full_name": "گزارشگر پیوست",
                    "phone_number": "09121234567",
                    "subject_id": subject.pk,
                    "description": "گزارش همراه با پنج تصویر معتبر",
                    "attachments": attachments,
                },
                format="multipart",
            )

        assert response.status_code == status.HTTP_201_CREATED
        assert len(response.data["data"]["attachments"]) == MAX_ATTACHMENTS_PER_REPORT
        assert ReportAttachment.objects.count() == MAX_ATTACHMENTS_PER_REPORT
        mock_task.delay.assert_called_once()

    def test_report_create_rejects_six_images(self) -> None:
        subject = ReportSubjectFactory(title="آپلود بیش از حد")
        client = APIClient()
        attachments = [
            _make_image_file(f"too-many-{index}.png")
            for index in range(MAX_ATTACHMENTS_PER_REPORT + 1)
        ]

        response = client.post(
            reverse("public_reports:report-create"),
            data={
                "full_name": "گزارشگر پیوست زیاد",
                "subject_id": subject.pk,
                "description": "گزارش با تعداد پیوست غیرمجاز",
                "attachments": attachments,
            },
            format="multipart",
        )

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert ReportAttachment.objects.count() == 0
        assert "attachments" in response.data["errors"]

    def test_report_create_rejects_non_image_attachment(self) -> None:
        subject = ReportSubjectFactory(title="فایل نامعتبر")
        client = APIClient()

        response = client.post(
            reverse("public_reports:report-create"),
            data={
                "full_name": "گزارشگر فایل نامعتبر",
                "subject_id": subject.pk,
                "description": "گزارش با فایل غیرتصویری",
                "attachments": [_make_text_file()],
            },
            format="multipart",
        )

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert ReportAttachment.objects.count() == 0
        assert "attachments" in response.data["errors"]


class TestPublicReportsAdminListFilters:
    """تست‌های فیلتر و pagination لیست ادمین گزارش‌ها."""

    def test_admin_report_list_filters_by_status_and_subject(self) -> None:
        client = _admin_client()
        subject_a = ReportSubjectFactory(title="موضوع A")
        subject_b = ReportSubjectFactory(title="موضوع B")
        expected = ReportFactory(subject=subject_a, status=ReportStatus.APPROVED)
        ReportFactory(subject=subject_a, status=ReportStatus.PENDING)
        ReportFactory(subject=subject_b, status=ReportStatus.APPROVED)

        response = client.get(
            reverse("public_reports:admin-report-list"),
            data={"status": ReportStatus.APPROVED, "subject": subject_a.pk},
        )

        assert response.status_code == status.HTTP_200_OK
        data = response.data["data"]
        assert set(data) == {"count", "next", "previous", "results"}
        assert data["count"] == 1
        assert data["results"][0]["id"] == expected.pk

    def test_admin_report_list_uses_enveloped_pagination(self) -> None:
        client = _admin_client()
        subject = ReportSubjectFactory(title="صفحه‌بندی")
        for index in range(3):
            ReportFactory(subject=subject, full_name=f"گزارشگر {index}")

        response = client.get(
            reverse("public_reports:admin-report-list"),
            data={"page_size": 2},
        )

        assert response.status_code == status.HTTP_200_OK
        assert response.data["success"] is True
        assert response.data["data"]["count"] == 3
        assert len(response.data["data"]["results"]) == 2


class TestPublicReportServiceStateMachine:
    """تست مستقیم service برای transitionهای وضعیت گزارش."""

    @pytest.mark.parametrize(
        ("old_status", "new_status"),
        [
            (ReportStatus.PENDING, ReportStatus.REVIEWING),
            (ReportStatus.PENDING, ReportStatus.APPROVED),
            (ReportStatus.PENDING, ReportStatus.REJECTED),
            (ReportStatus.REVIEWING, ReportStatus.PENDING),
            (ReportStatus.REVIEWING, ReportStatus.APPROVED),
            (ReportStatus.REVIEWING, ReportStatus.REJECTED),
        ],
    )
    def test_allowed_transitions_are_persisted(self, old_status: str, new_status: str) -> None:
        report = ReportFactory(status=old_status)

        updated = update_report_status(report=report, status=new_status, admin_note="ok")

        assert updated.status == new_status
        assert updated.admin_note == "ok"

    @pytest.mark.parametrize(
        ("old_status", "new_status"),
        [
            (ReportStatus.APPROVED, ReportStatus.PENDING),
            (ReportStatus.APPROVED, ReportStatus.REVIEWING),
            (ReportStatus.APPROVED, ReportStatus.REJECTED),
            (ReportStatus.REJECTED, ReportStatus.PENDING),
            (ReportStatus.REJECTED, ReportStatus.REVIEWING),
            (ReportStatus.REJECTED, ReportStatus.APPROVED),
        ],
    )
    def test_terminal_transitions_are_rejected(self, old_status: str, new_status: str) -> None:
        report = ReportFactory(status=old_status)

        with pytest.raises(InvalidReportStatusTransition):
            update_report_status(report=report, status=new_status)

        report.refresh_from_db()
        assert report.status == old_status

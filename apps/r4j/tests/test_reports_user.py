"""
Tests — apps.r4j user report endpoints (Phase R4J.3)

این تست‌ها رفتار report endpoints از دید کاربر را verify می‌کنند:

- submit report (happy path + validation + edge cases)
- submit report with attachments (JSON + multipart)
- list my reports (scope isolation + filter)
- retrieve my report (IDOR protection)
- cancel request (state machine exhaustive)

اصول طراحی:
- هر کلاس تست یک scenario مستقل دارد.
- mock کردن audit task برای جلوگیری از celery overhead.
- IDOR scenarios صریحاً تست می‌شوند.
- state machine از تمام جهت‌ها cover می‌شود.
- attachment flow هم در JSON و هم در multipart تست می‌شود.
"""

from __future__ import annotations

import json
from io import BytesIO
from unittest.mock import MagicMock, patch

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from rest_framework import status
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken

from apps.audit_logs import actions as audit_actions
from apps.r4j.choices import ReportFieldChangeStatus, ReportStatus
from apps.r4j.models import R4JReport, R4JReportAttachment, R4JReportFieldChange
from tests.factories.auth import UserFactory
from tests.factories.r4j import (
    R4JCriminalFactory,
    R4JReportFactory,
    R4JReportFieldChangeFactory,
)

pytestmark = [pytest.mark.django_db]

_TASK_PATCH_PATH = "apps.audit_logs.tasks.create_audit_log_task"


# ============================================================
# Helpers
# ============================================================


def _make_minimal_pdf() -> SimpleUploadedFile:
    """ساخت یک فایل PDF minimal in-memory برای تست."""
    return SimpleUploadedFile(
        name="test_attachment.pdf",
        content=b"%PDF-1.4 minimal",
        content_type="application/pdf",
    )


def _make_minimal_image() -> SimpleUploadedFile:
    """ساخت یک فایل تصویری minimal in-memory برای تست."""
    return SimpleUploadedFile(
        name="test_image.jpg",
        content=BytesIO(b"\xff\xd8\xff\xe0" + b"\x00" * 100).getvalue(),
        content_type="image/jpeg",
    )


# ============================================================
# Fixtures
# ============================================================


@pytest.fixture
def api_client() -> APIClient:
    """Client بدون احراز هویت."""
    return APIClient()


@pytest.fixture
def regular_user(db):
    """کاربر عادی لاگین‌کرده با ایمیل تأیید شده."""
    return UserFactory(email="reporter@example.com", is_email_verified=True)


@pytest.fixture
def auth_client(regular_user) -> APIClient:
    """Client احراز هویت‌شده برای کاربر عادی."""
    client = APIClient()
    refresh = RefreshToken.for_user(regular_user)
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {refresh.access_token!s}")
    return client


@pytest.fixture
def published_criminal(db):
    """مجرم منتشرشده برای ارسال گزارش."""
    criminal = R4JCriminalFactory(
        first_name="Donald",
        last_name="Trump",
    )
    criminal.publish()
    return criminal


@pytest.fixture
def published_criminal_simple(db):
    """مجرم منتشرشده ساده — بدون داده خاص."""
    criminal = R4JCriminalFactory()
    criminal.publish()
    return criminal


# ============================================================
# Submit Report — Happy Path
# ============================================================


class TestReportSubmitHappyPath:
    """ارسال موفق گزارش — happy path scenarios."""

    def test_submit_with_field_changes_returns_201(
        self,
        auth_client: APIClient,
        published_criminal_simple,
    ) -> None:
        """گزارش با field_change معتبر باید 201 برگرداند."""
        with patch(_TASK_PATCH_PATH) as mock_task:
            mock_task.delay = MagicMock()
            response = auth_client.post(
                f"/api/v1/r4j/criminals/{published_criminal_simple.pk}/reports/",
                data={
                    "notes": "اطلاعات تکمیلی",
                    "field_changes": [
                        {
                            "field_name": "country",
                            "suggested_value": "USA",
                        },
                    ],
                },
                format="json",
            )

        assert response.status_code == status.HTTP_201_CREATED
        data = response.data["data"]
        assert data["status"] == ReportStatus.PENDING
        assert len(data["field_changes"]) == 1

    def test_submit_with_only_notes_returns_201(
        self,
        auth_client: APIClient,
        published_criminal_simple,
    ) -> None:
        """گزارش با فقط یادداشت (بدون field_change) باید مجاز باشد."""
        with patch(_TASK_PATCH_PATH):
            response = auth_client.post(
                f"/api/v1/r4j/criminals/{published_criminal_simple.pk}/reports/",
                data={"notes": "این فرد در تهران دیده شده."},
                format="json",
            )

        assert response.status_code == status.HTTP_201_CREATED
        data = response.data["data"]
        assert data["status"] == ReportStatus.PENDING
        assert data["notes"] == "این فرد در تهران دیده شده."

    def test_submit_multiple_field_changes(
        self,
        auth_client: APIClient,
        published_criminal_simple,
    ) -> None:
        """چند field_change در یک گزارش باید همه ذخیره شوند."""
        with patch(_TASK_PATCH_PATH):
            response = auth_client.post(
                f"/api/v1/r4j/criminals/{published_criminal_simple.pk}/reports/",
                data={
                    "field_changes": [
                        {"field_name": "country", "suggested_value": "USA"},
                        {"field_name": "province", "suggested_value": "Texas"},
                        {"field_name": "city", "suggested_value": "Dallas"},
                    ],
                },
                format="json",
            )

        assert response.status_code == status.HTTP_201_CREATED
        assert len(response.data["data"]["field_changes"]) == 3

    def test_submit_creates_field_change_with_snapshot(
        self,
        auth_client: APIClient,
        published_criminal_simple,
    ) -> None:
        """snapshot مقدار فعلی فیلد باید در field_change ذخیره شود."""
        published_criminal_simple.city = "Tehran"
        published_criminal_simple.save(update_fields=["city", "updated_at"])

        with patch(_TASK_PATCH_PATH):
            auth_client.post(
                f"/api/v1/r4j/criminals/{published_criminal_simple.pk}/reports/",
                data={
                    "field_changes": [
                        {"field_name": "city", "suggested_value": "Mashhad"},
                    ],
                },
                format="json",
            )

        fc = R4JReportFieldChange.objects.filter(
            field_name="city",
            suggested_value="Mashhad",
        ).first()
        assert fc is not None
        assert fc.current_value_snapshot == "Tehran"
        assert fc.status == ReportFieldChangeStatus.PENDING

    def test_submit_dispatches_audit_log(
        self,
        auth_client: APIClient,
        regular_user,
        published_criminal_simple,
    ) -> None:
        """ارسال موفق گزارش باید audit log مناسب dispatch کند."""
        with patch(_TASK_PATCH_PATH) as mock_task:
            mock_task.delay = MagicMock()
            auth_client.post(
                f"/api/v1/r4j/criminals/{published_criminal_simple.pk}/reports/",
                data={
                    "field_changes": [
                        {"field_name": "city", "suggested_value": "Tehran"},
                    ],
                },
                format="json",
            )

        mock_task.delay.assert_called_once()
        kwargs = mock_task.delay.call_args.kwargs
        assert kwargs["action"] == audit_actions.R4J_REPORT_SUBMITTED
        assert kwargs["user_id"] == regular_user.pk

    def test_submit_report_saved_to_db(
        self,
        auth_client: APIClient,
        regular_user,
        published_criminal_simple,
    ) -> None:
        """گزارش ارسال‌شده باید در DB ذخیره شده باشد."""
        with patch(_TASK_PATCH_PATH):
            auth_client.post(
                f"/api/v1/r4j/criminals/{published_criminal_simple.pk}/reports/",
                data={"notes": "تست ذخیره"},
                format="json",
            )

        assert R4JReport.objects.filter(
            submitted_by=regular_user,
            criminal=published_criminal_simple,
        ).exists()

    def test_submit_response_includes_criminal_name(
        self,
        auth_client: APIClient,
        published_criminal,
    ) -> None:
        """پاسخ باید نام مجرم را شامل شود."""
        with patch(_TASK_PATCH_PATH):
            response = auth_client.post(
                f"/api/v1/r4j/criminals/{published_criminal.pk}/reports/",
                data={"notes": "تست نام"},
                format="json",
            )

        assert response.status_code == status.HTTP_201_CREATED
        assert "Donald" in response.data["data"]["criminal_name"]
        assert "Trump" in response.data["data"]["criminal_name"]


# ============================================================
# Submit Report — Attachment Flow
# ============================================================


class TestReportSubmitWithAttachments:
    """
    تست end-to-end آپلود فایل ضمیمه در گزارش.

    دو حالت تست می‌شود:
    1. multipart: فایل + JSON string برای field_changes
    2. تأیید ذخیره‌شدن در DB
    3. نمایش در response
    4. چند فایل همزمان
    5. بدون فایل — اختیاری بودن attachment
    """

    def test_submit_with_single_attachment_multipart(
        self,
        auth_client: APIClient,
        published_criminal_simple,
    ) -> None:
        """ارسال گزارش با یک فایل ضمیمه در multipart باید 201 برگرداند."""
        pdf = _make_minimal_pdf()

        with patch(_TASK_PATCH_PATH):
            response = auth_client.post(
                f"/api/v1/r4j/criminals/{published_criminal_simple.pk}/reports/",
                data={
                    "notes": "گزارش با ضمیمه",
                    "attachments": pdf,
                },
                format="multipart",
            )

        assert response.status_code == status.HTTP_201_CREATED
        data = response.data["data"]
        assert data["status"] == ReportStatus.PENDING
        assert len(data["attachments"]) == 1

    def test_submit_attachment_saved_to_db(
        self,
        auth_client: APIClient,
        regular_user,
        published_criminal_simple,
    ) -> None:
        """فایل ضمیمه باید در DB ذخیره شود."""
        pdf = _make_minimal_pdf()

        with patch(_TASK_PATCH_PATH):
            response = auth_client.post(
                f"/api/v1/r4j/criminals/{published_criminal_simple.pk}/reports/",
                data={
                    "notes": "تست ذخیره ضمیمه",
                    "attachments": pdf,
                },
                format="multipart",
            )

        assert response.status_code == status.HTTP_201_CREATED
        report_id = response.data["data"]["id"]
        assert R4JReportAttachment.objects.filter(report_id=report_id).count() == 1

    def test_submit_with_multiple_attachments(
        self,
        auth_client: APIClient,
        published_criminal_simple,
    ) -> None:
        """ارسال چند فایل ضمیمه در یک گزارش باید همه ذخیره شوند."""
        pdf1 = _make_minimal_pdf()
        pdf2 = SimpleUploadedFile(
            name="second.pdf",
            content=b"%PDF-1.4 second",
            content_type="application/pdf",
        )

        with patch(_TASK_PATCH_PATH):
            response = auth_client.post(
                f"/api/v1/r4j/criminals/{published_criminal_simple.pk}/reports/",
                data={
                    "notes": "گزارش با چند ضمیمه",
                    "attachments": [pdf1, pdf2],
                },
                format="multipart",
            )

        assert response.status_code == status.HTTP_201_CREATED
        report_id = response.data["data"]["id"]
        assert R4JReportAttachment.objects.filter(report_id=report_id).count() == 2
        assert len(response.data["data"]["attachments"]) == 2

    def test_submit_multipart_with_field_changes_as_json_string(
        self,
        auth_client: APIClient,
        published_criminal_simple,
    ) -> None:
        """در multipart، field_changes به‌صورت JSON string باید درست parse شود."""
        pdf = _make_minimal_pdf()
        field_changes_json = json.dumps(
            [
                {"field_name": "city", "suggested_value": "Shiraz"},
            ]
        )

        with patch(_TASK_PATCH_PATH):
            response = auth_client.post(
                f"/api/v1/r4j/criminals/{published_criminal_simple.pk}/reports/",
                data={
                    "field_changes": field_changes_json,
                    "attachments": pdf,
                },
                format="multipart",
            )

        assert response.status_code == status.HTTP_201_CREATED
        data = response.data["data"]
        assert len(data["field_changes"]) == 1
        assert data["field_changes"][0]["field_name"] == "city"
        assert len(data["attachments"]) == 1

    def test_submit_multipart_field_changes_and_notes_and_attachments(
        self,
        auth_client: APIClient,
        published_criminal_simple,
    ) -> None:
        """ارسال هر سه: notes + field_changes + attachments در multipart."""
        pdf = _make_minimal_pdf()
        field_changes_json = json.dumps(
            [
                {"field_name": "country", "suggested_value": "Germany"},
            ]
        )

        with patch(_TASK_PATCH_PATH):
            response = auth_client.post(
                f"/api/v1/r4j/criminals/{published_criminal_simple.pk}/reports/",
                data={
                    "notes": "یادداشت کامل",
                    "field_changes": field_changes_json,
                    "attachments": pdf,
                },
                format="multipart",
            )

        assert response.status_code == status.HTTP_201_CREATED
        data = response.data["data"]
        assert data["notes"] == "یادداشت کامل"
        assert len(data["field_changes"]) == 1
        assert len(data["attachments"]) == 1

    def test_submit_without_attachment_is_still_valid(
        self,
        auth_client: APIClient,
        published_criminal_simple,
    ) -> None:
        """attachment اختیاری است — گزارش بدون فایل هم باید قبول شود."""
        with patch(_TASK_PATCH_PATH):
            response = auth_client.post(
                f"/api/v1/r4j/criminals/{published_criminal_simple.pk}/reports/",
                data={"notes": "گزارش بدون فایل"},
                format="json",
            )

        assert response.status_code == status.HTTP_201_CREATED
        assert response.data["data"]["attachments"] == []

    def test_submit_audit_log_includes_attachment_count(
        self,
        auth_client: APIClient,
        regular_user,
        published_criminal_simple,
    ) -> None:
        """audit log باید تعداد فایل‌های ضمیمه را شامل شود."""
        pdf = _make_minimal_pdf()

        with patch(_TASK_PATCH_PATH) as mock_task:
            mock_task.delay = MagicMock()
            auth_client.post(
                f"/api/v1/r4j/criminals/{published_criminal_simple.pk}/reports/",
                data={
                    "notes": "گزارش با فایل",
                    "attachments": pdf,
                },
                format="multipart",
            )

        mock_task.delay.assert_called_once()
        kwargs = mock_task.delay.call_args.kwargs
        assert kwargs["action"] == audit_actions.R4J_REPORT_SUBMITTED
        assert kwargs["extra_data"]["attachment_count"] == 1

    def test_multipart_invalid_field_changes_json_returns_400(
        self,
        auth_client: APIClient,
        published_criminal_simple,
    ) -> None:
        """JSON string نامعتبر برای field_changes باید 400 برگرداند."""
        response = auth_client.post(
            f"/api/v1/r4j/criminals/{published_criminal_simple.pk}/reports/",
            data={
                "field_changes": "این یک JSON نامعتبر است {{{",
            },
            format="multipart",
        )
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_multipart_invalid_field_name_in_json_string_returns_400(
        self,
        auth_client: APIClient,
        published_criminal_simple,
    ) -> None:
        """field_name نامعتبر در JSON string باید 400 برگرداند."""
        field_changes_json = json.dumps(
            [
                {"field_name": "total_bounty_toman", "suggested_value": "99999"},
            ]
        )

        response = auth_client.post(
            f"/api/v1/r4j/criminals/{published_criminal_simple.pk}/reports/",
            data={
                "field_changes": field_changes_json,
            },
            format="multipart",
        )
        assert response.status_code == status.HTTP_400_BAD_REQUEST


# ============================================================
# Submit Report — Failure Cases
# ============================================================


class TestReportSubmitFailures:
    """تست سناریوهای خطا در submit."""

    def test_anonymous_cannot_submit(
        self,
        api_client: APIClient,
        published_criminal_simple,
    ) -> None:
        """کاربر لاگین نکرده نباید بتواند گزارش ارسال کند."""
        response = api_client.post(
            f"/api/v1/r4j/criminals/{published_criminal_simple.pk}/reports/",
            data={"notes": "test"},
            format="json",
        )
        assert response.status_code in {
            status.HTTP_401_UNAUTHORIZED,
            status.HTTP_403_FORBIDDEN,
        }

    def test_empty_report_returns_400(
        self,
        auth_client: APIClient,
        published_criminal_simple,
    ) -> None:
        """گزارش کاملاً خالی (نه notes، نه field_changes) نباید قبول شود."""
        response = auth_client.post(
            f"/api/v1/r4j/criminals/{published_criminal_simple.pk}/reports/",
            data={},
            format="json",
        )
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_empty_notes_and_no_field_changes_returns_400(
        self,
        auth_client: APIClient,
        published_criminal_simple,
    ) -> None:
        """notes خالی + field_changes خالی نباید قبول شود."""
        response = auth_client.post(
            f"/api/v1/r4j/criminals/{published_criminal_simple.pk}/reports/",
            data={"notes": "", "field_changes": []},
            format="json",
        )
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_invalid_field_name_returns_400(
        self,
        auth_client: APIClient,
        published_criminal_simple,
    ) -> None:
        """field_name غیر مجاز (مثل total_bounty_toman) باید رد شود."""
        response = auth_client.post(
            f"/api/v1/r4j/criminals/{published_criminal_simple.pk}/reports/",
            data={
                "field_changes": [
                    {
                        "field_name": "total_bounty_toman",
                        "suggested_value": "999999",
                    },
                ],
            },
            format="json",
        )
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_is_published_field_not_reportable(
        self,
        auth_client: APIClient,
        published_criminal_simple,
    ) -> None:
        """تلاش برای گزارش فیلد is_published باید رد شود."""
        response = auth_client.post(
            f"/api/v1/r4j/criminals/{published_criminal_simple.pk}/reports/",
            data={
                "field_changes": [
                    {"field_name": "is_published", "suggested_value": "true"},
                ],
            },
            format="json",
        )
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_nonexistent_criminal_returns_404(
        self,
        auth_client: APIClient,
    ) -> None:
        """مجرم با id نامعتبر باید 404 برگرداند."""
        response = auth_client.post(
            "/api/v1/r4j/criminals/99999/reports/",
            data={"notes": "test"},
            format="json",
        )
        assert response.status_code == status.HTTP_404_NOT_FOUND

    def test_draft_criminal_returns_404(
        self,
        auth_client: APIClient,
        db,
    ) -> None:
        """مجرم draft (منتشر نشده) نباید قابل گزارش باشد."""
        draft = R4JCriminalFactory(is_published=False)
        response = auth_client.post(
            f"/api/v1/r4j/criminals/{draft.pk}/reports/",
            data={"notes": "test"},
            format="json",
        )
        assert response.status_code == status.HTTP_404_NOT_FOUND

    def test_soft_deleted_criminal_returns_404(
        self,
        auth_client: APIClient,
        db,
    ) -> None:
        """مجرم soft-deleted نباید قابل گزارش باشد."""
        criminal = R4JCriminalFactory()
        criminal.publish()
        criminal.soft_delete()

        response = auth_client.post(
            f"/api/v1/r4j/criminals/{criminal.pk}/reports/",
            data={"notes": "test"},
            format="json",
        )
        assert response.status_code == status.HTTP_404_NOT_FOUND


# ============================================================
# My Reports — List
# ============================================================


class TestUserMyReportsList:
    """لیست گزارشات کاربر جاری — scope isolation و filter."""

    def test_user_sees_only_own_reports(
        self,
        auth_client: APIClient,
        regular_user,
        db,
    ) -> None:
        """کاربر فقط گزارشات خودش را می‌بیند، نه گزارشات دیگران."""
        criminal = R4JCriminalFactory()
        other_user = UserFactory(email="other@example.com")

        R4JReportFactory(criminal=criminal, submitted_by=regular_user)
        R4JReportFactory(criminal=criminal, submitted_by=other_user)

        response = auth_client.get("/api/v1/r4j/me/reports/")

        assert response.status_code == status.HTTP_200_OK
        results = response.data["data"]["results"]
        assert len(results) == 1

    def test_anonymous_cannot_list(
        self,
        api_client: APIClient,
    ) -> None:
        """کاربر لاگین نکرده نباید به لیست گزارشات دسترسی داشته باشد."""
        response = api_client.get("/api/v1/r4j/me/reports/")
        assert response.status_code in {
            status.HTTP_401_UNAUTHORIZED,
            status.HTTP_403_FORBIDDEN,
        }

    def test_filter_by_status_pending(
        self,
        auth_client: APIClient,
        regular_user,
        db,
    ) -> None:
        """فیلتر status=pending فقط گزارشات pending را برگرداند."""
        criminal = R4JCriminalFactory()
        R4JReportFactory(
            criminal=criminal,
            submitted_by=regular_user,
            status=ReportStatus.PENDING,
        )
        R4JReportFactory(
            criminal=criminal,
            submitted_by=regular_user,
            status=ReportStatus.APPROVED,
        )

        response = auth_client.get("/api/v1/r4j/me/reports/?status=pending")

        assert response.status_code == status.HTTP_200_OK
        results = response.data["data"]["results"]
        assert len(results) == 1
        assert results[0]["status"] == ReportStatus.PENDING

    def test_filter_by_status_approved(
        self,
        auth_client: APIClient,
        regular_user,
        db,
    ) -> None:
        """فیلتر status=approved فقط گزارشات approved را برگرداند."""
        criminal = R4JCriminalFactory()
        R4JReportFactory(
            criminal=criminal,
            submitted_by=regular_user,
            status=ReportStatus.APPROVED,
        )
        R4JReportFactory(
            criminal=criminal,
            submitted_by=regular_user,
            status=ReportStatus.PENDING,
        )

        response = auth_client.get("/api/v1/r4j/me/reports/?status=approved")

        assert response.status_code == status.HTTP_200_OK
        results = response.data["data"]["results"]
        assert all(r["status"] == ReportStatus.APPROVED for r in results)

    def test_empty_list_when_no_reports(
        self,
        auth_client: APIClient,
        regular_user,
        db,
    ) -> None:
        """اگر کاربر هیچ گزارشی نفرستاده، لیست خالی برگردد."""
        response = auth_client.get("/api/v1/r4j/me/reports/")

        assert response.status_code == status.HTTP_200_OK
        assert response.data["data"]["count"] == 0

    def test_list_response_includes_criminal_name(
        self,
        auth_client: APIClient,
        regular_user,
        published_criminal,
    ) -> None:
        """لیست گزارشات باید نام مجرم را در هر آیتم شامل شود."""
        R4JReportFactory(
            criminal=published_criminal,
            submitted_by=regular_user,
        )

        response = auth_client.get("/api/v1/r4j/me/reports/")

        assert response.status_code == status.HTTP_200_OK
        result = response.data["data"]["results"][0]
        assert "criminal_name" in result
        assert "Donald" in result["criminal_name"]


# ============================================================
# My Reports — Detail (با IDOR protection)
# ============================================================


class TestUserMyReportDetail:
    """جزئیات گزارش کاربر — شامل IDOR protection exhaustive."""

    def test_user_can_retrieve_own_report(
        self,
        auth_client: APIClient,
        regular_user,
        db,
    ) -> None:
        """کاربر باید بتواند گزارش خودش را دریافت کند."""
        criminal = R4JCriminalFactory()
        report = R4JReportFactory(criminal=criminal, submitted_by=regular_user)

        response = auth_client.get(f"/api/v1/r4j/me/reports/{report.pk}/")

        assert response.status_code == status.HTTP_200_OK
        assert response.data["data"]["id"] == report.pk

    def test_user_cannot_access_other_users_report(
        self,
        auth_client: APIClient,
        db,
    ) -> None:
        """IDOR protection: کاربر نباید گزارش دیگران را ببیند."""
        other_user = UserFactory(email="victim@example.com")
        criminal = R4JCriminalFactory()
        other_report = R4JReportFactory(
            criminal=criminal,
            submitted_by=other_user,
        )

        response = auth_client.get(f"/api/v1/r4j/me/reports/{other_report.pk}/")

        assert response.status_code == status.HTTP_404_NOT_FOUND

    def test_nonexistent_report_returns_404(
        self,
        auth_client: APIClient,
    ) -> None:
        """شناسه نامعتبر گزارش باید 404 برگرداند."""
        response = auth_client.get("/api/v1/r4j/me/reports/99999/")
        assert response.status_code == status.HTTP_404_NOT_FOUND

    def test_report_detail_includes_field_changes(
        self,
        auth_client: APIClient,
        regular_user,
        db,
    ) -> None:
        """جزئیات گزارش باید field_changes را شامل شود."""
        criminal = R4JCriminalFactory()
        report = R4JReportFactory(criminal=criminal, submitted_by=regular_user)
        R4JReportFieldChangeFactory(report=report, field_name="country")
        R4JReportFieldChangeFactory(report=report, field_name="city")

        response = auth_client.get(f"/api/v1/r4j/me/reports/{report.pk}/")

        assert response.status_code == status.HTTP_200_OK
        assert len(response.data["data"]["field_changes"]) == 2

    def test_report_detail_shows_admin_note_after_review(
        self,
        auth_client: APIClient,
        regular_user,
        db,
    ) -> None:
        """بعد از review، کاربر باید admin_note را ببیند."""
        criminal = R4JCriminalFactory()
        report = R4JReportFactory(
            criminal=criminal,
            submitted_by=regular_user,
            status=ReportStatus.REJECTED,
            admin_note="اطلاعات کافی نیست.",
        )

        response = auth_client.get(f"/api/v1/r4j/me/reports/{report.pk}/")

        assert response.status_code == status.HTTP_200_OK
        assert response.data["data"]["admin_note"] == "اطلاعات کافی نیست."

    def test_anonymous_cannot_retrieve(
        self,
        api_client: APIClient,
        db,
    ) -> None:
        """کاربر لاگین نکرده نباید به جزئیات گزارش دسترسی داشته باشد."""
        report = R4JReportFactory()
        response = api_client.get(f"/api/v1/r4j/me/reports/{report.pk}/")
        assert response.status_code in {
            status.HTTP_401_UNAUTHORIZED,
            status.HTTP_403_FORBIDDEN,
        }


# ============================================================
# Cancel Request — State Machine Exhaustive
# ============================================================


class TestReportCancelRequest:
    """state machine cancel request توسط کاربر — exhaustive coverage."""

    def test_pending_report_can_be_cancel_requested(
        self,
        auth_client: APIClient,
        regular_user,
        db,
    ) -> None:
        """گزارش PENDING باید قابل درخواست لغو باشد."""
        criminal = R4JCriminalFactory()
        report = R4JReportFactory(
            criminal=criminal,
            submitted_by=regular_user,
            status=ReportStatus.PENDING,
        )

        with patch(_TASK_PATCH_PATH) as mock_task:
            mock_task.delay = MagicMock()
            response = auth_client.post(
                f"/api/v1/r4j/me/reports/{report.pk}/cancel/",
            )

        assert response.status_code == status.HTTP_200_OK
        assert response.data["data"]["status"] == ReportStatus.CANCEL_REQUESTED

        report.refresh_from_db()
        assert report.status == ReportStatus.CANCEL_REQUESTED
        assert report.cancel_requested_at is not None

    def test_cancel_request_dispatches_audit(
        self,
        auth_client: APIClient,
        regular_user,
        db,
    ) -> None:
        """درخواست لغو موفق باید audit log مناسب dispatch کند."""
        criminal = R4JCriminalFactory()
        report = R4JReportFactory(
            criminal=criminal,
            submitted_by=regular_user,
            status=ReportStatus.PENDING,
        )

        with patch(_TASK_PATCH_PATH) as mock_task:
            mock_task.delay = MagicMock()
            auth_client.post(f"/api/v1/r4j/me/reports/{report.pk}/cancel/")

        mock_task.delay.assert_called_once()
        kwargs = mock_task.delay.call_args.kwargs
        assert kwargs["action"] == audit_actions.R4J_REPORT_CANCEL_REQUESTED
        assert kwargs["user_id"] == regular_user.pk

    def test_approved_report_cannot_be_canceled(
        self,
        auth_client: APIClient,
        regular_user,
        db,
    ) -> None:
        """گزارش APPROVED نباید قابل cancel باشد."""
        criminal = R4JCriminalFactory()
        report = R4JReportFactory(
            criminal=criminal,
            submitted_by=regular_user,
            status=ReportStatus.APPROVED,
        )

        response = auth_client.post(
            f"/api/v1/r4j/me/reports/{report.pk}/cancel/",
        )
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_rejected_report_cannot_be_canceled(
        self,
        auth_client: APIClient,
        regular_user,
        db,
    ) -> None:
        """گزارش REJECTED نباید قابل cancel باشد."""
        criminal = R4JCriminalFactory()
        report = R4JReportFactory(
            criminal=criminal,
            submitted_by=regular_user,
            status=ReportStatus.REJECTED,
        )

        response = auth_client.post(
            f"/api/v1/r4j/me/reports/{report.pk}/cancel/",
        )
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_partially_approved_report_cannot_be_canceled(
        self,
        auth_client: APIClient,
        regular_user,
        db,
    ) -> None:
        """گزارش PARTIALLY_APPROVED نباید قابل cancel باشد."""
        criminal = R4JCriminalFactory()
        report = R4JReportFactory(
            criminal=criminal,
            submitted_by=regular_user,
            status=ReportStatus.PARTIALLY_APPROVED,
        )

        response = auth_client.post(
            f"/api/v1/r4j/me/reports/{report.pk}/cancel/",
        )
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_canceled_report_cannot_be_canceled_again(
        self,
        auth_client: APIClient,
        regular_user,
        db,
    ) -> None:
        """گزارش CANCELED نباید قابل cancel مجدد باشد."""
        criminal = R4JCriminalFactory()
        report = R4JReportFactory(
            criminal=criminal,
            submitted_by=regular_user,
            status=ReportStatus.CANCELED,
        )

        response = auth_client.post(
            f"/api/v1/r4j/me/reports/{report.pk}/cancel/",
        )
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_already_cancel_requested_cannot_cancel_again(
        self,
        auth_client: APIClient,
        regular_user,
        db,
    ) -> None:
        """گزارش CANCEL_REQUESTED نباید قابل cancel مجدد باشد."""
        criminal = R4JCriminalFactory()
        report = R4JReportFactory(
            criminal=criminal,
            submitted_by=regular_user,
            status=ReportStatus.CANCEL_REQUESTED,
        )

        response = auth_client.post(
            f"/api/v1/r4j/me/reports/{report.pk}/cancel/",
        )
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_user_cannot_cancel_other_users_report(
        self,
        auth_client: APIClient,
        db,
    ) -> None:
        """IDOR: کاربر نباید بتواند گزارش دیگران را cancel کند."""
        other_user = UserFactory(email="victim2@example.com")
        criminal = R4JCriminalFactory()
        report = R4JReportFactory(
            criminal=criminal,
            submitted_by=other_user,
            status=ReportStatus.PENDING,
        )

        response = auth_client.post(
            f"/api/v1/r4j/me/reports/{report.pk}/cancel/",
        )
        assert response.status_code == status.HTTP_404_NOT_FOUND

    def test_anonymous_cannot_cancel(
        self,
        api_client: APIClient,
        db,
    ) -> None:
        """کاربر لاگین نکرده نباید بتواند cancel کند."""
        report = R4JReportFactory(status=ReportStatus.PENDING)

        response = api_client.post(
            f"/api/v1/r4j/me/reports/{report.pk}/cancel/",
        )
        assert response.status_code in {
            status.HTTP_401_UNAUTHORIZED,
            status.HTTP_403_FORBIDDEN,
        }

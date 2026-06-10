"""
R4J performance and visibility contract tests.

Phase 8 هدفش جلوگیری از برگشت N+1 و تثبیت قراردادهای query layer است. این
تست‌ها روی selector + serializer تمرکز می‌کنند تا مطمئن شویم داده‌های nested
قبل از serialization prefetch/select شده‌اند و رندر پاسخ‌های پرترافیک با تعداد
query ثابت انجام می‌شود.
"""

from __future__ import annotations

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import connection
from django.test.utils import CaptureQueriesContext

from apps.r4j import selectors
from apps.r4j.choices import CriminalAttachmentKind, SocialPlatform
from apps.r4j.models import (
    R4JCriminalAlias,
    R4JCriminalAttachment,
    R4JCriminalFieldVisibility,
    R4JCriminalPhone,
    R4JCriminalPhoto,
    R4JCriminalSocial,
)
from apps.r4j.serializers import (
    R4JAdminReportListSerializer,
    R4JPublicCriminalDetailSerializer,
    R4JPublicCriminalListSerializer,
    R4JUserReportDetailSerializer,
)
from tests.factories.r4j import (
    R4JCriminalPublishedFactory,
    R4JReportAttachmentFactory,
    R4JReportFactory,
    R4JReportFieldChangeFactory,
)

pytestmark = pytest.mark.django_db


def _image_file(name: str) -> SimpleUploadedFile:
    """ساخت فایل تصویر minimal برای مدل‌های R4J."""
    return SimpleUploadedFile(name, b"image-content", content_type="image/png")


def _pdf_file(name: str) -> SimpleUploadedFile:
    """ساخت فایل PDF minimal برای attachmentهای R4J."""
    return SimpleUploadedFile(name, b"%PDF-1.4 minimal", content_type="application/pdf")


class TestR4JPublicCriminalQueryContracts:
    """تست‌های query contract برای public criminal endpoints."""

    def test_public_criminal_list_serializer_does_not_query_after_prefetch(self) -> None:
        for index in range(3):
            criminal = R4JCriminalPublishedFactory(first_name=f"Public{index}")
            R4JCriminalPhoto.objects.create(
                criminal=criminal,
                image=_image_file(f"criminal-{index}.png"),
                is_primary=True,
            )

        criminals = list(selectors.get_public_criminals_queryset())

        with CaptureQueriesContext(connection) as captured:
            data = R4JPublicCriminalListSerializer(criminals, many=True).data

        assert len(data) == 3
        assert len(captured) == 0

    def test_public_criminal_detail_serializer_does_not_query_after_prefetch(self) -> None:
        criminal = R4JCriminalPublishedFactory(national_code="0123456789")
        R4JCriminalPhoto.objects.create(criminal=criminal, image=_image_file("photo.png"))
        R4JCriminalPhone.objects.create(criminal=criminal, number="+989120000000", is_public=True)
        R4JCriminalSocial.objects.create(
            criminal=criminal,
            platform=SocialPlatform.TELEGRAM,
            handle_or_url="@criminal",
            is_public=True,
        )
        R4JCriminalAttachment.objects.create(
            criminal=criminal,
            file=_pdf_file("doc.pdf"),
            kind=CriminalAttachmentKind.DOCUMENT,
            title="doc",
            is_public=True,
        )
        R4JCriminalAlias.objects.create(criminal=criminal, alias="Alias One")
        R4JCriminalFieldVisibility.objects.create(
            criminal=criminal,
            field_name="national_code",
            is_public=False,
        )

        prefetched = selectors.get_public_criminal_detail(lookup=criminal.pk)

        with CaptureQueriesContext(connection) as captured:
            data = R4JPublicCriminalDetailSerializer(prefetched).data

        assert data["national_code"] is None
        assert len(data["phones"]) == 1
        assert len(data["socials"]) == 1
        assert len(data["attachments"]) == 1
        assert len(captured) == 0


class TestR4JReportQueryContracts:
    """تست‌های query contract برای گزارش‌های user/admin."""

    def test_user_report_detail_serializer_does_not_query_after_prefetch(self) -> None:
        report = R4JReportFactory()
        R4JReportFieldChangeFactory(report=report, field_name="city")
        R4JReportAttachmentFactory(report=report)

        prefetched = selectors.get_user_report_by_id(
            user_id=report.submitted_by_id,
            report_id=report.pk,
        )

        with CaptureQueriesContext(connection) as captured:
            data = R4JUserReportDetailSerializer(prefetched).data

        assert data["id"] == report.pk
        assert len(data["field_changes"]) == 1
        assert len(data["attachments"]) == 1
        assert len(captured) == 0

    def test_admin_report_list_serializer_does_not_query_after_select_related(self) -> None:
        reports = []
        for index in range(3):
            report = R4JReportFactory(notes=f"report {index}")
            R4JReportFieldChangeFactory(report=report)
            reports.append(report)

        prefetched_reports = list(selectors.get_admin_reports_queryset())

        with CaptureQueriesContext(connection) as captured:
            data = R4JAdminReportListSerializer(prefetched_reports, many=True).data

        assert len(data) >= len(reports)
        assert len(captured) == 0

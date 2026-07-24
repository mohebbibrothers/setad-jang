"""Django admin UX tests for public reports.

Report attachments are documentary evidence. They should be reviewed in the
context of their report, hidden from the top-level admin index, and protected
from direct mutation.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest
from django.contrib import admin
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse

from apps.public_reports.admin import ReportAttachmentInline
from apps.public_reports.choices import ReportStatus
from apps.public_reports.models import Report, ReportAttachment, ReportSubject
from tests.factories import AdminUserFactory
from tests.factories.public_reports import ReportFactory

pytestmark = pytest.mark.django_db


def _image(name: str = "evidence.png") -> SimpleUploadedFile:
    return SimpleUploadedFile(name, b"\x89PNG\r\n\x1a\nminimal", content_type="image/png")


class TestPublicReportsDjangoAdminUX:
    """Public reports admin should be a clean, service-backed review workspace."""

    def test_report_attachments_are_inline_and_hidden_from_admin_index(self, rf):
        request = rf.get("/admin/")
        request.user = AdminUserFactory()

        report_admin = admin.site._registry[Report]
        attachment_admin = admin.site._registry[ReportAttachment]

        assert report_admin.inlines == [ReportAttachmentInline]
        assert attachment_admin.get_model_perms(request) == {}

    def test_subject_and_report_workspaces_remain_visible(self, rf):
        request = rf.get("/admin/")
        request.user = AdminUserFactory()

        assert admin.site._registry[ReportSubject].get_model_perms(request)
        assert admin.site._registry[Report].get_model_perms(request)

    def test_admin_index_hides_attachments_but_keeps_report_workspaces(self, client):
        admin_user = AdminUserFactory()
        client.force_login(admin_user)

        response = client.get(reverse("admin:index"))

        assert response.status_code == 200
        html = response.content.decode("utf-8")
        assert "مستندات گزارش‌ها" not in html
        assert "گزارش‌های مردمی" in html
        assert "موضوعات گزارش" in html

    def test_report_review_panel_is_rendered_for_pending_report(self, client):
        admin_user = AdminUserFactory()
        client.force_login(admin_user)
        report = ReportFactory(status=ReportStatus.PENDING)
        ReportAttachment.objects.create(report=report, image=_image())

        response = client.get(reverse("admin:public_reports_report_change", args=[report.pk]))

        assert response.status_code == 200
        html = response.content.decode("utf-8")
        assert "در حال بررسی" in html
        assert "تأیید گزارش" in html
        assert "رد گزارش" in html
        assert "public_report_admin_note" in html

    def test_report_admin_status_action_uses_service_and_audits(self, client):
        admin_user = AdminUserFactory()
        client.force_login(admin_user)
        report = ReportFactory(status=ReportStatus.PENDING)

        with patch("apps.public_reports.admin.log_action") as mock_log_action:
            response = client.post(
                reverse("admin:public_reports_report_change", args=[report.pk]),
                data={
                    "_public_report_approve": "1",
                    "public_report_admin_note": "مستندات کافی است.",
                },
                follow=True,
            )

        assert response.status_code == 200
        report.refresh_from_db()
        assert report.status == ReportStatus.APPROVED
        assert report.admin_note == "مستندات کافی است."
        mock_log_action.assert_called_once()
        assert mock_log_action.call_args.kwargs["changes"] == {
            "status": {"before": ReportStatus.PENDING, "after": ReportStatus.APPROVED}
        }

    def test_terminal_report_does_not_render_mutating_review_buttons(self, client):
        admin_user = AdminUserFactory()
        client.force_login(admin_user)
        report = ReportFactory(status=ReportStatus.APPROVED)

        response = client.get(reverse("admin:public_reports_report_change", args=[report.pk]))

        assert response.status_code == 200
        html = response.content.decode("utf-8")
        assert "این گزارش تعیین تکلیف شده است" in html
        assert "_public_report_approve" not in html

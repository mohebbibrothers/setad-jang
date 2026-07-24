"""Django admin UX tests for R4J.

The data model stays normalized, but daily admin workflows are consolidated:
- Criminal edit page owns direct profile resources.
- Report edit page owns report review, field-change decisions, and attachments.
- Top-level admin index stays focused on true queues/workspaces.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from django.contrib import admin
from django.urls import reverse

from apps.r4j.admin import (
    R4JCriminalAliasInline,
    R4JCriminalAttachmentInline,
    R4JCriminalFieldVisibilityAdminForm,
    R4JCriminalFieldVisibilityInline,
    R4JCriminalPhoneInline,
    R4JCriminalPhotoInline,
    R4JCriminalSocialInline,
    R4JReportAliasSuggestionInline,
    R4JReportAttachmentInline,
    R4JReportFieldChangeInline,
    R4JReportPhoneSuggestionInline,
    R4JReportSocialSuggestionInline,
)
from apps.r4j.choices import (
    PublicVisibilityField,
    ReportFieldChangeStatus,
    ReportStatus,
    SocialPlatform,
)
from apps.r4j.models import (
    R4JBounty,
    R4JCriminal,
    R4JCriminalAttachment,
    R4JCriminalFieldVisibility,
    R4JEvidenceCustodyEvent,
    R4JReport,
    R4JReportAliasSuggestion,
    R4JReportAttachment,
    R4JReportFieldChange,
    R4JReportPhoneSuggestion,
    R4JReportSocialSuggestion,
)
from tests.factories.auth import AdminUserFactory
from tests.factories.r4j import R4JCriminalFactory, R4JReportFactory, R4JReportFieldChangeFactory

pytestmark = pytest.mark.django_db

_TASK_PATCH_PATH = "apps.audit_logs.tasks.create_audit_log_task"


class TestR4JDjangoAdminUX:
    """Admin index should be clean, while domain workspaces stay complete."""

    def test_criminal_admin_is_the_single_profile_workspace(self):
        criminal_admin = admin.site._registry[R4JCriminal]

        assert criminal_admin.inlines == [
            R4JCriminalAliasInline,
            R4JCriminalPhoneInline,
            R4JCriminalSocialInline,
            R4JCriminalPhotoInline,
            R4JCriminalAttachmentInline,
            R4JCriminalFieldVisibilityAdminForm,
    R4JCriminalFieldVisibilityInline,
        ]


    def test_field_visibility_admin_uses_persian_dropdown_instead_of_free_text(self):
        form = R4JCriminalFieldVisibilityAdminForm()

        field = form.fields["field_name"]
        choices = dict(field.choices)

        assert choices[PublicVisibilityField.NATIONAL_CODE] == "کد ملی"
        assert choices[PublicVisibilityField.BIRTH_DATE] == "تاریخ تولد"
        assert choices[PublicVisibilityField.CRIMES_SUMMARY] == "خلاصه جرائم"
        assert form.fields["is_public"].label == "در سایت نمایش داده شود؟"
        assert form.fields["is_active"].label == "این قانون فعال باشد؟"
        assert "تایپ فنی" in form.fields["field_name"].help_text

    def test_criminal_change_page_renders_field_visibility_dropdown_labels(self, client):
        admin_user = AdminUserFactory()
        client.force_login(admin_user)
        criminal = R4JCriminalFactory()

        response = client.get(reverse("admin:r4j_r4jcriminal_change", args=[criminal.pk]))

        assert response.status_code == 200
        html = response.content.decode("utf-8")
        assert "فیلد اطلاعاتی" in html
        assert "در سایت نمایش داده شود؟" in html
        assert "کد ملی" in html
        assert "خلاصه جرائم" in html

    def test_report_admin_is_the_single_report_review_workspace(self):
        report_admin = admin.site._registry[R4JReport]

        assert report_admin.inlines == [
            R4JReportFieldChangeInline,
            R4JReportAliasSuggestionInline,
            R4JReportPhoneSuggestionInline,
            R4JReportSocialSuggestionInline,
            R4JReportAttachmentInline,
        ]
        assert "review_decision_panel" in report_admin.readonly_fields

    def test_dependent_models_are_registered_but_hidden_from_admin_index(self, rf):
        request = rf.get("/admin/")
        request.user = AdminUserFactory()

        hidden_models = [
            R4JCriminalAttachment,
            R4JCriminalFieldVisibility,
            R4JReportFieldChange,
            R4JReportAttachment,
        ]
        for model in hidden_models:
            model_admin = admin.site._registry[model]
            assert model_admin.get_model_perms(request) == {}

    def test_independent_r4j_queues_remain_visible_in_admin_index(self, rf):
        request = rf.get("/admin/")
        request.user = AdminUserFactory()

        visible_models = [
            R4JCriminal,
            R4JReport,
            R4JBounty,
            R4JEvidenceCustodyEvent,
        ]
        for model in visible_models:
            model_admin = admin.site._registry[model]
            assert model_admin.get_model_perms(request)

    def test_admin_index_hides_dependent_submodels_but_keeps_core_r4j_queues(self, client):
        admin_user = AdminUserFactory()
        client.force_login(admin_user)

        response = client.get(reverse("admin:index"))

        assert response.status_code == 200
        html = response.content.decode("utf-8")

        assert "اسناد مجرمان" not in html
        assert "تنظیمات نمایش فیلدهای مجرمان" not in html
        assert "پیشنهادهای اصلاح فیلدهای گزارش" not in html
        assert "ضمائم گزارش‌های عدالت" not in html

        assert "مجرمان" in html
        assert "گزارش‌های عدالت" in html
        assert "جوایز عدالت" in html
        assert "رویدادهای زنجیره نگهداری شواهد" in html

    def test_report_review_panel_is_rendered_on_report_change_page(self, client):
        admin_user = AdminUserFactory()
        client.force_login(admin_user)
        report = R4JReportFactory(status=ReportStatus.PENDING)
        R4JReportFieldChangeFactory(
            report=report,
            field_name="city",
            current_value_snapshot="تهران",
            suggested_value="قم",
        )

        response = client.get(reverse("admin:r4j_r4jreport_change", args=[report.pk]))

        assert response.status_code == 200
        html = response.content.decode("utf-8")
        assert "ثبت بررسی از مسیر امن سرویس" in html
        assert "r4j_decision_" in html
        assert "services.review_report" in html

    def test_report_review_submit_uses_service_and_updates_criminal(self, client):
        admin_user = AdminUserFactory()
        client.force_login(admin_user)
        criminal = R4JCriminalFactory(city="تهران")
        report = R4JReportFactory(criminal=criminal, status=ReportStatus.PENDING)
        field_change = R4JReportFieldChangeFactory(
            report=report,
            field_name="city",
            current_value_snapshot="تهران",
            suggested_value="قم",
        )

        with patch(_TASK_PATCH_PATH) as mock_task:
            mock_task.delay = MagicMock()
            response = client.post(
                reverse("admin:r4j_r4jreport_change", args=[report.pk]),
                data={
                    "_r4j_review_report": "1",
                    f"r4j_decision_{field_change.pk}": ReportFieldChangeStatus.APPROVED,
                    f"r4j_note_{field_change.pk}": "مدرک کافی است.",
                    "r4j_report_admin_note": "بررسی شد.",
                },
                follow=True,
            )

        assert response.status_code == 200
        criminal.refresh_from_db()
        report.refresh_from_db()
        field_change.refresh_from_db()

        assert criminal.city == "قم"
        assert report.status == ReportStatus.APPROVED
        assert report.reviewed_by_id == admin_user.pk
        assert field_change.status == ReportFieldChangeStatus.APPROVED
        assert field_change.admin_note == "مدرک کافی است."
        mock_task.delay.assert_called_once()

    def test_report_review_requires_decision_for_every_field_change(self, client):
        admin_user = AdminUserFactory()
        client.force_login(admin_user)
        report = R4JReportFactory(status=ReportStatus.PENDING)
        field_change = R4JReportFieldChangeFactory(report=report, field_name="city")

        response = client.post(
            reverse("admin:r4j_r4jreport_change", args=[report.pk]),
            data={"_r4j_review_report": "1"},
            follow=True,
        )

        assert response.status_code == 200
        report.refresh_from_db()
        field_change.refresh_from_db()
        assert report.status == ReportStatus.PENDING
        assert field_change.status == ReportFieldChangeStatus.PENDING
        assert "برای همه پیشنهادهای اصلاح باید تصمیم" in response.content.decode("utf-8")


    def test_report_review_submit_applies_resource_suggestions(self, client):
        admin_user = AdminUserFactory()
        client.force_login(admin_user)
        criminal = R4JCriminalFactory(city="تهران")
        report = R4JReportFactory(criminal=criminal, status=ReportStatus.PENDING)
        alias = R4JReportAliasSuggestion.objects.create(report=report, alias="حاج علی")
        phone = R4JReportPhoneSuggestion.objects.create(report=report, label="واتساپ", number="+989121234567")
        social = R4JReportSocialSuggestion.objects.create(
            report=report,
            platform=SocialPlatform.TELEGRAM,
            handle_or_url="@hajali",
        )

        with patch(_TASK_PATCH_PATH) as mock_task:
            mock_task.delay = MagicMock()
            response = client.post(
                reverse("admin:r4j_r4jreport_change", args=[report.pk]),
                data={
                    "_r4j_review_report": "1",
                    f"r4j_alias_decision_{alias.pk}": ReportFieldChangeStatus.APPROVED,
                    f"r4j_phone_decision_{phone.pk}": ReportFieldChangeStatus.APPROVED,
                    f"r4j_social_decision_{social.pk}": ReportFieldChangeStatus.REJECTED,
                    "r4j_report_admin_note": "بررسی شد.",
                },
                follow=True,
            )

        assert response.status_code == 200
        report.refresh_from_db()
        alias.refresh_from_db()
        phone.refresh_from_db()
        social.refresh_from_db()

        assert report.status == ReportStatus.PARTIALLY_APPROVED
        assert alias.status == ReportFieldChangeStatus.APPROVED
        assert alias.applied_alias_id is not None
        assert phone.status == ReportFieldChangeStatus.APPROVED
        assert phone.applied_phone_id is not None
        assert social.status == ReportFieldChangeStatus.REJECTED
        assert social.applied_social_id is None
        mock_task.delay.assert_called_once()

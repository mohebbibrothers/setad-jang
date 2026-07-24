"""Django admin UX tests for R4J.

The data model stays normalized, but the daily admin workflow should be centered
on the Criminal edit page. Directly dependent profile resources are inlines and
hidden from the top-level admin index, while independent queues remain visible.
"""

from __future__ import annotations

import pytest
from django.contrib import admin
from django.urls import reverse

from apps.r4j.admin import (
    R4JCriminalAliasInline,
    R4JCriminalAttachmentInline,
    R4JCriminalFieldVisibilityInline,
    R4JCriminalPhoneInline,
    R4JCriminalPhotoInline,
    R4JCriminalSocialInline,
)
from apps.r4j.models import (
    R4JBounty,
    R4JCriminal,
    R4JCriminalAttachment,
    R4JCriminalFieldVisibility,
    R4JEvidenceCustodyEvent,
    R4JReport,
    R4JReportAttachment,
    R4JReportFieldChange,
)
from tests.factories.auth import AdminUserFactory

pytestmark = pytest.mark.django_db


class TestR4JDjangoAdminUX:
    """Admin index should be clean, while profile resources stay editable inline."""

    def test_criminal_admin_is_the_single_profile_workspace(self):
        criminal_admin = admin.site._registry[R4JCriminal]

        assert criminal_admin.inlines == [
            R4JCriminalAliasInline,
            R4JCriminalPhoneInline,
            R4JCriminalSocialInline,
            R4JCriminalPhotoInline,
            R4JCriminalAttachmentInline,
            R4JCriminalFieldVisibilityInline,
        ]

    def test_dependent_profile_models_are_registered_but_hidden_from_admin_index(self, rf):
        request = rf.get("/admin/")
        request.user = AdminUserFactory()

        hidden_models = [R4JCriminalAttachment, R4JCriminalFieldVisibility]
        for model in hidden_models:
            model_admin = admin.site._registry[model]
            assert model_admin.get_model_perms(request) == {}

    def test_independent_r4j_review_queues_remain_visible_in_admin_index(self, rf):
        request = rf.get("/admin/")
        request.user = AdminUserFactory()

        visible_models = [
            R4JCriminal,
            R4JReport,
            R4JReportFieldChange,
            R4JReportAttachment,
            R4JBounty,
            R4JEvidenceCustodyEvent,
        ]
        for model in visible_models:
            model_admin = admin.site._registry[model]
            assert model_admin.get_model_perms(request)

    def test_admin_index_hides_profile_submodels_but_keeps_core_r4j_queues(self, client):
        admin_user = AdminUserFactory()
        client.force_login(admin_user)

        response = client.get(reverse("admin:index"))

        assert response.status_code == 200
        html = response.content.decode("utf-8")

        assert "اسناد مجرمان" not in html
        assert "تنظیمات نمایش فیلدهای مجرمان" not in html

        assert "مجرمان" in html
        assert "گزارش‌های عدالت" in html
        assert "پیشنهادهای اصلاح فیلدهای گزارش" in html
        assert "ضمائم گزارش‌های عدالت" in html
        assert "جوایز عدالت" in html
        assert "رویدادهای زنجیره نگهداری شواهد" in html

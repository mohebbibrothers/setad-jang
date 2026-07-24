"""Django admin UX tests for Madadkar finance workspaces.

Madadkar is financially sensitive, so UX consolidation must not weaken the
normalized model or bypass service-layer workflows. These tests verify that
subordinate evidence models are visible in their parent workspace and hidden
from the top-level admin index.
"""

from __future__ import annotations

import pytest
from django.contrib import admin
from django.urls import reverse

from apps.madadkar.admin import PaymentEventInline, PaymentReconciliationItemInline
from apps.madadkar.models import (
    Campaign,
    CampaignImage,
    Payment,
    PaymentEvent,
    PaymentReconciliationBatch,
    PaymentReconciliationItem,
)
from tests.factories import AdminUserFactory

pytestmark = pytest.mark.django_db


class TestMadadkarDjangoAdminUX:
    """Madadkar admin should expose finance-safe workspaces without index noise."""

    def test_campaign_images_are_managed_inside_campaign_workspace(self, rf):
        request = rf.get("/admin/")
        request.user = AdminUserFactory()

        campaign_admin = admin.site._registry[Campaign]
        image_admin = admin.site._registry[CampaignImage]

        assert CampaignImage in [inline.model for inline in campaign_admin.inlines]
        assert image_admin.get_model_perms(request) == {}

    def test_payment_events_are_embedded_in_payment_workspace_and_hidden_from_index(self, rf):
        request = rf.get("/admin/")
        request.user = AdminUserFactory()

        payment_admin = admin.site._registry[Payment]
        event_admin = admin.site._registry[PaymentEvent]

        assert payment_admin.inlines == [PaymentEventInline]
        assert event_admin.get_model_perms(request) == {}

    def test_reconciliation_items_are_embedded_in_batch_workspace_and_hidden_from_index(self, rf):
        request = rf.get("/admin/")
        request.user = AdminUserFactory()

        batch_admin = admin.site._registry[PaymentReconciliationBatch]
        item_admin = admin.site._registry[PaymentReconciliationItem]

        assert batch_admin.inlines == [PaymentReconciliationItemInline]
        assert item_admin.get_model_perms(request) == {}

    def test_admin_index_hides_inline_only_models_but_keeps_finance_workspaces(self, client):
        admin_user = AdminUserFactory()
        client.force_login(admin_user)

        response = client.get(reverse("admin:index"))

        assert response.status_code == 200
        html = response.content.decode("utf-8")

        assert "تصاویر گالری حرکت‌ها" not in html
        assert "رویدادهای پرداخت" not in html
        assert "ردیف‌های تطبیق پرداخت" not in html

        assert "حرکت‌ها" in html
        assert "پرداخت‌ها" in html
        assert "دسته‌های تطبیق پرداخت" in html
        assert "بازپرداخت‌های مددکار" in html
        assert "تخصیص‌های مالی مددکار" in html
        assert "سیگنال‌های ریسک مددکار" in html

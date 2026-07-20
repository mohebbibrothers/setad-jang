"""Tests for Django admin custom display helpers in Madadkar."""

from __future__ import annotations

import pytest
from django.contrib.admin.sites import AdminSite

from apps.madadkar.admin import CampaignAdmin
from apps.madadkar.models import Campaign
from tests.factories.madadkar import CampaignFactory

pytestmark = pytest.mark.django_db


class TestCampaignDjangoAdmin:
    """Regression coverage for Django admin changelist display methods."""

    def test_progress_display_formats_numeric_percent_before_format_html(self):
        """Django's format_html escapes args before str.format, so no numeric format specs."""
        campaign = CampaignFactory(total_shares=1000)
        campaign.purchased_shares = 333
        admin = CampaignAdmin(Campaign, AdminSite())

        html = admin.progress_display(campaign)

        assert "33.3%" in str(html)
        assert "red" in str(html)

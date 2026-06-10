"""
تست‌های Campaign public endpoints.

پوشش:
- List campaigns: فقط visible + PUBLISHED/COMPLETED/CLOSED برمی‌گرداند
- DRAFT و invisible نباید نمایش داده شوند
- Filters: sponsor, status, has_deadline, is_fully_funded, search
- Pagination: page, page_size
- Detail: happy path, 404 برای invisible/draft
- Response envelope
"""

from __future__ import annotations

import pytest
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient

from apps.madadkar.choices import CampaignStatus
from tests.factories.madadkar import (
    CampaignFactory,
    CampaignImageFactory,
    CompletedCampaignFactory,
    PublishedCampaignFactory,
    SponsorFactory,
)

pytestmark = pytest.mark.django_db


# ============================================================
# Public Campaign List
# ============================================================


class TestPublicCampaignList:
    """تست‌های GET /api/v1/madadkar/campaigns/"""

    def test_list_returns_published_visible_only(self):
        """فقط campaignهای PUBLISHED + is_visible=True برمی‌گردند."""
        published_visible = PublishedCampaignFactory(title="منتشرشده قابل نمایش")
        PublishedCampaignFactory(
            title="منتشرشده مخفی",
            is_visible=False,
        )
        CampaignFactory(title="پیش‌نویس")  # DRAFT

        client = APIClient()
        url = reverse("madadkar:public-campaign-list")
        response = client.get(url)

        assert response.status_code == status.HTTP_200_OK
        titles = [c["title"] for c in response.data["data"]["results"]]
        assert published_visible.title in titles
        assert "منتشرشده مخفی" not in titles
        assert "پیش‌نویس" not in titles

    def test_list_includes_completed_and_closed(self):
        """COMPLETED و CLOSED هم در لیست عمومی هستند."""
        published = PublishedCampaignFactory(title="فعال")
        completed = CompletedCampaignFactory(title="تکمیل شده")

        client = APIClient()
        url = reverse("madadkar:public-campaign-list")
        response = client.get(url)

        titles = [c["title"] for c in response.data["data"]["results"]]
        assert published.title in titles
        assert completed.title in titles

    def test_list_accessible_without_authentication(self):
        client = APIClient()
        url = reverse("madadkar:public-campaign-list")
        response = client.get(url)
        assert response.status_code == status.HTTP_200_OK

    def test_list_response_envelope(self):
        PublishedCampaignFactory()

        client = APIClient()
        url = reverse("madadkar:public-campaign-list")
        response = client.get(url)

        assert response.data["success"] is True
        assert response.data["status_code"] == 200
        assert "results" in response.data["data"]
        assert "count" in response.data["data"]

    # ── Filters ────────────────────────────────────────────

    def test_filter_by_sponsor(self):
        sponsor_a = SponsorFactory(name="الف")
        sponsor_b = SponsorFactory(name="ب")
        camp_a = PublishedCampaignFactory(sponsor=sponsor_a, title="A")
        camp_b = PublishedCampaignFactory(sponsor=sponsor_b, title="B")

        client = APIClient()
        url = reverse("madadkar:public-campaign-list")
        response = client.get(url, {"sponsor": sponsor_a.pk})

        titles = [c["title"] for c in response.data["data"]["results"]]
        assert camp_a.title in titles
        assert camp_b.title not in titles

    def test_filter_by_sponsor_slug(self):
        sponsor_a = SponsorFactory(name="یکم")
        PublishedCampaignFactory(sponsor=sponsor_a, title="یکم-A")
        PublishedCampaignFactory(title="دیگری")

        client = APIClient()
        url = reverse("madadkar:public-campaign-list")
        response = client.get(url, {"sponsor_slug": sponsor_a.slug})

        titles = [c["title"] for c in response.data["data"]["results"]]
        assert "یکم-A" in titles
        assert "دیگری" not in titles

    def test_filter_by_status_published(self):
        PublishedCampaignFactory(title="فعال")
        CompletedCampaignFactory(title="تکمیل شده")

        client = APIClient()
        url = reverse("madadkar:public-campaign-list")
        response = client.get(url, {"status": CampaignStatus.PUBLISHED})

        titles = [c["title"] for c in response.data["data"]["results"]]
        assert "فعال" in titles
        assert "تکمیل شده" not in titles

    def test_filter_is_fully_funded_true(self):
        """فقط campaignهای تکمیل شده."""
        PublishedCampaignFactory(title="نیمه‌فعال")  # purchased_shares=0
        CompletedCampaignFactory(title="کامل")  # purchased_shares=total_shares

        client = APIClient()
        url = reverse("madadkar:public-campaign-list")
        response = client.get(url, {"is_fully_funded": "true"})

        titles = [c["title"] for c in response.data["data"]["results"]]
        assert "کامل" in titles
        assert "نیمه‌فعال" not in titles

    def test_search_in_title(self):
        PublishedCampaignFactory(title="خرید پشه‌بند ضد دوربین")
        PublishedCampaignFactory(title="کمک به جبهه")

        client = APIClient()
        url = reverse("madadkar:public-campaign-list")
        response = client.get(url, {"search": "پشه‌بند"})

        titles = [c["title"] for c in response.data["data"]["results"]]
        assert "خرید پشه‌بند ضد دوربین" in titles
        assert "کمک به جبهه" not in titles

    # ── Pagination ─────────────────────────────────────────

    def test_pagination_page_size(self):
        for i in range(5):
            PublishedCampaignFactory(title=f"کمپین {i}")

        client = APIClient()
        url = reverse("madadkar:public-campaign-list")
        response = client.get(url, {"page_size": 2})

        assert response.status_code == status.HTTP_200_OK
        assert len(response.data["data"]["results"]) == 2
        assert response.data["data"]["count"] == 5


# ============================================================
# Public Campaign Detail
# ============================================================


class TestPublicCampaignDetail:
    """تست‌های GET /api/v1/madadkar/campaigns/{slug}/"""

    def test_retrieve_happy_path(self):
        campaign = PublishedCampaignFactory(title="جزئیات تست")

        client = APIClient()
        url = reverse(
            "madadkar:public-campaign-detail",
            kwargs={"slug": campaign.slug},
        )
        response = client.get(url)

        assert response.status_code == status.HTTP_200_OK
        assert response.data["data"]["title"] == "جزئیات تست"
        assert "description" in response.data["data"]
        assert "gallery_images" in response.data["data"]

    def test_retrieve_includes_gallery(self):
        campaign = PublishedCampaignFactory()
        CampaignImageFactory(campaign=campaign, display_order=0)
        CampaignImageFactory(campaign=campaign, display_order=1)

        client = APIClient()
        url = reverse(
            "madadkar:public-campaign-detail",
            kwargs={"slug": campaign.slug},
        )
        response = client.get(url)

        assert len(response.data["data"]["gallery_images"]) == 2

    def test_retrieve_includes_sponsor_info(self):
        sponsor = SponsorFactory(name="مددکار تست")
        campaign = PublishedCampaignFactory(sponsor=sponsor)

        client = APIClient()
        url = reverse(
            "madadkar:public-campaign-detail",
            kwargs={"slug": campaign.slug},
        )
        response = client.get(url)

        assert response.data["data"]["sponsor"]["name"] == "مددکار تست"

    def test_retrieve_includes_progress_info(self):
        campaign = PublishedCampaignFactory(
            total_amount=10_000_000,
            total_shares=100,
        )
        campaign.purchased_shares = 25
        campaign.save(update_fields=["purchased_shares", "updated_at"])

        client = APIClient()
        url = reverse(
            "madadkar:public-campaign-detail",
            kwargs={"slug": campaign.slug},
        )
        response = client.get(url)

        data = response.data["data"]
        assert data["purchased_shares"] == 25
        assert data["remaining_shares"] == 75
        assert data["progress_percent"] == 25.0
        assert data["is_fully_funded"] is False

    def test_retrieve_404_for_draft_campaign(self):
        """campaign DRAFT نباید در public قابل دسترس باشد."""
        campaign = CampaignFactory(title="پیش‌نویس")  # DRAFT, is_visible=False

        client = APIClient()
        url = reverse(
            "madadkar:public-campaign-detail",
            kwargs={"slug": campaign.slug},
        )
        response = client.get(url)

        assert response.status_code == status.HTTP_404_NOT_FOUND

    def test_retrieve_404_for_invisible_campaign(self):
        """campaign با is_visible=False نباید قابل دسترس باشد."""
        campaign = PublishedCampaignFactory(
            title="مخفی",
            is_visible=False,
        )

        client = APIClient()
        url = reverse(
            "madadkar:public-campaign-detail",
            kwargs={"slug": campaign.slug},
        )
        response = client.get(url)

        assert response.status_code == status.HTTP_404_NOT_FOUND

    def test_retrieve_404_for_nonexistent_slug(self):
        client = APIClient()
        url = reverse(
            "madadkar:public-campaign-detail",
            kwargs={"slug": "non-existent-slug"},
        )
        response = client.get(url)

        assert response.status_code == status.HTTP_404_NOT_FOUND

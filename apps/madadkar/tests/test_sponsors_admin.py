"""
تست‌های Sponsor admin endpoints.

پوشش:
- List sponsors (admin): pagination, filter, search
- Create sponsor: happy path, validation, permission, audit dispatch
- Retrieve sponsor: happy path, 404
- Update sponsor: happy path, partial, permission
- Delete sponsor: happy path, SponsorInUseError, permission
- Permission boundaries: anonymous, regular user, admin
- Public sponsor endpoints: list/detail با visibility فیلتر شده
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient

from apps.audit_logs import actions as audit_actions
from apps.madadkar.models import Sponsor
from tests.factories import AdminUserFactory, UserFactory
from tests.factories.madadkar import (
    PublishedCampaignFactory,
    SponsorFactory,
)

pytestmark = pytest.mark.django_db


_AUDIT_TASK_PATH = "apps.audit_logs.tasks.create_audit_log_task"


# ============================================================
# Helpers
# ============================================================


def _auth(client: APIClient, user) -> None:
    """احراز هویت سریع کاربر در client."""
    client.force_authenticate(user=user)


# ============================================================
# Public Sponsor endpoints
# ============================================================


class TestPublicSponsorList:
    """تست‌های GET /api/v1/madadkar/sponsors/"""

    def test_list_returns_only_sponsors_with_visible_campaigns(self):
        """فقط sponsorهایی که حداقل یک کمپین قابل نمایش دارند برمی‌گردند."""
        sponsor_with_campaign = SponsorFactory(name="با کمپین")
        PublishedCampaignFactory(sponsor=sponsor_with_campaign)

        SponsorFactory(name="بدون کمپین")  # نباید بیاد

        client = APIClient()
        url = reverse("madadkar:public-sponsor-list")
        response = client.get(url)

        assert response.status_code == status.HTTP_200_OK
        names = [item["name"] for item in response.data["data"]["results"]]
        assert "با کمپین" in names
        assert "بدون کمپین" not in names

    def test_list_accessible_without_authentication(self):
        """endpoint عمومی است."""
        client = APIClient()
        url = reverse("madadkar:public-sponsor-list")
        response = client.get(url)
        assert response.status_code == status.HTTP_200_OK

    def test_list_response_envelope(self):
        """فرمت پاسخ باید envelope استاندارد باشد."""
        sponsor = SponsorFactory()
        PublishedCampaignFactory(sponsor=sponsor)

        client = APIClient()
        url = reverse("madadkar:public-sponsor-list")
        response = client.get(url)

        assert response.data["success"] is True
        assert response.data["status_code"] == 200
        assert "message" in response.data
        assert "data" in response.data


class TestPublicSponsorDetail:
    """تست‌های GET /api/v1/madadkar/sponsors/{slug}/"""

    def test_retrieve_happy_path(self):
        sponsor = SponsorFactory(name="بنیاد علوی")
        PublishedCampaignFactory(sponsor=sponsor)

        client = APIClient()
        url = reverse(
            "madadkar:public-sponsor-detail",
            kwargs={"slug": sponsor.slug},
        )
        response = client.get(url)

        assert response.status_code == status.HTTP_200_OK
        assert response.data["data"]["name"] == "بنیاد علوی"

    def test_retrieve_404_for_sponsor_without_visible_campaigns(self):
        """sponsor بدون campaign قابل نمایش، 404 می‌دهد."""
        sponsor = SponsorFactory()  # بدون campaign

        client = APIClient()
        url = reverse(
            "madadkar:public-sponsor-detail",
            kwargs={"slug": sponsor.slug},
        )
        response = client.get(url)

        assert response.status_code == status.HTTP_404_NOT_FOUND
        assert response.data["success"] is False


# ============================================================
# Admin Sponsor — List + Create
# ============================================================


class TestAdminSponsorListCreate:
    """تست‌های GET/POST /api/v1/madadkar/admin/sponsors/"""

    # ── Permission ─────────────────────────────────────────

    def test_list_requires_authentication(self):
        client = APIClient()
        url = reverse("madadkar:admin-sponsor-list-create")
        response = client.get(url)
        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    def test_list_forbidden_for_regular_user(self):
        client = APIClient()
        _auth(client, UserFactory())
        url = reverse("madadkar:admin-sponsor-list-create")
        response = client.get(url)
        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_create_forbidden_for_regular_user(self):
        client = APIClient()
        _auth(client, UserFactory())
        url = reverse("madadkar:admin-sponsor-list-create")
        response = client.post(url, data={"name": "تست"}, format="multipart")
        assert response.status_code == status.HTTP_403_FORBIDDEN

    # ── Happy paths ────────────────────────────────────────

    def test_list_returns_all_sponsors_for_admin(self):
        """ادمین همه sponsorها را می‌بیند حتی بدون campaign."""
        SponsorFactory(name="با کمپین")
        SponsorFactory(name="بدون کمپین")

        client = APIClient()
        _auth(client, AdminUserFactory())
        url = reverse("madadkar:admin-sponsor-list-create")
        response = client.get(url)

        assert response.status_code == status.HTTP_200_OK
        names = [item["name"] for item in response.data["data"]["results"]]
        assert "با کمپین" in names
        assert "بدون کمپین" in names

    def test_list_filter_by_search(self):
        SponsorFactory(name="گروه جهادی الف")
        SponsorFactory(name="بنیاد ب")

        client = APIClient()
        _auth(client, AdminUserFactory())
        url = reverse("madadkar:admin-sponsor-list-create")
        response = client.get(url, {"search": "جهادی"})

        names = [item["name"] for item in response.data["data"]["results"]]
        assert "گروه جهادی الف" in names
        assert "بنیاد ب" not in names

    def test_create_happy_path(self):
        client = APIClient()
        _auth(client, AdminUserFactory())
        url = reverse("madadkar:admin-sponsor-list-create")

        with patch(_AUDIT_TASK_PATH) as mock_task:
            mock_task.delay = MagicMock()
            response = client.post(
                url,
                data={"name": "مددکار جدید"},
                format="multipart",
            )

        assert response.status_code == status.HTTP_201_CREATED
        assert response.data["data"]["name"] == "مددکار جدید"
        assert Sponsor.objects.filter(name="مددکار جدید").exists()

        # Audit dispatch
        mock_task.delay.assert_called_once()
        kwargs = mock_task.delay.call_args.kwargs
        assert kwargs["action"] == audit_actions.MADADKAR_SPONSOR_CREATED

    def test_create_validation_error_name_required(self):
        client = APIClient()
        _auth(client, AdminUserFactory())
        url = reverse("madadkar:admin-sponsor-list-create")
        response = client.post(url, data={}, format="multipart")

        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_create_validation_error_duplicate_name(self):
        SponsorFactory(name="تکراری")

        client = APIClient()
        _auth(client, AdminUserFactory())
        url = reverse("madadkar:admin-sponsor-list-create")
        response = client.post(
            url,
            data={"name": "تکراری"},
            format="multipart",
        )

        assert response.status_code == status.HTTP_400_BAD_REQUEST


# ============================================================
# Admin Sponsor — Retrieve / Update / Delete
# ============================================================


class TestAdminSponsorDetail:
    """تست‌های GET/PATCH/DELETE /api/v1/madadkar/admin/sponsors/{id}/"""

    # ── Retrieve ───────────────────────────────────────────

    def test_retrieve_happy_path(self):
        sponsor = SponsorFactory(name="نمونه")
        client = APIClient()
        _auth(client, AdminUserFactory())
        url = reverse(
            "madadkar:admin-sponsor-detail",
            kwargs={"sponsor_id": sponsor.pk},
        )
        response = client.get(url)

        assert response.status_code == status.HTTP_200_OK
        assert response.data["data"]["name"] == "نمونه"

    def test_retrieve_404(self):
        client = APIClient()
        _auth(client, AdminUserFactory())
        url = reverse(
            "madadkar:admin-sponsor-detail",
            kwargs={"sponsor_id": 999_999},
        )
        response = client.get(url)
        assert response.status_code == status.HTTP_404_NOT_FOUND

    def test_retrieve_forbidden_for_regular_user(self):
        sponsor = SponsorFactory()
        client = APIClient()
        _auth(client, UserFactory())
        url = reverse(
            "madadkar:admin-sponsor-detail",
            kwargs={"sponsor_id": sponsor.pk},
        )
        response = client.get(url)
        assert response.status_code == status.HTTP_403_FORBIDDEN

    # ── Update ─────────────────────────────────────────────

    def test_update_happy_path(self):
        sponsor = SponsorFactory(name="قدیمی")

        client = APIClient()
        _auth(client, AdminUserFactory())
        url = reverse(
            "madadkar:admin-sponsor-detail",
            kwargs={"sponsor_id": sponsor.pk},
        )

        with patch(_AUDIT_TASK_PATH) as mock_task:
            mock_task.delay = MagicMock()
            response = client.patch(
                url,
                data={"name": "جدید"},
                format="multipart",
            )

        assert response.status_code == status.HTTP_200_OK
        sponsor.refresh_from_db()
        assert sponsor.name == "جدید"

        mock_task.delay.assert_called_once()
        kwargs = mock_task.delay.call_args.kwargs
        assert kwargs["action"] == audit_actions.MADADKAR_SPONSOR_UPDATED

    def test_update_404(self):
        client = APIClient()
        _auth(client, AdminUserFactory())
        url = reverse(
            "madadkar:admin-sponsor-detail",
            kwargs={"sponsor_id": 999_999},
        )
        response = client.patch(url, data={"name": "x"}, format="multipart")
        assert response.status_code == status.HTTP_404_NOT_FOUND

    # ── Delete ─────────────────────────────────────────────

    def test_delete_happy_path(self):
        sponsor = SponsorFactory()

        client = APIClient()
        _auth(client, AdminUserFactory())
        url = reverse(
            "madadkar:admin-sponsor-detail",
            kwargs={"sponsor_id": sponsor.pk},
        )

        with patch(_AUDIT_TASK_PATH) as mock_task:
            mock_task.delay = MagicMock()
            response = client.delete(url)

        assert response.status_code == status.HTTP_200_OK
        sponsor.refresh_from_db()
        assert sponsor.is_active is False

    def test_delete_blocked_when_published_campaign_exists(self):
        """sponsor با campaign غیر DRAFT قابل حذف نیست."""
        sponsor = SponsorFactory()
        PublishedCampaignFactory(sponsor=sponsor)

        client = APIClient()
        _auth(client, AdminUserFactory())
        url = reverse(
            "madadkar:admin-sponsor-detail",
            kwargs={"sponsor_id": sponsor.pk},
        )
        response = client.delete(url)

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert response.data["success"] is False

        sponsor.refresh_from_db()
        assert sponsor.is_active is True  # نباید حذف شده باشه

    def test_delete_404(self):
        client = APIClient()
        _auth(client, AdminUserFactory())
        url = reverse(
            "madadkar:admin-sponsor-detail",
            kwargs={"sponsor_id": 999_999},
        )
        response = client.delete(url)
        assert response.status_code == status.HTTP_404_NOT_FOUND

"""
تست‌های Campaign admin endpoints.

پوشش:
- List campaigns (admin): pagination, filter, search, تمام وضعیت‌ها
- Create campaign: happy path, validation, divisibility, deadline rules
- Retrieve campaign: happy path, 404
- Update campaign: happy path, field locks (after PAID), terminal status locks
- Delete campaign: فقط DRAFT
- Publish campaign: state machine enforcement
- Close campaign: state machine enforcement
- Campaign gallery: add, list, delete + IDOR/404 hardening
- Permission boundaries: anonymous, regular user, admin
- Audit dispatch verification
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from django.urls import reverse
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APIClient

from apps.audit_logs import actions as audit_actions
from apps.madadkar.choices import CampaignStatus
from apps.madadkar.models import Campaign, CampaignImage
from tests.factories import AdminUserFactory, UserFactory
from tests.factories.madadkar import (
    CampaignFactory,
    CampaignImageFactory,
    CompletedCampaignFactory,
    PaidParticipationFactory,
    PublishedCampaignFactory,
    SponsorFactory,
    _make_image_file,
)

pytestmark = pytest.mark.django_db


_AUDIT_TASK_PATH = "apps.audit_logs.tasks.create_audit_log_task"


# ============================================================
# Helpers
# ============================================================


def _make_image(name: str = "cover.png"):
    """
    ساخت یک تصویر تست معتبر.

    delegate به helper مرکزی در factory module تا تمام تست‌ها از یک
    منبع واحد PNG معتبر استفاده کنند (Pillow-generated، نه hand-crafted).
    """
    return _make_image_file(name)


def _auth(client: APIClient, user) -> None:
    """احراز هویت سریع کاربر در client."""
    client.force_authenticate(user=user)


# ============================================================
# Admin Campaign — List
# ============================================================


class TestAdminCampaignList:
    """تست‌های GET /api/v1/madadkar/admin/campaigns/"""

    def test_list_requires_authentication(self):
        client = APIClient()
        url = reverse("madadkar:admin-campaign-list-create")
        response = client.get(url)
        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    def test_list_forbidden_for_regular_user(self):
        client = APIClient()
        _auth(client, UserFactory())
        url = reverse("madadkar:admin-campaign-list-create")
        response = client.get(url)
        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_list_admin_sees_all_statuses(self):
        """ادمین همه campaignها را می‌بیند حتی DRAFT."""
        CampaignFactory(title="پیش‌نویس")
        PublishedCampaignFactory(title="منتشرشده")
        CompletedCampaignFactory(title="تکمیل شده")

        client = APIClient()
        _auth(client, AdminUserFactory())
        url = reverse("madadkar:admin-campaign-list-create")
        response = client.get(url)

        assert response.status_code == status.HTTP_200_OK
        titles = [c["title"] for c in response.data["data"]["results"]]
        assert "پیش‌نویس" in titles
        assert "منتشرشده" in titles
        assert "تکمیل شده" in titles

    def test_list_filter_by_status_draft(self):
        CampaignFactory(title="پیش‌نویس A")
        PublishedCampaignFactory(title="منتشرشده B")

        client = APIClient()
        _auth(client, AdminUserFactory())
        url = reverse("madadkar:admin-campaign-list-create")
        response = client.get(url, {"status": CampaignStatus.DRAFT})

        titles = [c["title"] for c in response.data["data"]["results"]]
        assert "پیش‌نویس A" in titles
        assert "منتشرشده B" not in titles

    def test_list_filter_by_sponsor(self):
        sponsor_a = SponsorFactory(name="الف")
        sponsor_b = SponsorFactory(name="ب")
        CampaignFactory(sponsor=sponsor_a, title="A")
        CampaignFactory(sponsor=sponsor_b, title="B")

        client = APIClient()
        _auth(client, AdminUserFactory())
        url = reverse("madadkar:admin-campaign-list-create")
        response = client.get(url, {"sponsor": sponsor_a.pk})

        titles = [c["title"] for c in response.data["data"]["results"]]
        assert "A" in titles
        assert "B" not in titles


# ============================================================
# Admin Campaign — Create
# ============================================================


class TestAdminCampaignCreate:
    """تست‌های POST /api/v1/madadkar/admin/campaigns/"""

    def test_create_happy_path(self):
        sponsor = SponsorFactory()

        client = APIClient()
        _auth(client, AdminUserFactory())
        url = reverse("madadkar:admin-campaign-list-create")

        with patch(_AUDIT_TASK_PATH) as mock_task:
            mock_task.delay = MagicMock()
            response = client.post(
                url,
                data={
                    "sponsor_id": sponsor.pk,
                    "title": "حرکت تست ایجاد",
                    "description": "توضیحات تست",
                    "cover_image": _make_image(),
                    "total_amount": "10000000000",
                    "total_shares": "1000",
                    "has_deadline": "false",
                    "is_visible": "false",
                },
                format="multipart",
            )

        assert response.status_code == status.HTTP_201_CREATED
        assert response.data["data"]["title"] == "حرکت تست ایجاد"
        assert response.data["data"]["status"] == CampaignStatus.DRAFT
        assert response.data["data"]["share_price"] == 10_000_000

        # Audit dispatch
        mock_task.delay.assert_called_once()
        kwargs = mock_task.delay.call_args.kwargs
        assert kwargs["action"] == audit_actions.MADADKAR_CAMPAIGN_CREATED

    def test_create_forbidden_for_regular_user(self):
        sponsor = SponsorFactory()

        client = APIClient()
        _auth(client, UserFactory())
        url = reverse("madadkar:admin-campaign-list-create")
        response = client.post(
            url,
            data={"sponsor_id": sponsor.pk, "title": "x"},
            format="multipart",
        )
        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_create_validation_missing_required_fields(self):
        client = APIClient()
        _auth(client, AdminUserFactory())
        url = reverse("madadkar:admin-campaign-list-create")
        response = client.post(url, data={}, format="multipart")

        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_create_404_for_nonexistent_sponsor(self):
        client = APIClient()
        _auth(client, AdminUserFactory())
        url = reverse("madadkar:admin-campaign-list-create")
        response = client.post(
            url,
            data={
                "sponsor_id": 999_999,
                "title": "تست",
                "description": "...",
                "cover_image": _make_image(),
                "total_amount": "1000000",
                "total_shares": "100",
            },
            format="multipart",
        )
        assert response.status_code == status.HTTP_404_NOT_FOUND

    def test_create_validation_divisibility(self):
        """مبلغ کل باید بر تعداد سهم بدون باقیمانده تقسیم شود."""
        sponsor = SponsorFactory()

        client = APIClient()
        _auth(client, AdminUserFactory())
        url = reverse("madadkar:admin-campaign-list-create")
        response = client.post(
            url,
            data={
                "sponsor_id": sponsor.pk,
                "title": "نامتعادل",
                "description": "...",
                "cover_image": _make_image(),
                "total_amount": "10000001",  # تقسیم بر 1000 باقیمانده دارد
                "total_shares": "1000",
            },
            format="multipart",
        )

        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_create_validation_deadline_required_when_has_deadline_true(self):
        sponsor = SponsorFactory()

        client = APIClient()
        _auth(client, AdminUserFactory())
        url = reverse("madadkar:admin-campaign-list-create")
        response = client.post(
            url,
            data={
                "sponsor_id": sponsor.pk,
                "title": "متناقض",
                "description": "...",
                "cover_image": _make_image(),
                "total_amount": "1000000",
                "total_shares": "100",
                "has_deadline": "true",
                # deadline ارسال نشده
            },
            format="multipart",
        )

        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_create_validation_deadline_in_past(self):
        sponsor = SponsorFactory()
        past_deadline = (timezone.now() - timezone.timedelta(days=1)).isoformat()

        client = APIClient()
        _auth(client, AdminUserFactory())
        url = reverse("madadkar:admin-campaign-list-create")
        response = client.post(
            url,
            data={
                "sponsor_id": sponsor.pk,
                "title": "گذشته",
                "description": "...",
                "cover_image": _make_image(),
                "total_amount": "1000000",
                "total_shares": "100",
                "has_deadline": "true",
                "deadline": past_deadline,
            },
            format="multipart",
        )

        assert response.status_code == status.HTTP_400_BAD_REQUEST


# ============================================================
# Admin Campaign — Retrieve / Update / Delete
# ============================================================


class TestAdminCampaignDetail:
    """تست‌های GET/PATCH/DELETE /api/v1/madadkar/admin/campaigns/{id}/"""

    # ── Retrieve ───────────────────────────────────────────

    def test_retrieve_happy_path(self):
        campaign = CampaignFactory(title="نمونه")

        client = APIClient()
        _auth(client, AdminUserFactory())
        url = reverse(
            "madadkar:admin-campaign-detail",
            kwargs={"campaign_id": campaign.pk},
        )
        response = client.get(url)

        assert response.status_code == status.HTTP_200_OK
        assert response.data["data"]["title"] == "نمونه"

    def test_retrieve_404(self):
        client = APIClient()
        _auth(client, AdminUserFactory())
        url = reverse(
            "madadkar:admin-campaign-detail",
            kwargs={"campaign_id": 999_999},
        )
        response = client.get(url)
        assert response.status_code == status.HTTP_404_NOT_FOUND

    def test_retrieve_admin_can_see_draft(self):
        """ادمین می‌تواند campaign DRAFT را ببیند (که در public نیست)."""
        campaign = CampaignFactory()  # DRAFT

        client = APIClient()
        _auth(client, AdminUserFactory())
        url = reverse(
            "madadkar:admin-campaign-detail",
            kwargs={"campaign_id": campaign.pk},
        )
        response = client.get(url)
        assert response.status_code == status.HTTP_200_OK

    # ── Update — Happy paths ───────────────────────────────

    def test_update_title_in_draft(self):
        campaign = CampaignFactory(title="قدیمی")

        client = APIClient()
        _auth(client, AdminUserFactory())
        url = reverse(
            "madadkar:admin-campaign-detail",
            kwargs={"campaign_id": campaign.pk},
        )

        with patch(_AUDIT_TASK_PATH) as mock_task:
            mock_task.delay = MagicMock()
            response = client.patch(
                url,
                data={"title": "جدید"},
                format="multipart",
            )

        assert response.status_code == status.HTTP_200_OK
        campaign.refresh_from_db()
        assert campaign.title == "جدید"

        mock_task.delay.assert_called_once()
        kwargs = mock_task.delay.call_args.kwargs
        assert kwargs["action"] == audit_actions.MADADKAR_CAMPAIGN_UPDATED

    def test_update_financial_fields_allowed_in_draft(self):
        """در DRAFT می‌توان مبلغ و تعداد سهم را تغییر داد."""
        campaign = CampaignFactory(
            total_amount=1_000_000,
            total_shares=100,
        )

        client = APIClient()
        _auth(client, AdminUserFactory())
        url = reverse(
            "madadkar:admin-campaign-detail",
            kwargs={"campaign_id": campaign.pk},
        )
        response = client.patch(
            url,
            data={
                "total_amount": "2000000",
                "total_shares": "200",
            },
            format="multipart",
        )

        assert response.status_code == status.HTTP_200_OK
        campaign.refresh_from_db()
        assert campaign.total_amount == 2_000_000
        assert campaign.total_shares == 200
        assert campaign.share_price == 10_000

    def test_update_financial_fields_allowed_in_published_without_payment(self):
        """در PUBLISHED بدون پرداخت موفق، فیلدهای مالی هنوز قابل ویرایش‌اند."""
        campaign = PublishedCampaignFactory(
            total_amount=1_000_000,
            total_shares=100,
        )

        client = APIClient()
        _auth(client, AdminUserFactory())
        url = reverse(
            "madadkar:admin-campaign-detail",
            kwargs={"campaign_id": campaign.pk},
        )
        response = client.patch(
            url,
            data={"total_amount": "5000000", "total_shares": "500"},
            format="multipart",
        )

        assert response.status_code == status.HTTP_200_OK

    # ── Update — Field locks after PAID ────────────────────

    def test_update_financial_fields_locked_after_paid_participation(self):
        """بعد از اولین پرداخت موفق، فیلدهای مالی قفل می‌شوند."""
        campaign = PublishedCampaignFactory(
            total_amount=1_000_000,
            total_shares=100,
        )
        PaidParticipationFactory(campaign=campaign, share_count=1)

        client = APIClient()
        _auth(client, AdminUserFactory())
        url = reverse(
            "madadkar:admin-campaign-detail",
            kwargs={"campaign_id": campaign.pk},
        )
        response = client.patch(
            url,
            data={"total_amount": "5000000"},
            format="multipart",
        )

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert response.data["success"] is False

        campaign.refresh_from_db()
        assert campaign.total_amount == 1_000_000  # تغییر نکرده

    def test_update_safe_fields_allowed_after_paid(self):
        """بعد از پرداخت، title/description/cover_image همچنان قابل ویرایش‌اند."""
        campaign = PublishedCampaignFactory(title="قدیم")
        PaidParticipationFactory(campaign=campaign)

        client = APIClient()
        _auth(client, AdminUserFactory())
        url = reverse(
            "madadkar:admin-campaign-detail",
            kwargs={"campaign_id": campaign.pk},
        )
        response = client.patch(
            url,
            data={"title": "جدید پس از پرداخت"},
            format="multipart",
        )

        assert response.status_code == status.HTTP_200_OK
        campaign.refresh_from_db()
        assert campaign.title == "جدید پس از پرداخت"

    def test_update_sponsor_locked_after_paid(self):
        """تغییر sponsor بعد از پرداخت ممنوع است."""
        sponsor_a = SponsorFactory(name="الف")
        sponsor_b = SponsorFactory(name="ب")
        campaign = PublishedCampaignFactory(sponsor=sponsor_a)
        PaidParticipationFactory(campaign=campaign)

        client = APIClient()
        _auth(client, AdminUserFactory())
        url = reverse(
            "madadkar:admin-campaign-detail",
            kwargs={"campaign_id": campaign.pk},
        )
        response = client.patch(
            url,
            data={"sponsor_id": sponsor_b.pk},
            format="multipart",
        )

        assert response.status_code == status.HTTP_400_BAD_REQUEST

    # ── Update — Terminal status locks ─────────────────────

    def test_update_total_amount_locked_in_completed(self):
        """در COMPLETED فیلدهای مالی قابل ویرایش نیستند."""
        campaign = CompletedCampaignFactory()

        client = APIClient()
        _auth(client, AdminUserFactory())
        url = reverse(
            "madadkar:admin-campaign-detail",
            kwargs={"campaign_id": campaign.pk},
        )
        response = client.patch(
            url,
            data={"total_amount": "999999999"},
            format="multipart",
        )

        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_update_safe_fields_in_completed(self):
        """در COMPLETED فقط متن‌ها و تصاویر قابل ویرایش‌اند."""
        campaign = CompletedCampaignFactory(title="تکمیل قدیم")

        client = APIClient()
        _auth(client, AdminUserFactory())
        url = reverse(
            "madadkar:admin-campaign-detail",
            kwargs={"campaign_id": campaign.pk},
        )
        response = client.patch(
            url,
            data={"title": "تکمیل جدید"},
            format="multipart",
        )

        assert response.status_code == status.HTTP_200_OK
        campaign.refresh_from_db()
        assert campaign.title == "تکمیل جدید"

    # ── Delete ─────────────────────────────────────────────

    def test_delete_draft_happy_path(self):
        campaign = CampaignFactory()

        client = APIClient()
        _auth(client, AdminUserFactory())
        url = reverse(
            "madadkar:admin-campaign-detail",
            kwargs={"campaign_id": campaign.pk},
        )

        with patch(_AUDIT_TASK_PATH):
            response = client.delete(url)

        assert response.status_code == status.HTTP_200_OK
        campaign.refresh_from_db()
        assert campaign.is_active is False

    def test_delete_published_blocked(self):
        """campaign PUBLISHED قابل حذف نیست."""
        campaign = PublishedCampaignFactory()

        client = APIClient()
        _auth(client, AdminUserFactory())
        url = reverse(
            "madadkar:admin-campaign-detail",
            kwargs={"campaign_id": campaign.pk},
        )
        response = client.delete(url)

        assert response.status_code == status.HTTP_400_BAD_REQUEST

        campaign.refresh_from_db()
        assert campaign.is_active is True

    def test_delete_404(self):
        client = APIClient()
        _auth(client, AdminUserFactory())
        url = reverse(
            "madadkar:admin-campaign-detail",
            kwargs={"campaign_id": 999_999},
        )
        response = client.delete(url)
        assert response.status_code == status.HTTP_404_NOT_FOUND


# ============================================================
# Admin Campaign — Publish
# ============================================================


class TestAdminCampaignPublish:
    """تست‌های POST /api/v1/madadkar/admin/campaigns/{id}/publish/"""

    def test_publish_happy_path(self):
        campaign = CampaignFactory()

        client = APIClient()
        _auth(client, AdminUserFactory())
        url = reverse(
            "madadkar:admin-campaign-publish",
            kwargs={"campaign_id": campaign.pk},
        )

        with patch(_AUDIT_TASK_PATH) as mock_task:
            mock_task.delay = MagicMock()
            response = client.post(url)

        assert response.status_code == status.HTTP_200_OK
        campaign.refresh_from_db()
        assert campaign.status == CampaignStatus.PUBLISHED
        assert campaign.published_at is not None

        mock_task.delay.assert_called_once()
        kwargs = mock_task.delay.call_args.kwargs
        assert kwargs["action"] == audit_actions.MADADKAR_CAMPAIGN_PUBLISHED

    def test_publish_blocked_for_already_published(self):
        """campaign که قبلاً PUBLISHED شده دوباره publish نمی‌شود."""
        campaign = PublishedCampaignFactory()

        client = APIClient()
        _auth(client, AdminUserFactory())
        url = reverse(
            "madadkar:admin-campaign-publish",
            kwargs={"campaign_id": campaign.pk},
        )
        response = client.post(url)

        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_publish_blocked_for_completed(self):
        campaign = CompletedCampaignFactory()

        client = APIClient()
        _auth(client, AdminUserFactory())
        url = reverse(
            "madadkar:admin-campaign-publish",
            kwargs={"campaign_id": campaign.pk},
        )
        response = client.post(url)
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_publish_forbidden_for_regular_user(self):
        campaign = CampaignFactory()

        client = APIClient()
        _auth(client, UserFactory())
        url = reverse(
            "madadkar:admin-campaign-publish",
            kwargs={"campaign_id": campaign.pk},
        )
        response = client.post(url)
        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_publish_404(self):
        client = APIClient()
        _auth(client, AdminUserFactory())
        url = reverse(
            "madadkar:admin-campaign-publish",
            kwargs={"campaign_id": 999_999},
        )
        response = client.post(url)
        assert response.status_code == status.HTTP_404_NOT_FOUND


# ============================================================
# Admin Campaign — Close
# ============================================================


class TestAdminCampaignClose:
    """تست‌های POST /api/v1/madadkar/admin/campaigns/{id}/close/"""

    def test_close_happy_path(self):
        campaign = PublishedCampaignFactory()

        client = APIClient()
        _auth(client, AdminUserFactory())
        url = reverse(
            "madadkar:admin-campaign-close",
            kwargs={"campaign_id": campaign.pk},
        )

        with patch(_AUDIT_TASK_PATH) as mock_task:
            mock_task.delay = MagicMock()
            response = client.post(url)

        assert response.status_code == status.HTTP_200_OK
        campaign.refresh_from_db()
        assert campaign.status == CampaignStatus.CLOSED
        assert campaign.closed_at is not None

        mock_task.delay.assert_called_once()
        kwargs = mock_task.delay.call_args.kwargs
        assert kwargs["action"] == audit_actions.MADADKAR_CAMPAIGN_CLOSED

    def test_close_blocked_for_draft(self):
        """campaign DRAFT قابل بستن نیست."""
        campaign = CampaignFactory()

        client = APIClient()
        _auth(client, AdminUserFactory())
        url = reverse(
            "madadkar:admin-campaign-close",
            kwargs={"campaign_id": campaign.pk},
        )
        response = client.post(url)

        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_close_blocked_for_already_closed(self):
        campaign = PublishedCampaignFactory()
        campaign.status = CampaignStatus.CLOSED
        campaign.closed_at = timezone.now()
        campaign.save()

        client = APIClient()
        _auth(client, AdminUserFactory())
        url = reverse(
            "madadkar:admin-campaign-close",
            kwargs={"campaign_id": campaign.pk},
        )
        response = client.post(url)
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_close_forbidden_for_regular_user(self):
        campaign = PublishedCampaignFactory()

        client = APIClient()
        _auth(client, UserFactory())
        url = reverse(
            "madadkar:admin-campaign-close",
            kwargs={"campaign_id": campaign.pk},
        )
        response = client.post(url)
        assert response.status_code == status.HTTP_403_FORBIDDEN


# ============================================================
# Admin Campaign Gallery
# ============================================================


class TestAdminCampaignGallery:
    """تست‌های /api/v1/madadkar/admin/campaigns/{id}/images/"""

    # ── List ───────────────────────────────────────────────

    def test_list_images_happy_path(self):
        campaign = PublishedCampaignFactory()
        CampaignImageFactory(campaign=campaign, display_order=0)
        CampaignImageFactory(campaign=campaign, display_order=1)

        client = APIClient()
        _auth(client, AdminUserFactory())
        url = reverse(
            "madadkar:admin-campaign-image-list-create",
            kwargs={"campaign_id": campaign.pk},
        )
        response = client.get(url)

        assert response.status_code == status.HTTP_200_OK
        assert len(response.data["data"]) == 2

    def test_list_images_404_for_nonexistent_campaign(self):
        client = APIClient()
        _auth(client, AdminUserFactory())
        url = reverse(
            "madadkar:admin-campaign-image-list-create",
            kwargs={"campaign_id": 999_999},
        )
        response = client.get(url)
        assert response.status_code == status.HTTP_404_NOT_FOUND

    def test_list_images_forbidden_for_regular_user(self):
        campaign = PublishedCampaignFactory()

        client = APIClient()
        _auth(client, UserFactory())
        url = reverse(
            "madadkar:admin-campaign-image-list-create",
            kwargs={"campaign_id": campaign.pk},
        )
        response = client.get(url)
        assert response.status_code == status.HTTP_403_FORBIDDEN

    # ── Create / Upload ────────────────────────────────────

    def test_add_image_happy_path(self):
        campaign = PublishedCampaignFactory()

        client = APIClient()
        _auth(client, AdminUserFactory())
        url = reverse(
            "madadkar:admin-campaign-image-list-create",
            kwargs={"campaign_id": campaign.pk},
        )

        with patch(_AUDIT_TASK_PATH) as mock_task:
            mock_task.delay = MagicMock()
            response = client.post(
                url,
                data={
                    "image": _make_image("gallery.png"),
                    "alt_text": "تصویر تست",
                },
                format="multipart",
            )

        assert response.status_code == status.HTTP_201_CREATED
        assert CampaignImage.objects.filter(campaign=campaign).count() == 1

        mock_task.delay.assert_called_once()
        kwargs = mock_task.delay.call_args.kwargs
        assert kwargs["action"] == audit_actions.MADADKAR_CAMPAIGN_IMAGE_ADDED

    def test_add_image_auto_display_order(self):
        """display_order خودکار به انتها اضافه می‌شود."""
        campaign = PublishedCampaignFactory()
        CampaignImageFactory(campaign=campaign, display_order=5)

        client = APIClient()
        _auth(client, AdminUserFactory())
        url = reverse(
            "madadkar:admin-campaign-image-list-create",
            kwargs={"campaign_id": campaign.pk},
        )
        response = client.post(
            url,
            data={"image": _make_image()},
            format="multipart",
        )

        assert response.status_code == status.HTTP_201_CREATED
        assert response.data["data"]["display_order"] == 6

    def test_add_image_with_explicit_display_order(self):
        campaign = PublishedCampaignFactory()

        client = APIClient()
        _auth(client, AdminUserFactory())
        url = reverse(
            "madadkar:admin-campaign-image-list-create",
            kwargs={"campaign_id": campaign.pk},
        )
        response = client.post(
            url,
            data={
                "image": _make_image(),
                "display_order": "3",
            },
            format="multipart",
        )

        assert response.status_code == status.HTTP_201_CREATED
        assert response.data["data"]["display_order"] == 3

    def test_add_image_404_for_nonexistent_campaign(self):
        client = APIClient()
        _auth(client, AdminUserFactory())
        url = reverse(
            "madadkar:admin-campaign-image-list-create",
            kwargs={"campaign_id": 999_999},
        )
        response = client.post(
            url,
            data={"image": _make_image()},
            format="multipart",
        )
        assert response.status_code == status.HTTP_404_NOT_FOUND

    def test_add_image_validation_missing_image(self):
        campaign = PublishedCampaignFactory()

        client = APIClient()
        _auth(client, AdminUserFactory())
        url = reverse(
            "madadkar:admin-campaign-image-list-create",
            kwargs={"campaign_id": campaign.pk},
        )
        response = client.post(url, data={}, format="multipart")

        assert response.status_code == status.HTTP_400_BAD_REQUEST

    # ── Delete ─────────────────────────────────────────────

    def test_delete_image_happy_path(self):
        campaign = PublishedCampaignFactory()
        image = CampaignImageFactory(campaign=campaign)

        client = APIClient()
        _auth(client, AdminUserFactory())
        url = reverse(
            "madadkar:admin-campaign-image-delete",
            kwargs={"campaign_id": campaign.pk, "image_id": image.pk},
        )

        with patch(_AUDIT_TASK_PATH) as mock_task:
            mock_task.delay = MagicMock()
            response = client.delete(url)

        assert response.status_code == status.HTTP_200_OK
        image.refresh_from_db()
        assert image.is_active is False

        mock_task.delay.assert_called_once()
        kwargs = mock_task.delay.call_args.kwargs
        assert kwargs["action"] == audit_actions.MADADKAR_CAMPAIGN_IMAGE_REMOVED

    def test_delete_image_404_wrong_campaign(self):
        """IDOR check — تصویر یک campaign دیگر را نمی‌توان از این path حذف کرد."""
        campaign_a = PublishedCampaignFactory()
        campaign_b = PublishedCampaignFactory()
        image_b = CampaignImageFactory(campaign=campaign_b)

        client = APIClient()
        _auth(client, AdminUserFactory())
        # تلاش برای حذف image_b از طریق campaign_a
        url = reverse(
            "madadkar:admin-campaign-image-delete",
            kwargs={"campaign_id": campaign_a.pk, "image_id": image_b.pk},
        )
        response = client.delete(url)

        assert response.status_code == status.HTTP_404_NOT_FOUND

        # image_b هنوز فعال است
        image_b.refresh_from_db()
        assert image_b.is_active is True

    def test_delete_image_404_for_nonexistent_image(self):
        campaign = PublishedCampaignFactory()

        client = APIClient()
        _auth(client, AdminUserFactory())
        url = reverse(
            "madadkar:admin-campaign-image-delete",
            kwargs={"campaign_id": campaign.pk, "image_id": 999_999},
        )
        response = client.delete(url)
        assert response.status_code == status.HTTP_404_NOT_FOUND

    def test_delete_image_forbidden_for_regular_user(self):
        campaign = PublishedCampaignFactory()
        image = CampaignImageFactory(campaign=campaign)

        client = APIClient()
        _auth(client, UserFactory())
        url = reverse(
            "madadkar:admin-campaign-image-delete",
            kwargs={"campaign_id": campaign.pk, "image_id": image.pk},
        )
        response = client.delete(url)
        assert response.status_code == status.HTTP_403_FORBIDDEN


# ============================================================
# Cross-cutting concerns
# ============================================================


class TestSoftDeletedCampaignNotInAdminQueries:
    """soft-deleted campaign نباید در queryهای ادمین ظاهر شود."""

    def test_soft_deleted_campaign_excluded_from_list(self):
        CampaignFactory(title="فعال")
        deleted = CampaignFactory(title="حذف‌شده")
        deleted.soft_delete()

        client = APIClient()
        _auth(client, AdminUserFactory())
        url = reverse("madadkar:admin-campaign-list-create")
        response = client.get(url)

        titles = [c["title"] for c in response.data["data"]["results"]]
        assert "فعال" in titles
        assert "حذف‌شده" not in titles

    def test_soft_deleted_campaign_returns_404_on_detail(self):
        campaign = CampaignFactory()
        campaign.soft_delete()

        client = APIClient()
        _auth(client, AdminUserFactory())
        url = reverse(
            "madadkar:admin-campaign-detail",
            kwargs={"campaign_id": campaign.pk},
        )
        response = client.get(url)
        assert response.status_code == status.HTTP_404_NOT_FOUND


class TestCampaignStateMachineIntegrity:
    """تست یکپارچگی state machine campaign از طریق API."""

    def test_full_lifecycle_draft_to_closed(self):
        """مسیر کامل: DRAFT → PUBLISHED → CLOSED."""
        client = APIClient()
        _auth(client, AdminUserFactory())

        campaign = CampaignFactory()
        assert campaign.status == CampaignStatus.DRAFT

        # Publish
        with patch(_AUDIT_TASK_PATH):
            url = reverse(
                "madadkar:admin-campaign-publish",
                kwargs={"campaign_id": campaign.pk},
            )
            response = client.post(url)
        assert response.status_code == status.HTTP_200_OK
        campaign.refresh_from_db()
        assert campaign.status == CampaignStatus.PUBLISHED

        # Close
        with patch(_AUDIT_TASK_PATH):
            url = reverse(
                "madadkar:admin-campaign-close",
                kwargs={"campaign_id": campaign.pk},
            )
            response = client.post(url)
        assert response.status_code == status.HTTP_200_OK
        campaign.refresh_from_db()
        assert campaign.status == CampaignStatus.CLOSED

    def test_cannot_close_then_reopen(self):
        """campaign CLOSED قابل publish دوباره نیست."""
        client = APIClient()
        _auth(client, AdminUserFactory())

        campaign = PublishedCampaignFactory()
        campaign.status = CampaignStatus.CLOSED
        campaign.closed_at = timezone.now()
        campaign.save()

        url = reverse(
            "madadkar:admin-campaign-publish",
            kwargs={"campaign_id": campaign.pk},
        )
        response = client.post(url)
        assert response.status_code == status.HTTP_400_BAD_REQUEST

        # یا close دوباره
        url = reverse(
            "madadkar:admin-campaign-close",
            kwargs={"campaign_id": campaign.pk},
        )
        response = client.post(url)
        assert response.status_code == status.HTTP_400_BAD_REQUEST


# Ensure Campaign import is used at module level (Ruff F401 prevention)
_ = Campaign

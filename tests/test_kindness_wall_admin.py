"""تست‌های API ادمین و Django Admin دیوار مهربانی v2.

پنل ادمین «تنها راه ورود آگهی» است؛ اینجا هر دو مسیر (REST ادمین و Admin
سایتی) با هم قفل می‌شوند: اکشن‌ها، audit، نگهبان دسته، خروجی اکسل و badgeها.
"""

from __future__ import annotations

from datetime import timedelta
from unittest.mock import patch

import pytest
from django.contrib.admin.sites import AdminSite
from django.test import RequestFactory
from django.urls import reverse
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APIClient

from apps.audit_logs.actions import (
    KINDNESS_LISTING_FULFILLED,
    KINDNESS_LISTING_PUBLISHED,
)
from apps.kindness_wall import admin as kw_admin, services
from apps.kindness_wall.admin import KindnessListingAdmin, KindnessOfferAdmin
from apps.kindness_wall.choices import ListingStatus, OfferStatus
from apps.kindness_wall.models import KindnessCategory, KindnessListing, KindnessOffer
from tests.factories import AdminUserFactory, UserFactory
from tests.factories.kindness_wall import (
    KindnessCategoryFactory,
    KindnessListingFactory,
    PublishedNeedListingFactory,
)

_TASK_PATCH_PATH = "apps.audit_logs.tasks.create_audit_log_task"


def _admin_client(user=None) -> APIClient:
    """کلاینت احراز هویت‌شده ادمین (force_authenticate؛ بدون JWT loop)."""
    client = APIClient()
    client.force_authenticate(user=user or AdminUserFactory())
    return client


@pytest.mark.django_db
class TestAdminRestCategories:
    def test_non_admin_is_forbidden(self) -> None:
        client = APIClient()
        client.force_authenticate(user=UserFactory())
        response = client.get(reverse("kindness_wall:admin-category-list"))
        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_create_category_and_count_in_list(self) -> None:
        client = _admin_client()
        with patch(_TASK_PATCH_PATH) as mock_task:
            response = client.post(
                reverse("kindness_wall:admin-category-list"),
                {"title": "لوازم آشپزخانه", "icon": "🍳", "order": 3},
                format="json",
            )
        assert response.status_code == status.HTTP_201_CREATED
        assert response.data["data"]["slug"] == "لوازم-آشپزخانه"
        mock_task.delay.assert_called_once()

    def test_deactivate_blocked_while_listings_open(self) -> None:
        category = KindnessCategoryFactory()
        PublishedNeedListingFactory(category=category)
        with patch(_TASK_PATCH_PATH):
            response = _admin_client().delete(
                reverse("kindness_wall:admin-category-detail", kwargs={"category_id": category.pk})
            )
        assert response.status_code == status.HTTP_409_CONFLICT
        category.refresh_from_db()
        assert category.is_active is True


@pytest.mark.django_db
class TestAdminRestListings:
    def _payload(self, category, **overrides) -> dict:
        """بدنهٔ کامل و معتبر آگهی برای create."""
        base = {
            "category": category.pk,
            "title": "بافتنی گرم برای زمستان",
            "description": "برای کودکان کار خیابانی منطقهٔ ۱۲ تهران به این نیاز هست",
            "quantity": 3,
            "unit": "بسته",
            "urgency": "urgent",
            "city": "تهران",
            "contact_phone": "۰۹۱۲۱۱۱۲۲۳۳",
            "contact_telegram": "@mehraban",
        }
        base.update(overrides)
        return base

    def test_create_makes_draft_and_normalizes_channels(self) -> None:
        category = KindnessCategoryFactory()
        with patch(_TASK_PATCH_PATH):
            response = _admin_client().post(
                reverse("kindness_wall:admin-listing-list"),
                self._payload(category),
                format="json",
            )
        assert response.status_code == status.HTTP_201_CREATED
        listing = KindnessListing.objects.get(pk=response.data["data"]["id"])
        assert listing.status == ListingStatus.DRAFT
        assert listing.contact_phone == "09121112233"
        assert listing.contact_telegram == "mehraban"

    def test_create_rejects_all_channels_invalid(self) -> None:
        category = KindnessCategoryFactory()
        response = _admin_client().post(
            reverse("kindness_wall:admin-listing-list"),
            self._payload(category, contact_phone="123", contact_instagram="a"),
            format="json",
        )
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        errors = response.data["errors"]
        assert "contact_phone" in errors
        assert "contact_instagram" in errors

    def test_create_rejects_short_description(self) -> None:
        category = KindnessCategoryFactory()
        response = _admin_client().post(
            reverse("kindness_wall:admin-listing-list"),
            self._payload(category, description="کوتاه است"),
            format="json",
        )
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "description" in response.data["errors"]

    def test_publish_action_sets_expiry_and_audits(self) -> None:
        listing = KindnessListingFactory()
        admin = AdminUserFactory()
        with patch(_TASK_PATCH_PATH) as mock_task:
            response = _admin_client(admin).post(
                reverse(
                    "kindness_wall:admin-listing-action",
                    kwargs={"listing_id": listing.pk, "action": "publish"},
                )
            )
        assert response.status_code == status.HTTP_200_OK
        listing.refresh_from_db()
        assert listing.status == ListingStatus.PUBLISHED
        assert listing.expires_at > timezone.now() + timedelta(days=40)
        kwargs = mock_task.delay.call_args.kwargs
        assert kwargs["action"] == KINDNESS_LISTING_PUBLISHED

    def test_publish_action_conflicts_without_channels(self) -> None:
        listing = KindnessListingFactory(contact_phone="")
        response = _admin_client().post(
            reverse(
                "kindness_wall:admin-listing-action",
                kwargs={"listing_id": listing.pk, "action": "publish"},
            )
        )
        assert response.status_code == status.HTTP_409_CONFLICT
        listing.refresh_from_db()
        assert listing.status == ListingStatus.DRAFT

    def test_fulfill_action_stores_note(self) -> None:
        listing = PublishedNeedListingFactory()
        with patch(_TASK_PATCH_PATH) as mock_task:
            response = _admin_client().post(
                reverse(
                    "kindness_wall:admin-listing-action",
                    kwargs={"listing_id": listing.pk, "action": "fulfill"},
                ),
                {"note": "با کمک سه داوطلب"},
                format="json",
            )
        assert response.status_code == status.HTTP_200_OK
        listing.refresh_from_db()
        assert listing.status == ListingStatus.FULFILLED
        assert listing.fulfillment_note == "با کمک سه داوطلب"
        assert mock_task.delay.call_args.kwargs["action"] == KINDNESS_LISTING_FULFILLED

    def test_unknown_action_is_404(self) -> None:
        listing = PublishedNeedListingFactory()
        response = _admin_client().post(
            reverse(
                "kindness_wall:admin-listing-action",
                kwargs={"listing_id": listing.pk, "action": "launch-rocket"},
            )
        )
        assert response.status_code == status.HTTP_404_NOT_FOUND

    def test_admin_list_includes_drafts_and_search(self) -> None:
        category = KindnessCategoryFactory()
        draft = KindnessListingFactory(category=category, title="پتوی مسافرتی")
        response = _admin_client().get(
            reverse("kindness_wall:admin-listing-list"), {"search": "پتوی"}
        )
        slugs = [row["slug"] for row in response.data["data"]["results"]]
        assert slugs == [draft.slug]

    def test_patch_updates_title_keeps_slug(self) -> None:
        listing = KindnessListingFactory()
        old_slug = listing.slug
        response = _admin_client().patch(
            reverse("kindness_wall:admin-listing-detail", kwargs={"listing_id": listing.pk}),
            {"title": "عنوان ویرایش‌شدهٔ جدید"},
            format="json",
        )
        assert response.status_code == status.HTTP_200_OK
        listing.refresh_from_db()
        assert listing.title == "عنوان ویرایش‌شدهٔ جدید"
        assert listing.slug == old_slug


@pytest.mark.django_db
class TestAdminRestOffers:
    def test_review_flow_updates_and_notifies_nothing(self) -> None:
        listing = PublishedNeedListingFactory()
        volunteer = UserFactory()
        offer = KindnessOffer.objects.create(listing=listing, user=volunteer, message="دارم")
        admin = AdminUserFactory()
        with patch(_TASK_PATCH_PATH):
            response = _admin_client(admin).post(
                reverse("kindness_wall:admin-offer-review", kwargs={"offer_id": offer.pk}),
                {"status": OfferStatus.CONTACTED, "note": "شماره‌ات را دادم"},
                format="json",
            )
        assert response.status_code == status.HTTP_200_OK
        offer.refresh_from_db()
        assert offer.status == OfferStatus.CONTACTED
        assert offer.handled_by == admin
        assert offer.admin_note == "شماره‌ات را دادم"
        # سیاست v2: هیچ اعلان درون‌اپی از این مسیر نباید ساخته شود
        from apps.notifications.models import NotificationEvent

        assert not NotificationEvent.objects.filter(event_type__startswith="kindness.").exists()

    def test_offer_queue_filter_by_status(self) -> None:
        listing = PublishedNeedListingFactory()
        new_offer = KindnessOffer.objects.create(listing=listing, user=UserFactory())
        handled = KindnessOffer.objects.create(
            listing=listing, user=UserFactory(), status=OfferStatus.CONTACTED
        )
        response = _admin_client().get(
            reverse("kindness_wall:admin-offer-list"), {"status": OfferStatus.NEW}
        )
        slugs = {row["id"] for row in response.data["data"]["results"]}
        assert slugs == {new_offer.pk}
        assert handled.pk not in slugs

    def test_volunteer_locked_after_review(self) -> None:
        listing = PublishedNeedListingFactory()
        volunteer = UserFactory()
        KindnessOffer.objects.create(
            listing=listing, user=volunteer, status=OfferStatus.CONTACTED, message="اولی"
        )
        client = APIClient()
        client.force_authenticate(user=volunteer)
        response = client.post(
            reverse("kindness_wall:offer-create", kwargs={"slug": listing.slug}),
            {"message": "باز هم!"},
            format="json",
        )
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert listing.offers.get().message == "اولی"  # پیامِ بررسی‌شده بازنویسی نشد


@pytest.mark.django_db
class TestAdminRestExports:
    def test_listings_export_streams_xlsx_with_filter(self) -> None:
        category = KindnessCategoryFactory()
        PublishedNeedListingFactory(category=category, title="یخچال")
        KindnessListingFactory(category=category, title="پتو")
        with patch(_TASK_PATCH_PATH):
            response = _admin_client().get(
                reverse("kindness_wall:admin-export-listings"), {"category": category.slug}
            )
        assert response.status_code == status.HTTP_200_OK
        assert "spreadsheetml" in response["Content-Type"]
        assert response["Content-Disposition"].startswith(
            'attachment; filename="kindness-wall-listings-'
        )
        assert len(response.content) > 1000  # شیت واقعی، نه بدنهٔ خالی

    def test_offers_export_ok(self) -> None:
        listing = PublishedNeedListingFactory()
        KindnessOffer.objects.create(listing=listing, user=UserFactory())
        with patch(_TASK_PATCH_PATH):
            response = _admin_client().get(reverse("kindness_wall:admin-export-offers"))
        assert response.status_code == status.HTTP_200_OK
        assert "spreadsheetml" in response["Content-Type"]


@pytest.mark.django_db
class TestDjangoAdminSurface:
    """اکشن‌های Django Admin — همان‌که ادمین واقعی روزمره کار می‌کند."""

    def _request(self, user):
        """درخواست ادمین با storage پیام (admin actionها messages می‌زنند)."""
        from django.contrib.messages.storage.fallback import FallbackStorage
        from django.contrib.sessions.backends.db import SessionStore

        request = RequestFactory().post("/admin/")
        request.user = user
        request.session = SessionStore()
        request._messages = FallbackStorage(request)
        return request

    def test_admin_publish_action_reports_channel_errors(self) -> None:
        category = KindnessCategoryFactory()
        good = KindnessListingFactory(category=category)
        bad = KindnessListingFactory(category=category, contact_phone="")
        model_admin = KindnessListingAdmin(KindnessListing, AdminSite())
        with patch(_TASK_PATCH_PATH):
            model_admin.publish_listings(
                self._request(AdminUserFactory()),
                KindnessListing.objects.filter(pk__in=[good.pk, bad.pk]),
            )
        good.refresh_from_db()
        bad.refresh_from_db()
        assert good.status == ListingStatus.PUBLISHED
        assert bad.status == ListingStatus.DRAFT

    def test_admin_offer_actions_mark_and_lock(self) -> None:
        listing = PublishedNeedListingFactory()
        offer = KindnessOffer.objects.create(listing=listing, user=UserFactory())
        model_admin = KindnessOfferAdmin(KindnessOffer, AdminSite())
        model_admin.mark_contacted(self._request(AdminUserFactory()), KindnessOffer.objects.all())
        offer.refresh_from_db()
        assert offer.status == OfferStatus.CONTACTED
        assert offer.handled_at is not None

    def test_admin_delete_offers_is_disabled(self) -> None:
        model_admin = KindnessOfferAdmin(KindnessOffer, AdminSite())
        actions = model_admin.get_actions(self._request(AdminUserFactory()))
        assert "delete_selected" not in actions
        assert model_admin.has_delete_permission(self._request(AdminUserFactory())) is False

    def test_category_admin_open_count_uses_board_filter(self) -> None:
        category = KindnessCategoryFactory()
        PublishedNeedListingFactory(category=category)
        PublishedNeedListingFactory(
            category=category, expires_at=timezone.now() - timedelta(days=1)
        )
        model_admin = kw_admin.KindnessCategoryAdmin(KindnessCategory, AdminSite())
        assert model_admin.open_count(category) is not None
        assert category.open_listings().count() == 1

    def test_service_error_on_renew_via_admin_action(self) -> None:
        fulfilled = PublishedNeedListingFactory()
        services.fulfill_listing(listing=fulfilled)
        model_admin = KindnessListingAdmin(KindnessListing, AdminSite())
        model_admin.renew_listings(
            self._request(AdminUserFactory()),
            KindnessListing.objects.filter(pk=fulfilled.pk),
        )
        fulfilled.refresh_from_db()
        assert fulfilled.status == ListingStatus.FULFILLED  # renew رد شد


@pytest.mark.django_db
class TestSchemaAndEnumNaming:
    def test_schema_generates_with_kindness_enums(self) -> None:
        """اسکیمای کامل API باید بدون خطا تولید شود (ENUM overrides فعال‌اند)."""
        import subprocess
        import sys

        result = subprocess.run(
            [sys.executable, "manage.py", "spectacular", "--validate", "--fail-on-warn"],
            capture_output=True,
            text=True,
            timeout=240,
        )
        assert result.returncode == 0, result.stderr[-3000:]

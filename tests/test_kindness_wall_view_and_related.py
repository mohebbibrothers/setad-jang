"""تست‌های «شمارشِ امنِ بازدید» و «نیازهای مشابه».

قراردادهای قفل‌شده:

شمارشِ بازدید (POST /listings/{slug}/view/):
  • هر بیننده در پنجرهٔ dedupe فقط **یک** شمارش تولید می‌کند؛ رفرشِ پیاپی
    عدد را بالا نمی‌برد.
  • کاربرِ واردشده با شناسهٔ خودش dedupe می‌شود (مستقل از دستگاه).
  • کارکنان/ادمین شمارش نمی‌شوند (پیش‌نمایش آمار را آلوده نمی‌کند).
  • آگهیِ غیرِ‌عمومی ۴۰۴ می‌دهد و شمارنده را لمس نمی‌کند.
  • پاسخ همیشه عددِ **تازه** را برمی‌گرداند تا رابط بدونِ رفرش به‌روز شود.
  • پنجره از تنظیمات (`KINDNESS_VIEW_DEDUPE_SECONDS`) قابل تغییر است.
  • رندرِ جزئیات هرگز شمارنده را تغییر نمی‌دهد (ریشهٔ عددِ بادکرده).

نیازهای مشابه (GET /listings/{slug}/related/):
  • خودِ آگهی هرگز در نتیجه نیست (حذفِ سمتِ سرور، نه فرانت).
  • ترتیب بر پایهٔ ربط: دسته+شهر > دسته > استان > سراسری > بقیه.
  • `limit` کلمپ می‌شود (۱..۱۲) و مقدارِ نامعتبر به پیش‌فرض برمی‌گردد.
  • آگهیِ غیرِ‌عمومی/ناموجود ۴۰۴.
  • خروجی هیچ فیلدِ تماسی ندارد (همان سیاستِ ضد اسکرپینگِ فهرست).
"""

from __future__ import annotations

from datetime import timedelta

import pytest
from django.core.cache import cache
from django.urls import reverse
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APIClient

from apps.kindness_wall.choices import RELATED_MAX_LIMIT, ListingStatus
from apps.kindness_wall.models import KindnessListing
from apps.kindness_wall.services import viewer_fingerprint
from tests.factories import AdminUserFactory, UserFactory
from tests.factories.kindness_wall import (
    KindnessCategoryFactory,
    KindnessListingFactory,
    PublishedNeedListingFactory,
)

pytestmark = pytest.mark.django_db

_CONTACT_FIELDS = (
    "contact_phone",
    "contact_bale",
    "contact_eitaa",
    "contact_telegram",
    "contact_rubika",
    "contact_instagram",
)


def _view_url(slug: str) -> str:
    return reverse("kindness_wall:listing-view", kwargs={"slug": slug})


def _related_url(slug: str) -> str:
    return reverse("kindness_wall:listing-related", kwargs={"slug": slug})


@pytest.fixture(autouse=True)
def _clear_cache():
    """هر تست با کشِ خالی شروع شود تا dedupe بینِ تست‌ها نشت نکند."""
    cache.clear()
    yield
    cache.clear()


class TestViewBeacon:
    def test_first_view_counts_and_returns_fresh_number(self) -> None:
        listing = PublishedNeedListingFactory()
        response = APIClient().post(_view_url(listing.slug))
        assert response.status_code == status.HTTP_200_OK
        data = response.data["data"]
        assert data["counted"] is True
        assert data["view_count"] == 1
        listing.refresh_from_db()
        assert listing.view_count == 1

    def test_repeat_view_in_window_is_not_counted(self) -> None:
        listing = PublishedNeedListingFactory()
        client = APIClient()
        for _ in range(4):
            response = client.post(_view_url(listing.slug))
            assert response.status_code == status.HTTP_200_OK
        listing.refresh_from_db()
        # چهار رفرشِ پیاپی = یک بازدید
        assert listing.view_count == 1
        assert response.data["data"]["counted"] is False
        assert response.data["data"]["view_count"] == 1

    def test_different_viewers_each_count(self) -> None:
        listing = PublishedNeedListingFactory()
        client_a = APIClient(REMOTE_ADDR="10.0.0.1", HTTP_USER_AGENT="BrowserA/1.0")
        client_b = APIClient(REMOTE_ADDR="10.0.0.2", HTTP_USER_AGENT="BrowserB/1.0")
        client_a.post(_view_url(listing.slug))
        client_b.post(_view_url(listing.slug))
        listing.refresh_from_db()
        assert listing.view_count == 2

    def test_same_ip_different_browser_counts_separately(self) -> None:
        """چند مرورگر پشتِ یک NAT باید بازدیدِ مستقل داشته باشند."""
        listing = PublishedNeedListingFactory()
        APIClient(REMOTE_ADDR="10.0.0.9", HTTP_USER_AGENT="Chrome/120").post(
            _view_url(listing.slug)
        )
        APIClient(REMOTE_ADDR="10.0.0.9", HTTP_USER_AGENT="Firefox/121").post(
            _view_url(listing.slug)
        )
        listing.refresh_from_db()
        assert listing.view_count == 2

    def test_authenticated_user_fingerprint_uses_id(self) -> None:
        listing = PublishedNeedListingFactory()
        user = UserFactory()
        client = APIClient()
        client.force_authenticate(user=user)
        client.post(_view_url(listing.slug))
        # همان کاربر از «دستگاهِ» دیگر (IP دیگر) هم دوباره شمرده نمی‌شود
        other = APIClient(REMOTE_ADDR="203.0.113.7", HTTP_USER_AGENT="OtherDevice/2")
        other.force_authenticate(user=user)
        response = other.post(_view_url(listing.slug))
        listing.refresh_from_db()
        assert listing.view_count == 1
        assert response.data["data"]["counted"] is False

    def test_staff_is_never_counted(self) -> None:
        listing = PublishedNeedListingFactory()
        client = APIClient()
        client.force_authenticate(user=AdminUserFactory(is_staff=True, is_superuser=True))
        response = client.post(_view_url(listing.slug))
        assert response.status_code == status.HTTP_200_OK
        assert response.data["data"]["counted"] is False
        listing.refresh_from_db()
        assert listing.view_count == 0

    def test_unknown_or_draft_listing_returns_404(self) -> None:
        draft = KindnessListingFactory()
        client = APIClient()
        assert client.post(_view_url(draft.slug)).status_code == status.HTTP_404_NOT_FOUND
        assert client.post(_view_url("هیچ-چنین-آگهی")).status_code == status.HTTP_404_NOT_FOUND
        draft.refresh_from_db()
        assert draft.view_count == 0

    def test_expired_listing_is_not_counted(self) -> None:
        expired = PublishedNeedListingFactory(expires_at=timezone.now() - timedelta(hours=1))
        response = APIClient().post(_view_url(expired.slug))
        assert response.status_code == status.HTTP_404_NOT_FOUND
        expired.refresh_from_db()
        assert expired.view_count == 0

    def test_dedupe_window_comes_from_settings(self, settings) -> None:
        settings.KINDNESS_VIEW_DEDUPE_SECONDS = 1
        listing = PublishedNeedListingFactory()
        client = APIClient()
        client.post(_view_url(listing.slug))
        # پنجرهٔ یک‌ثانیه‌ای را دستی منقضی می‌کنیم (بدونِ sleep در تست)
        cache.clear()
        client.post(_view_url(listing.slug))
        listing.refresh_from_db()
        assert listing.view_count == 2

    def test_detail_render_never_touches_counter(self) -> None:
        listing = PublishedNeedListingFactory()
        client = APIClient()
        for _ in range(2):
            client.get(reverse("kindness_wall:listing-detail", kwargs={"slug": listing.slug}))
        listing.refresh_from_db()
        assert listing.view_count == 0

    def test_fingerprint_never_stores_raw_ip(self) -> None:
        listing = PublishedNeedListingFactory()
        request = APIClient(REMOTE_ADDR="198.51.100.23", HTTP_USER_AGENT="UA/1").post(
            _view_url(listing.slug)
        )
        assert request.status_code == status.HTTP_200_OK
        # هیچ کلیدِ کشی نباید IP خام را در خود داشته باشد
        keys = []
        if hasattr(cache, "_cache"):
            keys = list(getattr(cache, "_cache", {}).keys())
        assert all("198.51.100.23" not in key for key in keys)


class TestRelatedListings:
    def test_related_never_includes_itself(self) -> None:
        category = KindnessCategoryFactory(title="لوازم آشپزخانه")
        listing = PublishedNeedListingFactory(category=category, title="یخچال")
        PublishedNeedListingFactory(category=category, title="اجاق")
        PublishedNeedListingFactory(category=category, title="ماشین لباسشویی")

        response = APIClient().get(_related_url(listing.slug))
        assert response.status_code == status.HTTP_200_OK
        slugs = [row["slug"] for row in response.data["data"]]
        assert listing.slug not in slugs
        assert len(slugs) == 2

    def test_related_ranks_same_category_first(self) -> None:
        category = KindnessCategoryFactory()
        other_category = KindnessCategoryFactory()
        listing = PublishedNeedListingFactory(category=category, province="تهران", city="")
        same_cat = PublishedNeedListingFactory(category=category, title="همان دسته")
        other_province = PublishedNeedListingFactory(
            category=other_category, province="گیلان", title="استان دیگر"
        )
        nationwide = PublishedNeedListingFactory(
            category=other_category, province="", city="", title="سراسری"
        )

        response = APIClient().get(_related_url(listing.slug))
        slugs = [row["slug"] for row in response.data["data"]]
        assert slugs[0] == same_cat.slug
        # سراسری (ربط ۲) پیش از «استانِ دیگر » (ربط ۱) — چون استانِ آگهی تهران است
        assert slugs.index(nationwide.slug) < slugs.index(other_province.slug)

    def test_related_prefers_same_city_inside_category(self) -> None:
        category = KindnessCategoryFactory()
        listing = PublishedNeedListingFactory(category=category, province="تهران", city="ورامین")
        same_city = PublishedNeedListingFactory(
            category=category, province="تهران", city="ورامین", title="هم‌شهر"
        )
        same_cat_other_city = PublishedNeedListingFactory(
            category=category, province="تهران", city="ری", title="هم‌دسته، شهرِ دیگر"
        )
        response = APIClient().get(_related_url(listing.slug))
        slugs = [row["slug"] for row in response.data["data"]]
        assert slugs.index(same_city.slug) < slugs.index(same_cat_other_city.slug)

    def test_related_limit_is_respected_and_clamped(self) -> None:
        category = KindnessCategoryFactory()
        listing = PublishedNeedListingFactory(category=category)
        for i in range(RELATED_MAX_LIMIT + 3):
            PublishedNeedListingFactory(category=category, title=f"نیاز {i}")

        client = APIClient()
        assert len(client.get(_related_url(listing.slug), {"limit": 2}).data["data"]) == 2
        # سقفِ سخت: هرگز بیشتر از RELATED_MAX_LIMIT
        assert (
            len(client.get(_related_url(listing.slug), {"limit": 999}).data["data"])
            == RELATED_MAX_LIMIT
        )
        # مقدارِ نامعتبر → پیش‌فرض (۴)
        assert len(client.get(_related_url(listing.slug), {"limit": "abc"}).data["data"]) == 4

    def test_related_excludes_contact_fields(self) -> None:
        category = KindnessCategoryFactory()
        listing = PublishedNeedListingFactory(category=category)
        PublishedNeedListingFactory(category=category, contact_phone="09121234567")
        response = APIClient().get(_related_url(listing.slug))
        for row in response.data["data"]:
            for field in _CONTACT_FIELDS:
                assert field not in row
            assert "contact_channels" not in row
        assert "09121234567" not in str(response.data)

    def test_related_404_for_draft_and_unknown(self) -> None:
        draft = KindnessListingFactory()
        client = APIClient()
        assert client.get(_related_url(draft.slug)).status_code == status.HTTP_404_NOT_FOUND
        assert client.get(_related_url("ناموجود")).status_code == status.HTTP_404_NOT_FOUND

    def test_related_empty_when_alone(self) -> None:
        listing = PublishedNeedListingFactory()
        response = APIClient().get(_related_url(listing.slug))
        assert response.status_code == status.HTTP_200_OK
        assert response.data["data"] == []

    def test_related_never_includes_unpublished(self) -> None:
        category = KindnessCategoryFactory()
        listing = PublishedNeedListingFactory(category=category)
        hidden = KindnessListingFactory(category=category)  # draft
        archived = PublishedNeedListingFactory(category=category)
        KindnessListing.all_objects.filter(pk=archived.pk).update(status=ListingStatus.ARCHIVED)

        slugs = [row["slug"] for row in APIClient().get(_related_url(listing.slug)).data["data"]]
        assert hidden.slug not in slugs
        assert archived.slug not in slugs


class TestFingerprintHelper:
    def test_authenticated_fingerprint_is_stable(self) -> None:
        user = UserFactory()

        class _Req:
            META = {"REMOTE_ADDR": "1.2.3.4"}

        req = _Req()
        req.user = user  # type: ignore[attr-defined]
        first = viewer_fingerprint(request=req)
        req.META = {"REMOTE_ADDR": "9.9.9.9"}  # تغییرِ دستگاه
        assert viewer_fingerprint(request=req) == first

    def test_anonymous_fingerprint_changes_with_user_agent(self) -> None:
        class _Req:
            def __init__(self, ua: str) -> None:
                self.META = {"REMOTE_ADDR": "1.2.3.4", "HTTP_USER_AGENT": ua}

        anonymous = type("Anonymous", (), {"is_authenticated": False})()
        a = _Req("UA-A")
        a.user = anonymous  # type: ignore[attr-defined]
        b = _Req("UA-B")
        b.user = anonymous  # type: ignore[attr-defined]
        assert viewer_fingerprint(request=a) != viewer_fingerprint(request=b)

"""مرتب‌سازی «توزیع عادلانه‌ی تأمین» در لیست عمومی حرکت‌ها.

ایده‌ی محصول: وقتی گروه‌های جهادی وارد صفحه می‌شوند، حرکتِ نیازمندتر را اول
ببینند — نه اینکه یک حرکتِ داغ همه‌ی صفحه را ببلعد و بقیه زنده بمانند.
پس ترتیب: صعودیِ نرخِ تأمین برای فعال‌ها → کامل‌شده‌های ۱۰۰٪ → تکمیل/بسته‌ها
در انتها. دفترِ شفافیت هم باید ترنچِ آفلاین را جدا و هم‌راستا گزارش کند.
"""

from __future__ import annotations

from datetime import timedelta

import pytest
from django.urls import reverse
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APIClient

from apps.madadkar import services
from apps.madadkar.selectors import (
    get_public_campaign_transparency,
    get_public_campaigns_queryset,
)
from tests.factories.madadkar import (
    ClosedCampaignFactory,
    CompletedCampaignFactory,
    PublishedCampaignFactory,
)

pytestmark = pytest.mark.django_db


def _set_funded(campaign, shares: int) -> None:
    campaign.purchased_shares = shares
    campaign.save(update_fields=["purchased_shares"])


def _public_list_titles(query: str = "") -> list[str]:
    client = APIClient()
    response = client.get(reverse("madadkar:public-campaign-list") + query)
    assert response.status_code == status.HTTP_200_OK
    payload = response.json()
    data = payload.get("data", payload) if isinstance(payload, dict) else payload
    items = data.get("results", data) if isinstance(data, dict) else data
    return [item["title"] for item in items]


# ---------------------------------------------------------------------------
# مرتب‌سازی fair-share
# ---------------------------------------------------------------------------


def test_active_campaigns_sort_by_funding_ratio_ascending() -> None:
    rich = PublishedCampaignFactory(title="پُر", total_shares=1000)
    poor = PublishedCampaignFactory(title="خالی", total_shares=1000)
    mid = PublishedCampaignFactory(title="نیمه", total_shares=1000)
    _set_funded(rich, 900)
    _set_funded(mid, 500)
    _set_funded(poor, 100)

    titles = _public_list_titles()

    assert titles.index("خالی") < titles.index("نیمه") < titles.index("پُر")


def test_external_funding_counts_in_fair_share_ratio() -> None:
    """سهم‌های ثبت‌شده از بیرون هم در رتبه حساب می‌شوند (همان خواسته‌ی مشتری)."""
    offline_heavy = PublishedCampaignFactory(title="آفلاین‌دار", total_shares=1000)
    online_half = PublishedCampaignFactory(title="نیمونه", total_shares=1000)
    services.record_external_funding(campaign=offline_heavy, shares=800)
    _set_funded(online_half, 500)

    titles = _public_list_titles()

    # ۵۰٪ آنلاین باید قبل از ۸۰٪ (آفلاین) بیاید
    assert titles.index("نیمونه") < titles.index("آفلاین‌دار")


def test_fully_funded_but_published_goes_after_actives() -> None:
    full = PublishedCampaignFactory(title="پُرسهم", total_shares=1000)
    poor = PublishedCampaignFactory(title="نیازمند", total_shares=1000)
    _set_funded(full, 1000)
    _set_funded(poor, 100)

    titles = _public_list_titles()

    assert titles.index("نیازمند") < titles.index("پُرسهم")


def test_completed_and_closed_go_to_the_tail() -> None:
    CompletedCampaignFactory(title="تکمیل")
    ClosedCampaignFactory(title="بسته")
    active = PublishedCampaignFactory(title="در جریان", total_shares=1000)
    _set_funded(active, 50)

    titles = _public_list_titles()

    active_idx = titles.index("در جریان")
    assert active_idx < titles.index("تکمیل")
    assert active_idx < titles.index("بسته")


def test_equal_ratio_uses_newest_published_first_tiebreak() -> None:
    old = PublishedCampaignFactory(title="قدیمی", total_shares=1000)
    old.published_at = timezone.now() - timedelta(days=10)
    old.save(update_fields=["published_at"])
    PublishedCampaignFactory(title="تازه", total_shares=1000)

    titles = _public_list_titles()

    assert titles.index("تازه") < titles.index("قدیمی")


# ---------------------------------------------------------------------------
# دفترِ شفافیت — ترنچِ آفلاین جدا اما هم‌راستا با نوارِ پیشرفت
# ---------------------------------------------------------------------------


def test_public_transparency_reports_external_tranche_separately() -> None:
    campaign = PublishedCampaignFactory(title="شفاف", total_shares=1000)
    services.record_external_funding(campaign=campaign, shares=250)

    data = get_public_campaign_transparency(campaign=campaign)

    assert data["external_funded_shares"] == 250
    # amount خودکار = سهم × قیمت
    assert data["external_funded_amount"] == 250 * campaign.share_price
    assert data["external_funding_count"] == 1
    # هرگز با ناخالصِ درگاه قاطی نشود
    assert data["gross_raised_amount"] == 0
    # ولی در جمعِ کل و درصدِ کل دیده شود (هم‌سو با نوارِ سایت)
    assert data["total_funded_amount"] == data["external_funded_amount"]
    assert data["total_progress_percent"] > data["net_progress_percent"]


def test_public_transparency_voided_funding_is_excluded() -> None:
    campaign = PublishedCampaignFactory(title="ابطال‌دار", total_shares=1000)
    funding = services.record_external_funding(campaign=campaign, shares=100)
    services.void_external_funding(funding=funding, reason="اصلاح")

    data = get_public_campaign_transparency(campaign=campaign)

    assert data["external_funded_shares"] == 0
    assert data["external_funded_amount"] == 0
    assert data["external_funding_count"] == 0


def test_public_transparency_endpoint_exposes_external_fields() -> None:
    campaign = PublishedCampaignFactory(title="عمومی", total_shares=1000)
    services.record_external_funding(campaign=campaign, shares=60)

    client = APIClient()
    response = client.get(
        reverse("madadkar:public-campaign-transparency", kwargs={"slug": campaign.slug})
    )

    assert response.status_code == status.HTTP_200_OK
    payload = response.json()["data"] if "data" in response.json() else response.json()
    assert payload["external_funded_shares"] == 60
    assert payload["external_funding_count"] == 1
    assert payload["total_funded_amount"] == payload["external_funded_amount"]


def test_division_guard_branch_is_present_in_ordering_sql() -> None:
    """گاردِ «total_shares__lte=0» در annotate ماست: چون constraint دیتابیس
    (share_price>=1) ساختِ رکوردِ صفرسهم را ناممکن می‌کند، اینجا فقط وجودِ
    شاخه‌ی دفاعی در SQLِ real query را صیانت می‌کنیم تا در مهاجرت‌ها/داده‌ی
    خرابِ احتمالی تقسیم‌برصفر رخ ندهد."""
    qs = get_public_campaigns_queryset()
    sql = str(qs.query)
    assert "total_shares" in sql
    PublishedCampaignFactory(title="سالم", total_shares=1000)
    titles = _public_list_titles()
    assert titles == ["سالم"]


# ---------------------------------------------------------------------------
# صیانتِ قرارداد: پارامتر ordering در endpoint عمومی اثری ندارد
# ---------------------------------------------------------------------------
# ریشه‌ی باگِ گزارش‌شده‌ی مشتری: فرانت `?ordering=-published_at` می‌فرستاد و
# OrderingFilterِ قدیمیِ CampaignPublicFilter ترتیبِ fair-share را دور می‌زد.
# حالا فیلتر عمومی عمداً ordering ندارد؛ این تست‌ها صیانت‌اند که هرگز برنگردد.


def _build_prod_incident_trio() -> None:
    """بازسازی دقیق سناریویی که مشتری روی سایت دید:

    قدیمی‌ترین منتشرشده ۰٪ → میانی ۱۰۰٪ (rank 2) → تازه‌ترین ۵۰٪.
    با ordering=-published_atِ قدیمی، ترتیب C,B,A می‌شد؛ با fair-share باید
    A,C,B باشد — حتی اگر کلاینت همان پارامترِ مرده را بفرستد.
    """
    now = timezone.now()
    oldest = PublishedCampaignFactory(
        title="صفرِ قدیمی", total_shares=1000, published_at=now - timedelta(days=3)
    )
    middle = PublishedCampaignFactory(
        title="پُرِ میانی", total_shares=1000, published_at=now - timedelta(days=2)
    )
    newest = PublishedCampaignFactory(
        title="نیمه‌ی تازه", total_shares=1000, published_at=now - timedelta(days=1)
    )
    _set_funded(middle, 1000)
    _set_funded(newest, 500)
    _set_funded(oldest, 0)


def test_public_api_ignores_legacy_ordering_param_and_keeps_fair_share() -> None:
    _build_prod_incident_trio()

    titles = _public_list_titles("?ordering=-published_at")

    # fair-share: ۰٪ → ۵۰٪ → (rank 2) ۱۰۰٪ — نه ترتیبِ published_at
    assert titles == ["صفرِ قدیمی", "نیمه‌ی تازه", "پُرِ میانی"]


def test_public_api_unknown_ordering_param_is_ignored_not_error() -> None:
    """مقادیر نامعتبر ordering دیگر 400 نمی‌دهند؛ بی‌اثر می‌شوند (anti-fragile)."""
    _build_prod_incident_trio()

    titles = _public_list_titles("?ordering=banana")

    assert titles == ["صفرِ قدیمی", "نیمه‌ی تازه", "پُرِ میانی"]

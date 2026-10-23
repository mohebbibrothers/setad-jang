"""تست‌های «تأمین خارج از سایت» (پویش آفلاین — ExternalFunding).

پوشش:
    - ثبت رکورد: شمارنده‌ها، remaining/progress/funded، snapshot قیمت
    - سقف ترکیبی (آنلاین + آفلاین): هیچ‌وقت از کل سهم‌ها رد نمی‌شود
    - ابطال (storno): بازگشت شمارنده‌ها + بقای سند، بدون حذف فیزیکی
    - تکمیل خودکار وقتی تأمین آفلاین حرکت را پر می‌کند
    - یکی‌سازی با مسیر خرید آنلاین: رزرو سهم آفلاین‌خورده ناممکن است
    - خروجی سریالایزر عمومی + رویداد invalidate کش (به‌روزرسانی زنده‌ی سایت)
    - فرم ادمین: پیام‌های فارسیِ دقیق روی خطاها
"""

from __future__ import annotations

import pytest
from django.core.exceptions import ValidationError

from apps.core.models import CacheInvalidationEvent
from apps.madadkar import services
from apps.madadkar.choices import CampaignStatus, ExternalFundingStatus
from apps.madadkar.forms import ExternalFundingAddForm
from apps.madadkar.models import ExternalFunding
from apps.madadkar.serializers import CampaignPublicListSerializer
from tests.factories.auth import UserFactory
from tests.factories.madadkar import CampaignFactory, PublishedCampaignFactory

pytestmark = pytest.mark.django_db


# ---------------------------------------------------------------------------
# ثبت رکورد
# ---------------------------------------------------------------------------


def test_record_external_funding_updates_counters_and_properties():
    campaign = PublishedCampaignFactory(total_amount=10_000_000_000, total_shares=1000)

    funding = services.record_external_funding(campaign=campaign, shares=100)

    campaign.refresh_from_db()
    assert funding.status == ExternalFundingStatus.RECORDED
    assert campaign.external_funded_shares == 100
    assert campaign.external_funded_amount == 100 * campaign.share_price
    assert campaign.funded_shares == 100
    assert campaign.remaining_shares == 900
    assert campaign.progress_percent == 10.0
    assert not campaign.is_fully_funded


def test_amount_defaults_to_shares_times_price_and_snapshot_frozen():
    campaign = PublishedCampaignFactory(total_amount=10_000_000_000, total_shares=1000)
    price_before = campaign.share_price

    funding = services.record_external_funding(campaign=campaign, shares=40)

    assert funding.share_price_snapshot == price_before
    assert funding.amount == 40 * price_before


def test_explicit_amount_is_kept_but_required_positive():
    campaign = PublishedCampaignFactory()
    funding = services.record_external_funding(campaign=campaign, shares=10, amount=123_456)
    assert funding.amount == 123_456

    with pytest.raises(ValidationError, match="صفر یا منفی"):
        services.record_external_funding(campaign=campaign, shares=5, amount=0)


def test_record_requires_at_least_one_share():
    campaign = PublishedCampaignFactory()
    with pytest.raises(ValidationError, match="حداقل ۱"):
        services.record_external_funding(campaign=campaign, shares=0)


# ---------------------------------------------------------------------------
# سقف ترکیبی — oversell ناممکن
# ---------------------------------------------------------------------------


def test_record_overflow_beyond_total_is_rejected_and_persists_nothing():
    campaign = PublishedCampaignFactory(total_shares=1000)

    with pytest.raises(ValidationError, match="سقف سهم قابل ثبت"):
        services.record_external_funding(campaign=campaign, shares=1001)

    campaign.refresh_from_db()
    assert campaign.external_funded_shares == 0
    assert ExternalFunding.objects.count() == 0


def test_online_purchase_guard_respects_offline_reserved_shares():
    campaign = PublishedCampaignFactory(total_shares=1000)
    services.record_external_funding(campaign=campaign, shares=950)
    user = UserFactory()

    # reserve خدماتکننده‌ی داخلیِ مسیر خرید آنلاین است — باید remaining=50 را ببیند
    with pytest.raises(services.InsufficientSharesError, match="باقی‌مانده"):
        services._reserve_participation_shares(campaign=campaign, user=user, share_count=100)

    # ولی ۵۰ سهم نهایی هنوز به‌صورت آنلاین قابل رزرو است
    participation = services._reserve_participation_shares(
        campaign=campaign, user=user, share_count=50
    )
    assert participation.share_count == 50
    campaign.refresh_from_db()
    assert campaign.remaining_shares == 0
    assert campaign.is_fully_funded


# ---------------------------------------------------------------------------
# ابطال
# ---------------------------------------------------------------------------


def test_void_reverts_counters_and_keeps_document():
    campaign = PublishedCampaignFactory()
    funding = services.record_external_funding(campaign=campaign, shares=100)

    funding = services.void_external_funding(funding=funding, reason="ثبت اشتباه تستی")

    campaign.refresh_from_db()
    assert funding.status == ExternalFundingStatus.VOIDED
    assert funding.voided_at is not None
    assert funding.void_reason
    assert campaign.external_funded_shares == 0
    assert campaign.external_funded_amount == 0
    assert campaign.remaining_shares == 1000
    # سند باقی است — حذفِ فیزیکی پیش نیامده
    assert ExternalFunding.objects.filter(pk=funding.pk).exists()


def test_void_twice_is_rejected():
    campaign = PublishedCampaignFactory()
    funding = services.record_external_funding(campaign=campaign, shares=10)
    services.void_external_funding(funding=funding)

    with pytest.raises(ValidationError, match="قبلاً باطل"):
        services.void_external_funding(funding=funding)


# ---------------------------------------------------------------------------
# چرخه‌ی عمر حرکت
# ---------------------------------------------------------------------------


def test_auto_completes_when_offline_fills_the_campaign():
    campaign = PublishedCampaignFactory(total_shares=1000)

    services.record_external_funding(campaign=campaign, shares=1000)

    campaign.refresh_from_db()
    assert campaign.status == CampaignStatus.COMPLETED
    assert campaign.completed_at is not None
    assert campaign.progress_percent == 100.0


def test_recording_on_completed_campaign_is_rejected():
    campaign = PublishedCampaignFactory()
    campaign.status = CampaignStatus.COMPLETED
    campaign.save(update_fields=["status"])

    with pytest.raises(ValidationError, match="فقط برای حرکت"):
        services.record_external_funding(campaign=campaign, shares=1)


def test_recording_on_draft_campaign_is_allowed():
    campaign = CampaignFactory(status=CampaignStatus.DRAFT)

    services.record_external_funding(campaign=campaign, shares=25)

    campaign.refresh_from_db()
    assert campaign.external_funded_shares == 25


# ---------------------------------------------------------------------------
# خروجی عمومی + به‌روزرسانی زنده‌ی سایت
# ---------------------------------------------------------------------------


def test_public_serializer_exposes_offline_funding_fields():
    campaign = PublishedCampaignFactory(total_shares=1000)
    services.record_external_funding(campaign=campaign, shares=200)

    campaign.refresh_from_db()
    data = CampaignPublicListSerializer(campaign).data

    assert data["external_funded_shares"] == 200
    assert data["external_funded_amount"] == 200 * campaign.share_price
    assert data["funded_shares"] == 200
    assert data["remaining_shares"] == 800
    assert data["progress_percent"] == 20.0


@pytest.mark.django_db(transaction=True)
def test_recording_fires_public_cache_invalidation_for_madadkar():
    campaign = PublishedCampaignFactory()
    CacheInvalidationEvent.objects.all().delete()

    services.record_external_funding(campaign=campaign, shares=10)

    assert CacheInvalidationEvent.objects.filter(domain="madadkar").count() == 1


# ---------------------------------------------------------------------------
# فرم ادمین
# ---------------------------------------------------------------------------


def test_admin_form_blocks_overflow_with_friendly_message():
    campaign = PublishedCampaignFactory(total_shares=1000)

    form = ExternalFundingAddForm(
        data={
            "campaign": campaign.pk,
            "shares": 1001,
            "amount": "",
            "method": "card_transfer",
            "reference": "",
            "funded_at": "2026-10-23 10:00:00",
            "note": "",
        }
    )

    assert not form.is_valid()
    assert "سقف قابل ثبت" in form.errors["shares"][0]


def test_admin_form_accepts_valid_input():
    campaign = PublishedCampaignFactory(total_shares=1000)

    form = ExternalFundingAddForm(
        data={
            "campaign": campaign.pk,
            "shares": 250,
            "amount": "",
            "method": "cash",
            "reference": "TRX-123",
            "funded_at": "2026-10-23 10:00:00",
            "note": "دریافت حضوری دفتر",
        }
    )

    assert form.is_valid(), form.errors


# ---------------------------------------------------------------------------
# ترکیب آنلاین + آفلاین در progress (پایداری regresion)
# ---------------------------------------------------------------------------


def test_progress_combines_online_and_offline_shares():
    campaign = PublishedCampaignFactory(total_shares=1000)
    services.record_external_funding(campaign=campaign, shares=100)

    campaign.purchased_shares = 300
    campaign.save(update_fields=["purchased_shares"])

    campaign.refresh_from_db()
    assert campaign.funded_shares == 400
    assert campaign.progress_percent == 40.0
    assert campaign.remaining_shares == 600

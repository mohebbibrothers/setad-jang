"""بازتولیدِ مسیر واقعیِ کاربر ادمین برای «تأمین خارج از سایت».

این تست‌ها دقیقاً همان کاری را می‌کنند که ادمین در مرورگر انجام می‌دهد
(ورود → باز کردن صفحه‌ی افزودن/ویرایش → POST واقعی) تا باگ‌های ۵۰۰
پنل — از جنس اشتباهات UI-level مثل fieldset/formset — قبل از رسیدن به
پروداکشن شکار شوند.
"""

from __future__ import annotations

import pytest
from django.test import Client, override_settings
from django.urls import reverse
from django.utils import timezone

from apps.madadkar.choices import ExternalFundingStatus
from apps.madadkar.forms import jalali_to_gregorian
from apps.madadkar.models import ExternalFunding
from tests.factories.auth import UserFactory
from tests.factories.madadkar import PublishedCampaignFactory

pytestmark = pytest.mark.django_db


def _admin_client() -> Client:
    admin = UserFactory(is_staff=True, is_superuser=True)
    client = Client()
    client.force_login(admin)
    return client


FUNDED_AT_VALUE = "2026-10-23 10:00:00"


@override_settings(ALLOWED_HOSTS=["*"])
def test_standalone_add_page_get_is_200():
    campaign = PublishedCampaignFactory()
    client = _admin_client()

    url = reverse("admin:madadkar_externalfunding_add")
    response = client.get(url + f"?campaign={campaign.pk}")

    assert response.status_code == 200


@override_settings(ALLOWED_HOSTS=["*"])
def test_standalone_add_post_creates_record_and_redirects():
    campaign = PublishedCampaignFactory()
    client = _admin_client()

    url = reverse("admin:madadkar_externalfunding_add")
    response = client.post(
        url,
        data={
            "campaign": str(campaign.pk),
            "shares": "12",
            "amount": "",
            "method": "card_transfer",
            "reference": "",
            "funded_at": FUNDED_AT_VALUE,
            "note": "",
            "_save": "ذخیره",
        },
        follow=False,
    )

    assert response.status_code in (302, 303), (
        f"admin add POST باید ریدایرکت شود نه {response.status_code}"
    )
    funding = ExternalFunding.objects.get()
    assert funding.shares == 12
    campaign.refresh_from_db()
    assert campaign.external_funded_shares == 12


@override_settings(ALLOWED_HOSTS=["*"])
def test_campaign_page_inline_post_creates_record_and_redirects():
    campaign = PublishedCampaignFactory(title="حرکت واقعی", description="توضیح")
    client = _admin_client()

    url = reverse("admin:madadkar_campaign_change", args=[campaign.pk])
    response = client.post(
        url,
        data={
            # فیلدهای اجباری کمپین
            "sponsor": str(campaign.sponsor_id),
            "title": "حرکت واقعی",
            "description": "توضیح",
            "total_amount": str(campaign.total_amount),
            "total_shares": str(campaign.total_shares),
            "status": campaign.status,
            "has_deadline": "",
            "is_visible": "on",
            "is_active": "on",
            # مدیریت‌فرم اینلاین تصاویر (پریفیکس = related_name گالری)
            "gallery_images-TOTAL_FORMS": "0",
            "gallery_images-INITIAL_FORMS": "0",
            "gallery_images-MIN_NUM_FORMS": "0",
            "gallery_images-MAX_NUM_FORMS": "1000",
            # مدیریت‌فرم اینلاین تأمین خارجی + یک ردیف جدید
            "external_fundings-TOTAL_FORMS": "1",
            "external_fundings-INITIAL_FORMS": "0",
            "external_fundings-MIN_NUM_FORMS": "0",
            "external_fundings-MAX_NUM_FORMS": "1000",
            "external_fundings-0-shares": "7",
            "external_fundings-0-amount": "",
            "external_fundings-0-method": "cash",
            "external_fundings-0-reference": "",
            "external_fundings-0-funded_at": FUNDED_AT_VALUE,
            "external_fundings-0-note": "",
            "_save": "ذخیره",
        },
        follow=False,
    )

    assert response.status_code in (302, 303), (
        f"save کمپین با اینلاین تأمین باید ریدایرکت شود نه {response.status_code}"
    )
    funding = ExternalFunding.objects.get()
    assert funding.shares == 7
    assert funding.method == "cash"
    campaign.refresh_from_db()
    assert campaign.external_funded_shares == 7


@override_settings(ALLOWED_HOSTS=["*"])
def test_standalone_add_post_jalali_persian_digits_date_parses():
    campaign = PublishedCampaignFactory()
    client = _admin_client()

    url = reverse("admin:madadkar_externalfunding_add")
    response = client.post(
        url,
        data={
            "campaign": str(campaign.pk),
            "shares": "3",
            "amount": "",
            "method": "internal",
            "reference": "",
            "funded_at": "۱۴۰۵/۰۸/۰۱ ۱۲:۳۰",
            "note": "",
            "_save": "ذخیره",
        },
        follow=False,
    )

    assert response.status_code in (302, 303)
    funding = ExternalFunding.objects.get()
    local = timezone.localtime(funding.funded_at)
    assert (local.year, local.month, local.day) == (2026, 10, 23)
    assert (local.hour, local.minute) == (12, 30)


@override_settings(ALLOWED_HOSTS=["*"])
def test_standalone_add_post_empty_funded_at_defaults_to_now():
    campaign = PublishedCampaignFactory()
    client = _admin_client()

    url = reverse("admin:madadkar_externalfunding_add")
    response = client.post(
        url,
        data={
            "campaign": str(campaign.pk),
            "shares": "4",
            "amount": "",
            "method": "cash",
            "reference": "",
            "funded_at": "",
            "note": "",
            "_save": "ذخیره",
        },
        follow=False,
    )

    assert response.status_code in (302, 303)
    funding = ExternalFunding.objects.get()
    assert abs((timezone.now() - funding.funded_at).total_seconds()) < 60


@override_settings(ALLOWED_HOSTS=["*"])
def test_standalone_add_post_reference_and_note_are_optional():
    campaign = PublishedCampaignFactory()
    client = _admin_client()

    url = reverse("admin:madadkar_externalfunding_add")
    response = client.post(
        url,
        data={
            "campaign": str(campaign.pk),
            "shares": "2",
            "amount": "",
            "method": "card_transfer",
            "funded_at": "",
            "_save": "ذخیره",
        },
        follow=False,
    )

    assert response.status_code in (302, 303)
    funding = ExternalFunding.objects.get()
    assert funding.reference == ""
    assert funding.note == ""


@override_settings(ALLOWED_HOSTS=["*"])
def test_standalone_add_get_shows_remaining_guidance_for_prefilled_campaign():
    campaign = PublishedCampaignFactory(total_shares=1000)
    client = _admin_client()

    url = reverse("admin:madadkar_externalfunding_add")
    response = client.get(url + f"?campaign={campaign.pk}")

    assert response.status_code == 200
    assert "باقی‌مانده‌ی قابل ثبت" in response.content.decode()


@override_settings(ALLOWED_HOSTS=["*"])
def test_campaign_change_page_inline_shows_remaining_guidance():
    campaign = PublishedCampaignFactory(total_shares=1000)
    client = _admin_client()

    url = reverse("admin:madadkar_campaign_change", args=[campaign.pk])
    response = client.get(url)

    assert response.status_code == 200
    assert "باقی‌مانده‌ی قابل ثبت" in response.content.decode()
    assert "1000" in response.content.decode()


@override_settings(ALLOWED_HOSTS=["*"])
def test_changelist_shows_offline_funding_shortcut_button():
    campaign = PublishedCampaignFactory()
    client = _admin_client()

    url = reverse("admin:madadkar_campaign_changelist")
    response = client.get(url)

    assert response.status_code == 200
    body = response.content.decode()
    assert "ثبت تأمین خارجی" in body
    assert f"?campaign={campaign.pk}" in body


def test_changelist_never_uses_date_hierarchy_mysql_tz_guard():
    """گاردِ رگرسیون برای باگ ۵۰۰ پروداکشن.

    date_hierarchy روی MySQL/MariaDB به CONVERT_TZ وابسته است و روی هاست
    اشتراکیِ بدون جداول time_zone به ValueError («Are time zone definitions
    ... installed?») و صفحه‌ی ۵۰۰ منجر می‌شود — در ۶.‌این پنل جای آن
    DateFieldListFilter است (فیلتر WHERE بدون تبدیل مقدار برگشتی).
    هرگز date_hierarchy را برنگردان.
    """
    from apps.madadkar.admin import ExternalFundingAdmin

    assert getattr(ExternalFundingAdmin, "date_hierarchy", None) is None

    filter_keys = [f[0] if isinstance(f, tuple) else f for f in ExternalFundingAdmin.list_filter]
    assert "funded_at" in filter_keys


def test_jalali_to_gregorian_reference_dates():
    assert jalali_to_gregorian(1405, 8, 1) == (2026, 10, 23)
    assert jalali_to_gregorian(1403, 12, 30) == (2025, 3, 20)


def test_jalali_to_gregorian_leap_year():
    # ۱۴۰۳ کبیسه است — ۳۰ اسفند معتبر و آخرین روز سال
    assert jalali_to_gregorian(1403, 12, 29) == (2025, 3, 19)
    assert jalali_to_gregorian(1404, 12, 30) == (2026, 3, 21)


@override_settings(ALLOWED_HOSTS=["*"])
def test_void_action_via_changelist_updates_counters():
    from apps.madadkar import services

    campaign = PublishedCampaignFactory()
    funding = services.record_external_funding(campaign=campaign, shares=9)
    client = _admin_client()

    url = reverse("admin:madadkar_externalfunding_changelist")
    response = client.post(
        url,
        data={"action": "void_selected", "_selected_action": [str(funding.pk)]},
        follow=False,
    )

    assert response.status_code in (302, 303)
    funding.refresh_from_db()
    assert funding.status == ExternalFundingStatus.VOIDED
    campaign.refresh_from_db()
    assert campaign.external_funded_shares == 0

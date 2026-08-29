"""گیت داکیومنت API در production (یافتهٔ P1-۴ فاز ۷).

سه قرارداد:
- production + ناشناس → redirect به لاگین ادمین (نه 200، نه schema).
- production + staff → دسترسی کامل؛ flag API_DOCS_ALLOW_ANONYMOUS هم
  مسیر عمومیِ *عمدی* را باز می‌کند.
- contact schema هیچ ایمیل شخصی برنمی‌گرداند (regression برای gmailِ
  قدیمی که در فایل public commit شده بود).
"""

from __future__ import annotations

import pytest
from django.conf import settings as dj_settings
from django.urls import reverse

pytestmark = pytest.mark.django_db

_DOC_PATHS = ("/api/schema/", "/api/docs/", "/api/redoc/")


@pytest.mark.parametrize("path", _DOC_PATHS)
def test_anonymous_blocked_in_production(client, path, settings) -> None:
    """ناشناس نباید حتی بداند schema کجاست؛ redirect به login یعنی همان."""
    settings.DEBUG = False
    settings.API_DOCS_ALLOW_ANONYMOUS = False

    response = client.get(path)
    assert response.status_code == 302
    assert response["Location"].startswith(reverse("admin:login"))
    assert "next=" in response["Location"]  # بازگشت‌پذیری بعد از لاگین حفظ شود


@pytest.mark.parametrize("path", _DOC_PATHS)
def test_staff_can_access_in_production(admin_user, client, path, settings) -> None:
    """member تیم پس از لاگینِ سشنی، همان تجربهٔ قبلی را دارد.

    عمداً force_login (session) — گیت روی request.userِ احرازهویت‌شدهٔ
    مرورگر کار می‌کند، نه توکن API؛ این خودِ قراردادِ استفاده است.
    """
    settings.DEBUG = False
    settings.API_DOCS_ALLOW_ANONYMOUS = False

    client.force_login(admin_user)
    assert client.get(path).status_code == 200


def test_anonymous_flag_opens_docs_deliberately(client, settings) -> None:
    """flag صریح = پذیرش عمومی؛ باید کار کند (اپراتورِ آگاه قفل نمی‌شود)."""
    settings.DEBUG = False
    settings.API_DOCS_ALLOW_ANONYMOUS = True

    assert client.get("/api/schema/").status_code == 200


def test_debug_environment_stays_open(client, settings) -> None:
    """dev/test با DEBUG باز نباید ceremonial احراز هویت بخواهد."""
    settings.DEBUG = True
    settings.API_DOCS_ALLOW_ANONYMOUS = False

    assert client.get("/api/schema/").status_code == 200


def test_contact_email_is_organizational_not_personal() -> None:
    """regression: ایمیل شخصی در schema عمومی، P1-4 فاز ۷ (افشای contact)."""
    email = dj_settings.SPECTACULAR_SETTINGS["CONTACT"]["email"]
    assert email
    assert "gmail.com" not in email
    assert email == dj_settings.API_CONTACT_EMAIL

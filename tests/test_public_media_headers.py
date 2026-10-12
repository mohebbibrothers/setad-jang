"""هدرهای کشِ سروِ رسانه‌ی عمومی (apps/core/public_media.py).

انگیزه (SEO/Core Web Vitals): رسانه‌ی عمومی — کاورِ دوره، عکس پرونده‌های
R4J، فریم‌های رندر PDF — باید با Cache-Controlِ بلندمدتِ public سرو شود
تا بازدیدِ دومِ کاربر از کَشِ مرورگر بیاید و LCP کمینه شود؛ ولی immutable
عمدی نیست چون احتمالِ «جایگزینیِ فایلِ هم‌نام» وجود دارد و باید یک
پنجره‌ی بهنگام‌سازی (SWR) باز بماند.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from django.test import Client, override_settings
from django.urls import path

from apps.core.public_media import serve_public_media

pytestmark = pytest.mark.django_db

# چرا urlconf محلی؟ روتِ «media/public/<path:path>» در config/urls.py عمداً
# زمانِ import و فقط اگر SERVE_PUBLIC_MEDIA=True باشد ساخته می‌شود (امنیت:
# به‌طور پیش‌فرض بسته). در سوئیتِ کامل، تست‌های قبلی urlconf را خیلی قبل‌تر
# با پرچمِ پیش‌فرضِ False ایمپورت می‌کنند و روت هرگز ساخته نمی‌شود؛ برای
# استقلال از ترتیبِ اجرا، همین فایل urlconf اختصاصیِ خودش را می‌سازد.
urlpatterns = [
    path("media/public/<path:path>", serve_public_media, name="public-media"),
]

_MEDIA_URL = "/media/public/probe/cover.png"
_MEDIA_REL = Path("probe") / "cover.png"
_CONTENT = b"fake-png-bytes-for-tests"


@pytest.fixture
def media_root(tmp_path, settings):
    root = tmp_path / "media"
    target = root / "public" / _MEDIA_REL
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(_CONTENT)
    settings.MEDIA_ROOT = root
    return root


@override_settings(
    DEBUG=False,
    SERVE_PUBLIC_MEDIA=True,
    ALLOWED_HOSTS=["*"],
    ROOT_URLCONF=__name__,
)
def test_public_media_sends_long_public_cache_headers(media_root):
    response = Client().get(_MEDIA_URL)
    assert response.status_code == 200
    cache_control = response["Cache-Control"]
    assert "public" in cache_control
    assert "max-age=604800" in cache_control
    assert "stale-while-revalidate" in cache_control
    # immutable عمداً نیست — جایگزینیِ فایلِ هم‌نام باید در پنجره‌ی SWR جبران شود
    assert "immutable" not in cache_control
    assert response["X-Content-Type-Options"] == "nosniff"
    assert b"".join(response.streaming_content) == _CONTENT


@override_settings(
    DEBUG=False,
    SERVE_PUBLIC_MEDIA=True,
    ALLOWED_HOSTS=["*"],
    ROOT_URLCONF=__name__,
)
def test_public_media_404_does_not_gain_cache_header(media_root):
    response = Client().get("/media/public/probe/missing.png")
    assert response.status_code == 404

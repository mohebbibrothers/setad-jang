"""قراردادِ «شکستِ سریع» برای کش (Redisِ در دسترس‌نبودن نباید سایت را کند کند).

روی استقرارِ واقعی، هاست بدونِ Redis بالا آمده بود و `IGNORE_EXCEPTIONS` خطا را
می‌بلعید — ولی هر cache miss تا ~۱ ثانیه منتظرِ تایم‌اوتِ اتصال می‌ماند و لاگ
«Slow request detected … duration_ms=1012» تولید می‌کرد. این تست تضمین می‌کند
که سوکت‌تایم‌اوت‌های کوتاه در تنظیمات باقی بمانند.
"""

from __future__ import annotations

import pytest
from django.conf import settings

pytestmark = pytest.mark.django_db


def test_redis_cache_declares_short_socket_timeouts() -> None:
    """تایم‌اوت‌های کوتاه باید در همان بلوکِ OPTIONSِ کشِ redis باشند."""
    from pathlib import Path

    path = Path(__file__).resolve().parents[3] / "config" / "settings" / "base.py"
    text = path.read_text(encoding="utf-8")
    start = text.index('if CACHE_BACKEND == "redis":')
    end = text.index("else:", start)
    body = text[start:end]
    assert "CACHES = {" in body, "بلوکِ کشِ redis در base.py پیدا نشد"
    assert '"socket_connect_timeout": 0.2' in body or "'socket_connect_timeout': 0.2" in body
    assert '"socket_timeout": 0.2' in body or "'socket_timeout': 0.2" in body


def test_ignored_redis_errors_are_configurable() -> None:
    """اپراتور باید بتواند نویزِ لاگِ Redis را با env خاموش کند."""
    from pathlib import Path

    path = Path(__file__).resolve().parents[3] / "config" / "settings" / "base.py"
    text = path.read_text(encoding="utf-8")
    assert 'config(\n        "DJANGO_REDIS_LOG_IGNORED_EXCEPTIONS"' in text or (
        "DJANGO_REDIS_LOG_IGNORED_EXCEPTIONS" in text
        and 'config("DJANGO_REDIS_LOG_IGNORED_EXCEPTIONS"' in text
    )


def test_settings_still_expose_ignore_exceptions() -> None:
    """رفتارِ «بلعیدنِ خطا» نباید حذف شود؛ وگرنه یک Redisِ خاموش = ۵۰۰."""
    cache_conf = settings.CACHES.get("default", {})
    options = cache_conf.get("OPTIONS", {}) or {}
    if "redis" in str(cache_conf.get("BACKEND", "")):
        assert options.get("IGNORE_EXCEPTIONS") is True
        assert getattr(settings, "DJANGO_REDIS_IGNORE_EXCEPTIONS", False) is True

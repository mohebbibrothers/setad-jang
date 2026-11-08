"""لاگینِ ادمین با کشِ مرده: رمزِ اشتباه باید ۲۰۰ بدهد، نه ۵۰۰.

حادثهٔ واقعی (استقرار بدونِ Redis)
---------------------------------
``django_redis`` با ``IGNORE_EXCEPTIONS=True`` خطا را می‌بلعد و ``cache.incr``
به‌جای استثنا **None** برمی‌گرداند. گاردِ لاگین ادمین مقدار را با آستانه مقایسه
می‌کرد (``None >= 5``) و ``TypeError`` می‌داد. نتیجه، الگویی بود که کاربر دید:

    • رمزِ درست  → 302 → فقط ``cache.delete`` → ورود موفق ✅
    • رمزِ غلط   → 200 → ثبتِ شکست → کرش → **Server Error (500)** ❌

این تست همان سناریو را با کشی بازسازی می‌کند که «هیچ‌وقت نمی‌شمارد» و تضمین
می‌کند ثبتِ آمارِ امنیتی هرگز صفحهٔ لاگین را نشکند.
"""

from __future__ import annotations

import pytest
from django.core.cache.backends.base import BaseCache

from apps.core import admin_guard

pytestmark = pytest.mark.django_db


class DeadCache(BaseCache):
    """کشی که مثل django_redis با IGNORE_EXCEPTIONS رفتار می‌کند: None برمی‌گرداند."""

    def __init__(self) -> None:
        super().__init__({})

    def add(self, key, value, timeout=..., version=None):  # noqa: ANN001
        return None

    def get(self, key, default=None, version=None):  # noqa: ANN001
        return None

    def set(self, key, value, timeout=..., version=None):  # noqa: ANN001
        return None

    def touch(self, key, timeout=..., version=None):  # noqa: ANN001
        return None

    def delete(self, key, version=None):  # noqa: ANN001
        return None

    def get_many(self, keys, version=None):  # noqa: ANN001
        return {}

    def incr(self, key, delta=1, version=None):  # noqa: ANN001
        # مهم‌ترین خطِ این تست: django_redis در همین‌جا None می‌دهد، نه استثنا.
        return None


class ExplodingCache(DeadCache):
    """بدترین حالت: هر عملیات استثنا می‌دهد."""

    def get(self, *a, **kw):  # noqa: ANN002, ANN003
        raise RuntimeError("cache down")

    def set(self, *a, **kw):  # noqa: ANN002, ANN003
        raise RuntimeError("cache down")

    def incr(self, *a, **kw):  # noqa: ANN002, ANN003
        raise RuntimeError("cache down")

    def delete(self, *a, **kw):  # noqa: ANN002, ANN003
        raise RuntimeError("cache down")


@pytest.fixture
def dead_cache(monkeypatch):
    cache = DeadCache()
    monkeypatch.setattr(admin_guard, "cache", cache)
    return cache


@pytest.fixture
def exploding_cache(monkeypatch):
    cache = ExplodingCache()
    monkeypatch.setattr(admin_guard, "cache", cache)
    return cache


def test_record_failure_with_dead_cache_does_not_raise(dead_cache) -> None:
    """هستهٔ باگ: incr → None. نباید TypeError بدهد."""
    request = _post_request("someone@example.com")
    admin_guard.record_admin_login_failure(request)  # هیچ استثنایی نباید بیاید


def test_record_failure_with_exploding_cache_does_not_raise(exploding_cache) -> None:
    admin_guard.record_admin_login_failure(_post_request("someone@example.com"))


def test_lockout_probe_with_dead_cache_reports_unlocked(dead_cache) -> None:
    assert admin_guard.lockout_seconds_left(_post_request("someone@example.com")) == 0


def test_reset_after_success_with_dead_cache_does_not_raise(dead_cache) -> None:
    admin_guard.reset_admin_login_counters(_post_request("someone@example.com"))


def test_wrong_password_returns_200_not_500(client, dead_cache) -> None:
    """تستِ سرتاسری: فرمِ لاگینِ ادمین با اعتبارنامهٔ غلط باید ۲۰۰ بدهد."""
    response = client.post(
        "/admin/login/",
        data={"username": "nobody@example.com", "password": "definitely-wrong", "next": "/admin/"},
        follow=False,
    )
    assert response.status_code == 200, (
        f"لاگینِ ناموفق باید فرم را با ۲۰۰ برگرداند، نه {response.status_code}"
    )


def _post_request(username: str):
    from django.test import RequestFactory

    request = RequestFactory().post("/admin/login/", data={"username": username})
    request.META["REMOTE_ADDR"] = "127.0.0.1"
    return request

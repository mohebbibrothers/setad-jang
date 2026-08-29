"""
تست‌های وضوحِ «IP کلاینت» — قفل‌کردن یافتهٔ P1 ممیزی مستقل (X-Forwarded-For spoofing).

مشکل اثبات‌شده در ممیزی:
    رفتار پیش‌فرض DRF (و کدهای audit/auth پروژه) وقتی `NUM_PROXIES` تنظیم
    نشده باشد، header ورودی `X-Forwarded-For` را **بدون راستی‌آزمایی**
    می‌پذیرد. مهاجم می‌تواند `X-Forwarded-For` را جعل کند و:

    1. سهمیهٔ throttle را با عوض‌کردن یک header دور بزند؛
    2. IP جعلی را وارد audit trail و لاگ‌های امنیتی (وایفای/بلاک‌کردن) کند.

قرارداد این فایل:
    - `NUM_PROXIES` پیش‌فرض پروژه **صفر** است → XFF هرگز معتبر نیست؛
    - `NUM_PROXIES=k>0` → فقط از سمت راستِ زنجیرهٔ XFF و فقط وقتی طول
      زنجیره معتبر است، IP خوانده می‌شود؛ زنجیرهٔ کوتاه/معیوب → fail-closed
      و بازگشت به REMOTE_ADDR (عکس DRF که `addrs[-min(k, len)]` یعنی
      چپ‌ترین = قابل جعل‌ترین مقدار را برمی‌گرداند).
"""

from __future__ import annotations

from django.contrib.auth.models import AnonymousUser
from django.test import override_settings

from apps.audit_logs.helpers import get_client_ip as audit_client_ip
from apps.authentication.services import _get_client_ip as auth_client_ip
from apps.core.throttling import ClientIPRateThrottle, IdentityRateThrottle

_EVIL_XFF = "198.51.100.66, 203.0.113.9"
_REMOTE = "192.0.2.10"


def _throttle(cls):
    """ساخت throttle بدون init (فقط get_ident تست می‌شود؛ rate لازم نیست)."""
    return object.__new__(cls)


class _Request:
    """Double درخواست؛ هم META دارد (مسیر ما)، هم headers (سازگاری DRF)."""

    def __init__(self, *, meta: dict | None = None, headers: dict | None = None) -> None:
        self.user = AnonymousUser()
        self.META = meta or {"REMOTE_ADDR": _REMOTE}
        # DRF 3.18 `get_ident` از request.headers می‌خواند؛ برای اینکه تست
        # روی کد فعلی (قبل از رفع) صادقانه red باشد، XFF باید در هر دو جا باشد.
        if headers is None:
            xff = self.META.get("HTTP_X_FORWARDED_FOR")
            headers = {"x-forwarded-for": xff} if xff else {}
        self.headers = headers


class TestThrottleIdent:
    @override_settings(REST_FRAMEWORK={"NUM_PROXIES": 0})
    def test_num_proxies_zero_ignores_spoofed_xff(self) -> None:
        """با NUM_PROXIES=0 (پیش‌فرض امن پروژه) XFF جعلی نادیده گرفته می‌شود."""
        request = _Request(meta={"REMOTE_ADDR": _REMOTE, "HTTP_X_FORWARDED_FOR": _EVIL_XFF})
        assert _throttle(ClientIPRateThrottle).get_ident(request) == _REMOTE
        assert _throttle(IdentityRateThrottle).get_ident(request) == _REMOTE

    @override_settings(REST_FRAMEWORK={"NUM_PROXIES": None})
    def test_unset_num_proxies_is_still_fail_closed(self) -> None:
        """حتی وقتی NUM_PROXIES اصلاً تنظیم نشده، XFF معتبر نیست (عکس DRF)."""
        request = _Request(meta={"REMOTE_ADDR": _REMOTE, "HTTP_X_FORWARDED_FOR": _EVIL_XFF})
        assert _throttle(ClientIPRateThrottle).get_ident(request) == _REMOTE

    @override_settings(REST_FRAMEWORK={"NUM_PROXIES": 1})
    def test_single_trusted_proxy_reads_last_hop(self) -> None:
        """با یک پراکسی قابل اعتماد، IP کلاینت آخرین مقدار XFF است."""
        request = _Request(
            meta={"REMOTE_ADDR": "10.0.0.1", "HTTP_X_FORWARDED_FOR": "198.51.100.66"}
        )
        assert _throttle(ClientIPRateThrottle).get_ident(request) == "198.51.100.66"

    @override_settings(REST_FRAMEWORK={"NUM_PROXIES": 2})
    def test_two_proxies_read_second_from_right(self) -> None:
        """با دو پراکسی، مقدار دوم از راست (کلاینت واقعی) انتخاب می‌شود.

        زنجیرهٔ XFF=[کلاینت، پراکسی۱] است؛ با k=2 کلاینت = addrs[-2].
        """
        request = _Request(meta={"REMOTE_ADDR": "10.0.0.9", "HTTP_X_FORWARDED_FOR": _EVIL_XFF})
        assert _throttle(ClientIPRateThrottle).get_ident(request) == "198.51.100.66"

    @override_settings(REST_FRAMEWORK={"NUM_PROXIES": 2})
    def test_short_xff_chain_fails_closed(self) -> None:
        """زنجیرهٔ کوتاه‌تر از تعداد پراکسی → بازگشت به REMOTE_ADDR (نه چپ‌ترین)."""
        request = _Request(meta={"REMOTE_ADDR": _REMOTE, "HTTP_X_FORWARDED_FOR": "198.51.100.66"})
        assert _throttle(ClientIPRateThrottle).get_ident(request) == _REMOTE

    @override_settings(REST_FRAMEWORK={"NUM_PROXIES": 1})
    def test_port_is_stripped_from_forwarded_address(self) -> None:
        """پورت در XFF حذف می‌شود (IPv4 و IPv6)."""
        v4 = _Request(
            meta={"REMOTE_ADDR": "10.0.0.1", "HTTP_X_FORWARDED_FOR": "198.51.100.66:8443"}
        )
        assert _throttle(ClientIPRateThrottle).get_ident(v4) == "198.51.100.66"
        v6 = _Request(
            meta={"REMOTE_ADDR": "10.0.0.1", "HTTP_X_FORWARDED_FOR": "[2001:db8::1]:8443"}
        )
        assert _throttle(ClientIPRateThrottle).get_ident(v6) == "2001:db8::1"


class TestAuditAndAuthLogging:
    """لاگ‌های audit/auth هم نباید XFF جعلی را بدون راستی‌آزمایی قبول کنند."""

    @override_settings(REST_FRAMEWORK={"NUM_PROXIES": 0})
    def test_audit_helper_uses_remote_addr_ignoring_xff(self) -> None:
        request = _Request(meta={"REMOTE_ADDR": _REMOTE, "HTTP_X_FORWARDED_FOR": _EVIL_XFF})
        assert audit_client_ip(request) == _REMOTE

    @override_settings(REST_FRAMEWORK={"NUM_PROXIES": 1})
    def test_audit_helper_honours_trusted_proxy(self) -> None:
        request = _Request(
            meta={"REMOTE_ADDR": "10.0.0.1", "HTTP_X_FORWARDED_FOR": "198.51.100.66"}
        )
        assert audit_client_ip(request) == "198.51.100.66"

    @override_settings(REST_FRAMEWORK={"NUM_PROXIES": 0})
    def test_auth_service_helper_ignores_spoofed_xff(self) -> None:
        request = _Request(meta={"REMOTE_ADDR": _REMOTE, "HTTP_X_FORWARDED_FOR": _EVIL_XFF})
        assert auth_client_ip(request=request) == _REMOTE

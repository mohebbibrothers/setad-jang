"""هدرهای امنیتیِ مرورگری برای صفحاتِ HTML (یافتهٔ P2-۹ فاز ۸).

چرا API خالص بدونِ این‌ها «سبز» بود و اینجا لازم:
    ریسکِ CSP/XSS برای JSONِ خالص تقریباً صفر است (مرورگر آن را render نمی‌کند)
    — ولی /admin/ و Swagger/ReDoc صفحاتِ HTML واقعی‌اند. Swagger UI اسکریپتِ
    inline ندارد ولی CDN می‌کشد و ادمین جانگو script/styleِ inline دارد؛
    یعنی CSPِ «سخت» این‌ها را می‌شکند. راه‌حلِ مهندسی: **دو پروفایلِ مجزا**،
    هرکدام دقیقاً به اندازهٔ نیازِ همان صفحه باز، بقیه سفت.

پروفایل‌ها:
    - admin:   script/style 'self' + unsafe-inline (اجبارِ admin جانگو)،
               بدونِ هیچِ origin خارجی؛ frame-ancestors none.
    - docs:    همان اما با originهایِ CDN که واقعاً در تنظیماتِ
               SPECTACULAR (SWAGGER_UI_DIST/REDOC_DIST) آمده‌اند — یعنی اگر
               اپراتور CDN را عوض کند، CSP خودکار هم‌راستا می‌شود؛ CSPِ
               دستیِ جدا = منبعِ drift.

جهانی (روی هر پاسخ):
    - Permissions-Policy: هر capability حساسِ مرورگر بسته — این API
      دوربین/میکروفون/جی‌ال‌اس/پرداخت/سریال/USB نمی‌خواهد و نبودِ هدرِ صریح
      یعنی پیش‌فرضِ «هر سایتی که iframe کند حقِ پرسیدن دارد».
    - COOP از تنظیمِ داخلیِ جانگو (SECURE_CROSS_ORIGIN_OPENER_POLICY) در
      production.py تزریق می‌شود؛ اینجا عمداً تکرار نمی‌کنیم — دو منبع، یک هدر.

حالتِ report-only (SECURE_CSP_ENFORCE=False): برای استقرارِ اولِ CSP روی
سیستمِ زنده — خطاها به /csp-violation/ (اگر وصل شود) گزارش می‌شوند و صفحه
نمی‌شکند؛ بعد از یک چرخه، enforce.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Final
from urllib.parse import urlsplit

from django.conf import settings
from django.http import HttpRequest, HttpResponseBase

#: مسیرهایِ مستندِ HTML که CDNِ خودشان را از تنظیماتِ spectacular می‌خوانند.
DOCS_HTML_PATHS: Final[frozenset[str]] = frozenset({"/api/docs/", "/api/redoc/"})

#: capability‌هایی که صریحاً برای کلِ سامانه بسته‌اند. لیستِ صریحِ سفیدِ معکوس:
#: هر capabilityِ تازه‌ای که مرورگر اضافه کند، پیش‌فرضِ آن «مجاز» است و این
#: هدر فقط مواردِ شناخته‌شده را می‌بندد — به‌روزرسانیِ سالانه لازم است.
_DENIED_FEATURES: Final[tuple[str, ...]] = (
    "accelerometer",
    "ambient-light-sensor",
    "autoplay",
    "camera",
    "display-capture",
    "fullscreen",
    "geolocation",
    "gyroscope",
    "hid",
    "magnetometer",
    "microphone",
    "midi",
    "payment",
    "serial",
    "usb",
    "wake-lock",
)

_PERMISSIONS_POLICY: Final[str] = ", ".join(f"{name}=()" for name in _DENIED_FEATURES)


def _origin_of(dist_url: str) -> str | None:
    """originِ خالصِ یک CDN url برای درج در CSP؛ None یعنی 'self'‌محور."""
    if not dist_url:
        return None
    parts = urlsplit(dist_url)
    if parts.scheme and parts.netloc:
        return f"{parts.scheme}://{parts.netloc}"
    return None


def _spectacular_script_origins() -> str:
    """script/style-src برای صفحاتِ docs: 'self' + CDNهایِ واقعیِ تنظیم‌شده."""
    spectacular = getattr(settings, "SPECTACULAR_SETTINGS", {}) or {}
    origins: list[str] = ["'self'"]
    for key, fallback in (
        ("SWAGGER_UI_DIST", "https://cdn.jsdelivr.net/npm/swagger-ui-dist@latest"),
        ("REDOC_DIST", "https://cdn.jsdelivr.net/npm/redoc@next/bundles/redoc.standalone.js"),
    ):
        origin = _origin_of(str(spectacular.get(key) or fallback))
        if origin and origin not in origins:
            origins.append(origin)
    return " ".join(origins)


def _admin_csp() -> str:
    """CSPِ ادمینِ جانگو — هیچ origin خارجی مجاز نیست؛ inline به‌سببِ خودِ admin."""
    return (
        "default-src 'none'; script-src 'self' 'unsafe-inline'; "
        "style-src 'self' 'unsafe-inline'; img-src 'self' data:; font-src 'self'; "
        "connect-src 'self'; form-action 'self'; frame-ancestors 'none'; base-uri 'self'"
    )


def _docs_csp() -> str:
    """CSPِ Swagger/ReDoc — فقط CDNِ تنظیم‌شده باز است، inline نه (template ما نیست)."""
    src = _spectacular_script_origins()
    return (
        f"default-src 'none'; script-src {src}; style-src {src} 'unsafe-inline'; "
        "img-src 'self' data: https://*.githubusercontent.com; font-src 'self'; "
        "connect-src 'self'; frame-ancestors 'none'; base-uri 'self'"
    )


def _profile_for(request: HttpRequest) -> str | None:
    """کدام پروفایل CSP برای این مسیر؛ None یعنی CSP لازم نیست (API/JSON)."""
    path = request.path
    if path == "/admin" or path.startswith("/admin/"):
        return "admin"
    if path in DOCS_HTML_PATHS:
        return "docs"
    return None


class BrowserSecurityHeadersMiddleware:
    """تزریقِ Permissions-Policy (جهانی) + CSP (admin/docs) طبقِ پروفایل‌ها.

    ساده و بدونِ تنظیماتِ ضمنی: اگر SECURE_BROWSER_HEADERS_ENABLED=False شد،
    middleware صفرهزینه رد می‌شود (flag برای incident-response: در شکستِ
    رگرسیونِ CSP، یک خط env به‌جای revert).
    """

    def __init__(self, get_response: Callable[[HttpRequest], HttpResponseBase]) -> None:
        self._get_response = get_response

    def __call__(self, request: HttpRequest) -> HttpResponseBase:
        """هدرها پس از تولیدِ پاسخ اضافه می‌شوند تا overrideهایِ view نپوشندش.

        عمداً `setdefault` نیست: اگر view هدرِ CSP را خودش ست کرده (مثلاً
        page-specific)، همان حرفِ اول را می‌زند.
        """
        response = self._get_response(request)
        if not getattr(settings, "SECURE_BROWSER_HEADERS_ENABLED", True):
            return response
        response.setdefault("Permissions-Policy", _PERMISSIONS_POLICY)
        profile = _profile_for(request)
        if profile is not None:
            csp = _admin_csp() if profile == "admin" else _docs_csp()
            header = "Content-Security-Policy"
            if not getattr(settings, "SECURE_CSP_ENFORCE", True):
                header = "Content-Security-Policy-Report-Only"
            response.setdefault(header, csp)
        return response

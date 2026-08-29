"""گیت دسترسی داکیومنت API (یافتهٔ P1-۴ فاز ۷).

پیش‌ازاین `/api/schema/`، `/api/docs/` (Swagger UI) و `/api/redoc/` بدون هیچ
شرطی باز بودند؛ یعنی هر بازدیدکننده‌ای می‌توانست schema کامل (~۲۹۰ مسیر،
شامل اندپوینت‌های ادمینیِ audit export / command-center / revoke session /
payout) را دانلود کند — نقشهٔ حملهٔ آماده.

سیاست (به‌ترتیب اولویت، در `docs_allowed`):
    1. ``DEBUG``              → باز. توسعهٔ محلی نباید ceremonial بپردازد.
    2. ``API_DOCS_ALLOW_ANONYMOUS=True`` → باز. برای دیپلوی‌هایی که داکیومنت
       عمومی را *عمداً* پذیرفته‌اند (flag صریح، نه فراموشی).
    3. در غیر این صورت: فقط کاربر **staff** احرازهویت‌شده.

ناشناس در production با redirect به لاگین ادمین مواجه می‌شود (نه 404)، چون
قرار است مسیر برای تیم قابل‌استفاده باشد و لاگین ادمینِ موجود، همان
provider احراز هویت است؛ از قضا گاردِ لاگین ادمین (P1-۳ فاز ۷) همین مسیر را
هم محافظت می‌کند.

چرا mixin روی viewها به‌جای middleware؟
    دامنهٔ گیت دقیقاً سه مسیر نام‌دار است؛ middleware یعنی بررسیِ path روی
    *هر* درخواست. mixin در زمان resolve صفرهزینه است و scopeاش ریگرسی
    نمی‌شود (اگر کسی مسیر docs جدیدی اضافه کند، باید آگاهانه mixin را
    به‌کار ببرد — که خودش یک review-gate معنادار است).
"""

from __future__ import annotations

from typing import Any

from django.conf import settings
from django.http import HttpRequest, HttpResponseBase
from django.shortcuts import redirect, resolve_url
from drf_spectacular.views import (
    SpectacularAPIView,
    SpectacularRedocView,
    SpectacularSwaggerView,
)


def docs_allowed(request: HttpRequest) -> bool:
    """Return whether this request may read API documentation/schema."""
    if settings.DEBUG:
        return True
    if getattr(settings, "API_DOCS_ALLOW_ANONYMOUS", False):
        return True
    user = getattr(request, "user", None)
    return bool(user is not None and user.is_authenticated and user.is_staff)


class DocumentationGateMixin:
    """جلوگیری دسترسی ناشناس به داکیومنت در production (سیاست: docs_allowed).

    Mixin است نه decorator، چون `as_view(url_name=...)`های spectacular باید
    همان‌طور بمانند و فقط `dispatch` بیندازد.
    """

    def dispatch(self, request: HttpRequest, *args: Any, **kwargs: Any) -> HttpResponseBase:
        """گیتِ سطح‌دسترسی، پیش از هر پردازشِ view."""
        if not docs_allowed(request):
            login_url = resolve_url("admin:login")
            separator = "&" if "?" in login_url else "?"
            return redirect(f"{login_url}{separator}next={request.get_full_path()}")
        return super().dispatch(request, *args, **kwargs)


class GatedSpectacularAPIView(DocumentationGateMixin, SpectacularAPIView):
    """OpenAPI schema، گیت‌شده."""


class GatedSpectacularSwaggerView(DocumentationGateMixin, SpectacularSwaggerView):
    """Swagger UI، گیت‌شده."""


class GatedSpectacularRedocView(DocumentationGateMixin, SpectacularRedocView):
    """ReDoc UI، گیت‌شده."""

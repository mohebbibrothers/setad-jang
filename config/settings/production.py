"""
Production environment overrides for Setad Jang project.

این فایل فقط overrideهای مختص محیط production را روی base.py اعمال می‌کند.
هیچ منطق business یا چیزی غیر از security/operational hardening در آن نیست.

اصول طراحی:
- fail-fast: اگر یک env critical غایب یا نامعتبر باشد، برنامه boot نمی‌شود.
- defense-in-depth: چندین لایه‌ی محافظتی Django/HTTPS/Cookie همزمان اعمال می‌شوند.
- بدون تغییر در business code: تنها رفتار runtime در سطح framework/HTTP تغییر می‌کند.

نکته‌ی استقرار:
- در production متغیرهای SECRET_KEY و ALLOWED_HOSTS باید از طریق
  secret manager یا environment واقعی سرور تأمین شوند، نه فایل.
"""

from .base import *
from .base import SIMPLE_JWT, config

# ============================================================
# Fail-fast checks
# ============================================================
# هدف: جلوگیری از اجرای برنامه در production با تنظیمات ناامن.
#
# لیست ناامن شامل تمام مقادیر پیش‌فرض شناخته‌شده است:
# - مقدار پیش‌فرض base.py
# - مقدار پیش‌فرض .env.example
# - مقدار پیش‌فرض local docker-compose
# - مقدار پیش‌فرض test pipeline
# هر کدام از این مقادیر در production غیرمجاز است.

_INSECURE_SECRET_KEYS: set[str] = {
    "",
    "change-me",
    "change-me-in-production",
    "local-only-key-do-not-use-in-real-prod",
    "local-container-key-32-bytes-fixed-AAAA1111",
    "test-secret-key-with-at-least-32-bytes-2026",
}

if SECRET_KEY in _INSECURE_SECRET_KEYS:
    raise RuntimeError(
        "SECRET_KEY در production نباید مقدار پیش‌فرض dev، local container یا test باشد. "
        "یک کلید قوی (حداقل 50 کاراکتر) تولید کن و در environment تنظیم کن.",
    )

if len(SECRET_KEY) < 50:
    raise RuntimeError(
        f"SECRET_KEY در production باید حداقل 50 کاراکتر باشد. "
        f"فعلاً {len(SECRET_KEY)} کاراکتر است.",
    )

if not ALLOWED_HOSTS:
    raise RuntimeError(
        "ALLOWED_HOSTS در production نباید خالی باشد. "
        "حداقل یک hostname معتبر مشخص کن.",
    )


# ============================================================
# Debug
# ============================================================

DEBUG = False


# ============================================================
# HTTPS / Proxy
# ============================================================

SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
SECURE_SSL_REDIRECT = config("SECURE_SSL_REDIRECT", default=True, cast=bool)

SECURE_HSTS_SECONDS = config(
    "SECURE_HSTS_SECONDS",
    default=60 * 60 * 24 * 30,
    cast=int,
)
SECURE_HSTS_INCLUDE_SUBDOMAINS = config(
    "SECURE_HSTS_INCLUDE_SUBDOMAINS",
    default=True,
    cast=bool,
)
SECURE_HSTS_PRELOAD = config(
    "SECURE_HSTS_PRELOAD",
    default=False,
    cast=bool,
)


# ============================================================
# Browser-side hardening
# ============================================================

SECURE_CONTENT_TYPE_NOSNIFF = True
X_FRAME_OPTIONS = "DENY"
SECURE_REFERRER_POLICY = "strict-origin-when-cross-origin"


# ============================================================
# Secure cookies
# ============================================================

SESSION_COOKIE_SECURE = True
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = "Lax"

CSRF_COOKIE_SECURE = True
CSRF_COOKIE_HTTPONLY = True
CSRF_COOKIE_SAMESITE = "Lax"


# ============================================================
# CORS
# ============================================================

CORS_ALLOW_ALL_ORIGINS = False
CORS_ALLOWED_ORIGINS = config(
    "CORS_ALLOWED_ORIGINS",
    default="",
    cast=lambda v: [s.strip() for s in v.split(",") if s.strip()],
)


# ============================================================
# Auth — production-specific overrides
# ============================================================

# JWT key در production باید مستقل از SECRET_KEY باشد.
# اگر JWT_SIGNING_KEY تنظیم نشده باشد، Django از همان SECRET_KEY استفاده می‌کند
# که قبلاً validate شده پس safe است — ولی بهتر است مجزا باشد.
_JWT_SIGNING_KEY = config("JWT_SIGNING_KEY", default="")
if _JWT_SIGNING_KEY:
    SIMPLE_JWT = {
        **SIMPLE_JWT,
        "SIGNING_KEY": _JWT_SIGNING_KEY,
    }

# Legacy auth sunset date — برای deprecation headers روی v1 endpoints.
# اگر تنظیم شود، در هر response از legacy endpoints نمایش داده می‌شود.
# فرمت: RFC 7231 date string مثل "Sun, 01 Jan 2027 00:00:00 GMT"
AUTH_LEGACY_SUNSET = config("AUTH_LEGACY_SUNSET", default="")

# Global OTP guard threshold در production باید محافظه‌کارانه‌تر باشد.
AUTH_OTP_GLOBAL_THRESHOLD = config(
    "AUTH_OTP_GLOBAL_THRESHOLD",
    default=500,
    cast=int,
)
AUTH_OTP_GLOBAL_WINDOW_SECONDS = config(
    "AUTH_OTP_GLOBAL_WINDOW_SECONDS",
    default=60,
    cast=int,
)

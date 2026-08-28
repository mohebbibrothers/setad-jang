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
from .base import CACHE_BACKEND, SIMPLE_JWT, config

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
# Database — PostgreSQL by default
# ============================================================

_DATABASE_ENGINE = config("DATABASE_ENGINE", default="postgres").strip().lower()

if _DATABASE_ENGINE == "postgres":
    _POSTGRES_PASSWORD = config("POSTGRES_PASSWORD")
    if _POSTGRES_PASSWORD in {"", "change-me", "change-me-postgres-password"}:
        raise RuntimeError(
            "POSTGRES_PASSWORD در production نباید خالی یا مقدار نمونه باشد.",
        )

    if len(_POSTGRES_PASSWORD) < 16:
        raise RuntimeError(
            "POSTGRES_PASSWORD در production باید حداقل 16 کاراکتر باشد.",
        )

    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.postgresql",
            "NAME": config("POSTGRES_DB"),
            "USER": config("POSTGRES_USER"),
            "PASSWORD": _POSTGRES_PASSWORD,
            "HOST": config("POSTGRES_HOST", default="postgres"),
            "PORT": config("POSTGRES_PORT", default="5432"),
            "CONN_MAX_AGE": config("POSTGRES_CONN_MAX_AGE", default=60, cast=int),
            "CONN_HEALTH_CHECKS": True,
            "OPTIONS": {
                "connect_timeout": config("POSTGRES_CONNECT_TIMEOUT", default=10, cast=int),
            },
        },
    }
elif _DATABASE_ENGINE == "sqlite":
    if not config("ALLOW_SQLITE_IN_PRODUCTION", default=False, cast=bool):
        raise RuntimeError(
            "SQLite در production فقط برای demo/local emergency مجاز است. "
            "برای استفاده آگاهانه DATABASE_ENGINE=sqlite و "
            "ALLOW_SQLITE_IN_PRODUCTION=True را تنظیم کن؛ برای production واقعی "
            "از PostgreSQL استفاده کن.",
        )
else:
    raise RuntimeError(
        "DATABASE_ENGINE نامعتبر است. مقدارهای مجاز: postgres, sqlite.",
    )


# ============================================================
# Cache — must be shared across processes
# ============================================================

# کش در این پروژه صرفاً یک بهینه‌سازی نیست؛ چند سازوکار *صحت* روی آن سوارند.
# با locmem هر worker گانیکورن کش مستقل خودش را دارد و نتیجه‌اش این است:
#
#   - همهٔ throttleهای DRF per-process می‌شوند، پس با N worker نرخ واقعی
#     N برابر مقدار تنظیم‌شده است. یعنی محافظت anti-abuse و anti-brute-force
#     بی‌سروصدا چند برابر ضعیف‌تر از چیزی است که در تنظیمات نوشته شده.
#   - گارد سراسری OTP هم به همان نسبت شل می‌شود.
#   - و از همه بدتر: cache_delete_namespace فقط روی همان workerی اثر می‌کند
#     که درخواست را گرفته است. بقیهٔ workerها تا انقضای hard_ttl دادهٔ کهنه
#     سرو می‌کنند. این یک باگ صحت تمام‌عیار است، نه افت کارایی.
#
# چون CACHE_BACKEND در base.py مقدار پیش‌فرض "locmem" دارد و .env.example هم
# همان را نشان می‌دهد، یک deploy که فقط فایل نمونه را کپی کرده باشد کاملاً
# بی‌صدا در این حالت بالا می‌آید. پس اینجا fail-fast می‌کنیم.
if CACHE_BACKEND != "redis":
    raise RuntimeError(
        f"CACHE_BACKEND در production باید 'redis' باشد (مقدار فعلی: '{CACHE_BACKEND}'). "
        "با کش per-process، تمام throttleها به تعداد workerها ضعیف‌تر می‌شوند و "
        "invalidate کش فقط روی یک worker اثر می‌کند که باعث سرو شدن دادهٔ کهنه است.",
    )


# ============================================================
# HTTPS / Proxy
# ============================================================

SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
SECURE_SSL_REDIRECT = config("SECURE_SSL_REDIRECT", default=True, cast=bool)

SECURE_HSTS_SECONDS = config(
    "SECURE_HSTS_SECONDS",
    default=60 * 60 * 24 * 365,
    cast=int,
)
SECURE_HSTS_INCLUDE_SUBDOMAINS = config(
    "SECURE_HSTS_INCLUDE_SUBDOMAINS",
    default=True,
    cast=bool,
)
SECURE_HSTS_PRELOAD = config(
    "SECURE_HSTS_PRELOAD",
    default=True,
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

SESSION_COOKIE_SECURE = config("SESSION_COOKIE_SECURE", default=True, cast=bool)
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = "Lax"

CSRF_COOKIE_SECURE = config("CSRF_COOKIE_SECURE", default=True, cast=bool)
CSRF_COOKIE_HTTPONLY = True
CSRF_COOKIE_SAMESITE = "Lax"

# WhiteNoise serves the collected STATIC_ROOT directory in production/demo.
WHITENOISE_AUTOREFRESH = config("WHITENOISE_AUTOREFRESH", default=False, cast=bool)
WHITENOISE_USE_FINDERS = config("WHITENOISE_USE_FINDERS", default=False, cast=bool)


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

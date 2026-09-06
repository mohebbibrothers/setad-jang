"""
Base Django settings for Setad Jang project.

این فایل شامل تنظیمات مشترک بین تمام environmentها است.
فایل‌های development.py و production.py فقط overrideهای مخصوص خود را
روی همین تنظیمات پایه اعمال می‌کنند.

اصول طراحی:
- تمام تنظیمات حساس از environment variable خوانده می‌شوند (via python-decouple).
- هیچ secret در کد hardcode نشده است.
- ساختار فایل به بخش‌های مجزا تقسیم شده برای خوانایی و نگهداری آسان.
- هر بخش با header مشخص جدا شده است.
- تنظیمات Docker-compatible هستند — هم با Docker هم بدون آن کار می‌کنند.
"""

from datetime import timedelta
from pathlib import Path

from celery.schedules import crontab
from decouple import Csv, config

from config.observability import bootstrap_observability

BASE_DIR = Path(__file__).resolve().parent.parent.parent

# ============================================================================
# Security
# ============================================================================

SECRET_KEY = config("SECRET_KEY", default="change-me")
DEBUG = config("DEBUG", default=True, cast=bool)
ALLOWED_HOSTS = config(
    "ALLOWED_HOSTS",
    default="127.0.0.1,localhost",
    cast=Csv(),
)

# ============================================================================
# Applications
# ============================================================================

DJANGO_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    # برای ثبت lookupهای PostgreSQL (trigram_similar, unaccent, search).
    # بدون این اپ، لوکاپ `__trigram_similar` در سطح Django اصلاً ثبت
    # نمی‌شود (یافتهٔ مرتبط با P2 ممیزی: ایندکس‌های جستجو).
    "django.contrib.postgres",
]

THIRD_PARTY_APPS = [
    "rest_framework",
    "django_filters",
    "corsheaders",
    "drf_spectacular",
    "rest_framework_simplejwt.token_blacklist",
]

LOCAL_APPS = [
    "apps.core.apps.CoreConfig",
    "apps.public_reports.apps.PublicReportsConfig",
    "apps.authentication.apps.AuthenticationConfig",
    "apps.audit_logs.apps.AuditLogsConfig",
    "apps.tabyin.apps.TabyinConfig",
    "apps.r4j.apps.R4JConfig",
    "apps.madadkar.apps.MadadkarConfig",
    "apps.lms.apps.LMSConfig",
    "apps.kindness_wall.apps.KindnessWallConfig",
    "apps.support_desk.apps.SupportDeskConfig",
    "apps.notifications.apps.NotificationsConfig",
    "apps.activity.apps.ActivityConfig",
    "apps.command_center.apps.CommandCenterConfig",
]

INSTALLED_APPS = DJANGO_APPS + THIRD_PARTY_APPS + LOCAL_APPS

# ============================================================================
# Middleware
# ============================================================================

MIDDLEWARE = [
    "apps.core.middleware.RequestIDMiddleware",
    "apps.core.middleware.PrometheusMetricsMiddleware",
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    # گارد لاگین ادمین (یافتهٔ P1-۳ فاز ۷) — بعد از Session تا request کامل
    # باشد و قبل از CSRF تا تلاش‌های قفل‌شده هزینهٔ توکن هم نپردازند.
    "apps.core.admin_guard.AdminLoginGuardMiddleware",
    "corsheaders.middleware.CorsMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    # هدرهای مرورگریِ فاز 8 (یافتهٔ P2-9) — آخرِ زنجیره تا روی پاسخ‌های
    # WhiteNoise هم الگویِ پوشش‌دهیِ ثابتی داشته باشیم و overrideهای view
    # (setdefault نیست) حفظ شوند.
    "apps.core.browser_headers.BrowserSecurityHeadersMiddleware",
]

# پرچمِ خاموش‌شدنِ اضطراری هدرهای فاز 8 (incident-response): با False بودن،
# middleware بدونِ هیچ هزینه‌ای رد می‌شود. SECURE_CSP_ENFORCE=False یعنی
# Content-Security-Policy-Report-Only — حالتِ توصیه‌شده برای چرخهٔ اولِ استقرار.
SECURE_BROWSER_HEADERS_ENABLED = config("SECURE_BROWSER_HEADERS_ENABLED", default=True, cast=bool)
SECURE_CSP_ENFORCE = config("SECURE_CSP_ENFORCE", default=True, cast=bool)

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"
ASGI_APPLICATION = "config.asgi.application"

# ============================================================================
# Database
# ============================================================================

# «خالی» برابر است با «استفاده از پیش‌فرض» — .env.example عمداً این کلید را
# خالی مستند می‌کند و config() آن را "" می‌خواند، نه default؛ بدونِ این fallback،
# NAME="" مسیرِ SQLite را می‌شکند. (حاشیۀ یافتۀ P3-18 فاز 8.)
DATABASE_PATH = config("DATABASE_PATH", default="") or str(BASE_DIR / "db.sqlite3")

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": DATABASE_PATH,
    },
}

# ============================================================================
# Password validation
# ============================================================================

AUTH_PASSWORD_VALIDATORS = [
    {
        "NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
        "OPTIONS": {"min_length": 10},
    },
    {
        "NAME": "django.contrib.auth.password_validation.CommonPasswordValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.NumericPasswordValidator",
    },
    # سیاستِ بومیِ ستاد جنگ (یافتهٔ P2-8 فاز 8): کلاس‌های کاراکتری،
    # توالی/ردیفِ صفحه‌کلید، سالِ تولدِ شمسی، نامِ پلتفرم و黑名单ِ
    # فارسی/فینگلیش. مستند در apps/authentication/password_policy.py.
    {
        "NAME": "apps.authentication.password_policy.BesatPasswordPolicyValidator",
    },
]

# ============================================================================
# Internationalization
# ============================================================================

LANGUAGE_CODE = "fa-ir"
TIME_ZONE = "Asia/Tehran"
USE_I18N = True
USE_TZ = True

# ============================================================================
# Static & Media
# ============================================================================

STATIC_URL = "/static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
STATICFILES_DIRS = [BASE_DIR / "static"]
# In development/CI, WhiteNoise should use autorefresh mode so tests do not
# fail when STATIC_ROOT has not been generated yet. Production overrides this
# to False and serves files collected by collectstatic.
WHITENOISE_AUTOREFRESH = config("WHITENOISE_AUTOREFRESH", default=True, cast=bool)
WHITENOISE_USE_FINDERS = config("WHITENOISE_USE_FINDERS", default=True, cast=bool)

MEDIA_URL = "/media/"
MEDIA_ROOT = BASE_DIR / "media"
SERVE_PUBLIC_MEDIA = config("SERVE_PUBLIC_MEDIA", default=False, cast=bool)

MEDIA_STORAGE_BACKEND = config("MEDIA_STORAGE_BACKEND", default="local").strip().lower()

# ── رسانه‌ی روایت‌های مردمی (تبیین): آپلود مستقیم + آینه‌سازی ─────────
# سقف حجم هر نوع رسانه (مگابایت) — با env قابل تنظیم؛ با سقفِ nginx هماهنگ است.
TABYIN_UPLOAD_MAX_MB = {
    "image": config("TABYIN_UPLOAD_MAX_IMAGE_MB", default=10, cast=int),
    "video": config("TABYIN_UPLOAD_MAX_VIDEO_MB", default=100, cast=int),
    "audio": config("TABYIN_UPLOAD_MAX_AUDIO_MB", default=30, cast=int),
    "other": config("TABYIN_UPLOAD_MAX_OTHER_MB", default=25, cast=int),
}
# سقفِ سختِ دانلود هنگام آینه‌سازی نشانی‌های بیرونی (مگابایت؛ مستقل از نوع).
TABYIN_MIRROR_MAX_MB = config("TABYIN_MIRROR_MAX_MB", default=120, cast=int)
# مهلت خواندن از سرور مبدأ هنگام آینه‌سازی (ثانیه).
TABYIN_MIRROR_TIMEOUT_SECONDS = config("TABYIN_MIRROR_TIMEOUT_SECONDS", default=25, cast=int)
# اگر CDN خودمان داریم (مثلا https://cdn.besat.me)، رسانه‌ی عمومی با این پیشوند
# منتشر می‌شود؛ پیش‌فرض = مسیر نسبی /media/… روی همان origin سایت.
TABYIN_PUBLIC_MEDIA_BASE_URL = config("TABYIN_PUBLIC_MEDIA_BASE_URL", default="").strip()
# میزبان‌هایی که نشانی مطلقِ رسانه‌ی آن‌ها «داخلی» محسوب می‌شود (بدون آینه‌سازی).
TABYIN_LOCAL_MEDIA_HOSTS = config(
    "TABYIN_LOCAL_MEDIA_HOSTS",
    default="besat.me,www.besat.me",
    cast=Csv(),
)

# پیش‌فرض "default" یعنی زنجیرهٔ کامل: blocklist پسوند + بررسی امضای محتوا.
# مقدار "extension_blocklist" فقط لایهٔ اول را فعال می‌کند (سازگاری با رفتار
# قبلی) و "noop" همه‌چیز را خاموش می‌کند.
FILE_SCAN_PROVIDER = config("FILE_SCAN_PROVIDER", default="default").strip().lower()

# حالت ACL آپلودها روی S3/MinIO.
#
# "none" یعنی هیچ هدر ACLی ارسال نشود. این مقدار برای باکت‌هایی لازم است که
# با «Object Ownership: Bucket owner enforced» ساخته شده‌اند — پیش‌فرض AWS از
# آوریل ۲۰۲۳ — چون آن باکت‌ها هر درخواست دارای ACL را با خطای
# AccessControlListNotSupported رد می‌کنند. در آن حالت دسترسی عمومی باید با
# bucket policy مدیریت شود.
#
# برای باکت‌های قدیمی‌تر یا MinIO می‌توان مقدار را روی "public-read" گذاشت.
AWS_DEFAULT_ACL_MODE = config("AWS_DEFAULT_ACL_MODE", default="none")

# backoff نمایی برای تلاش مجدد رویدادهای outbox ابطال کش.
# sweeper هر دقیقه اجرا می‌شود، پس بدون این backoff یک رویداد خراب کل بودجهٔ
# تلاش‌هایش را در چند دقیقه می‌سوزاند.
CACHE_INVALIDATION_RETRY_BASE_SECONDS = config(
    "CACHE_INVALIDATION_RETRY_BASE_SECONDS", default=10, cast=int
)
CACHE_INVALIDATION_RETRY_MAX_SECONDS = config(
    "CACHE_INVALIDATION_RETRY_MAX_SECONDS", default=3600, cast=int
)

AUDIT_LOG_ARCHIVE_ROOT = config("AUDIT_LOG_ARCHIVE_ROOT", default=str(BASE_DIR / "audit_exports"))
AUDIT_LOG_RETENTION_DAYS = config("AUDIT_LOG_RETENTION_DAYS", default=2555, cast=int)
AUDIT_LOG_LEGAL_HOLD_ENABLED = config("AUDIT_LOG_LEGAL_HOLD_ENABLED", default=True, cast=bool)
AUDIT_LOG_RETENTION_DELETE_ENABLED = config(
    "AUDIT_LOG_RETENTION_DELETE_ENABLED", default=False, cast=bool
)
AUDIT_LOG_EXPORT_MAX_RECORDS = config("AUDIT_LOG_EXPORT_MAX_RECORDS", default=100000, cast=int)

MADADKAR_RISK_HIGH_AMOUNT_NEW_USER_THRESHOLD = config(
    "MADADKAR_RISK_HIGH_AMOUNT_NEW_USER_THRESHOLD", default=50_000_000, cast=int
)
MADADKAR_RISK_PAYMENT_FAILURE_SPIKE_THRESHOLD = config(
    "MADADKAR_RISK_PAYMENT_FAILURE_SPIKE_THRESHOLD", default=3, cast=int
)
MADADKAR_RISK_IP_DISTINCT_USERS_THRESHOLD = config(
    "MADADKAR_RISK_IP_DISTINCT_USERS_THRESHOLD", default=3, cast=int
)
MADADKAR_RISK_REFUND_VELOCITY_THRESHOLD = config(
    "MADADKAR_RISK_REFUND_VELOCITY_THRESHOLD", default=3, cast=int
)
MADADKAR_RISK_CAMPAIGN_REFUND_SPIKE_THRESHOLD = config(
    "MADADKAR_RISK_CAMPAIGN_REFUND_SPIKE_THRESHOLD", default=5, cast=int
)
MADADKAR_RISK_ADJUSTMENT_RATIO_THRESHOLD = config(
    "MADADKAR_RISK_ADJUSTMENT_RATIO_THRESHOLD", default=0.25, cast=float
)

AWS_ACCESS_KEY_ID = config("AWS_ACCESS_KEY_ID", default="")
AWS_SECRET_ACCESS_KEY = config("AWS_SECRET_ACCESS_KEY", default="")
AWS_STORAGE_BUCKET_NAME = config("AWS_STORAGE_BUCKET_NAME", default="")
AWS_S3_REGION_NAME = config("AWS_S3_REGION_NAME", default="")
AWS_S3_ENDPOINT_URL = config("AWS_S3_ENDPOINT_URL", default="")
AWS_S3_CUSTOM_DOMAIN = config("AWS_S3_CUSTOM_DOMAIN", default="")
AWS_S3_OBJECT_PARAMETERS = {"CacheControl": "max-age=86400"}
AWS_QUERYSTRING_AUTH = True
AWS_DEFAULT_ACL = None

if MEDIA_STORAGE_BACKEND == "s3":
    STORAGES = {
        "default": {"BACKEND": "apps.core.storage.PrivateMediaStorage"},
        "public_media": {"BACKEND": "apps.core.storage.PublicMediaStorage"},
        "private_media": {"BACKEND": "apps.core.storage.PrivateMediaStorage"},
        "staticfiles": {"BACKEND": "whitenoise.storage.CompressedStaticFilesStorage"},
    }
else:
    STORAGES = {
        "default": {"BACKEND": "apps.core.storage.LocalPublicMediaStorage"},
        "public_media": {"BACKEND": "apps.core.storage.LocalPublicMediaStorage"},
        "private_media": {"BACKEND": "apps.core.storage.LocalPrivateMediaStorage"},
        "staticfiles": {"BACKEND": "whitenoise.storage.CompressedStaticFilesStorage"},
    }


# ============================================================================
# Frontend on-demand revalidation
# ============================================================================

CACHE_INVALIDATION_OUTBOX_ENABLED = config(
    "CACHE_INVALIDATION_OUTBOX_ENABLED", default=True, cast=bool
)
CACHE_INVALIDATION_MAX_ATTEMPTS = config("CACHE_INVALIDATION_MAX_ATTEMPTS", default=10, cast=int)
CACHE_INVALIDATION_BATCH_SIZE = config("CACHE_INVALIDATION_BATCH_SIZE", default=100, cast=int)
FRONTEND_REVALIDATION_ENABLED = config("FRONTEND_REVALIDATION_ENABLED", default=False, cast=bool)
FRONTEND_REVALIDATION_URL = config("FRONTEND_REVALIDATION_URL", default="")
FRONTEND_REVALIDATION_SECRET = config("FRONTEND_REVALIDATION_SECRET", default="")
FRONTEND_REVALIDATION_TIMEOUT = config("FRONTEND_REVALIDATION_TIMEOUT", default=5, cast=int)

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# ============================================================================
# Performance Contracts
# ============================================================================

DEFAULT_PERFORMANCE_BUDGET_MS = config("DEFAULT_PERFORMANCE_BUDGET_MS", default=1000, cast=int)
DB_QUERY_TELEMETRY_ENABLED = config("DB_QUERY_TELEMETRY_ENABLED", default=True, cast=bool)
DB_SLOW_QUERY_THRESHOLD_MS = config("DB_SLOW_QUERY_THRESHOLD_MS", default=100, cast=int)
DB_QUERY_COUNT_WARNING_THRESHOLD = config("DB_QUERY_COUNT_WARNING_THRESHOLD", default=50, cast=int)
DB_TOTAL_QUERY_TIME_WARNING_MS = config("DB_TOTAL_QUERY_TIME_WARNING_MS", default=500, cast=int)
PERFORMANCE_CONTRACTS = {
    "/api/v1/health/*": 250,
    "/api/v1/metrics/": 500,
    "/api/v1/admin/*": 2000,
    "/api/v1/audit-logs/*": 2000,
    "/api/v1/madadkar/admin/*": 2500,
    "/api/v1/support/admin/*": 2500,
}

# ============================================================================
# Django REST Framework
# ============================================================================

REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": (
        "apps.authentication.jwt_auth.SessionAwareJWTAuthentication",
    ),
    # ── Client IP / X-Forwarded-For ────────────────────────────────────
    # تعداد پراکسی‌های «قابل اعتماد» پشت سرویس (یافتهٔ P1 ممیزی).
    # پیش‌فرض صفر است: header ورودی X-Forwarded-For هرگز معتبر نیست و
    # REMOTE_ADDR (که WSGI/پروکسی واقعی پر می‌کند) تنها منبع IP است.
    # وقتی پشت n پراکسی هستید که XFF را بازنویسی می‌کنند، این را دقیقاً
    # همان n بگذارید — نه تعداد hops شبکه. متدهای internal از
    # apps.core.client_ip استفاده می‌کنند (fail-closed حتی در حالت None).
    "NUM_PROXIES": config("NUM_PROXIES", default="0", cast=int),
    "DEFAULT_PERMISSION_CLASSES": ("rest_framework.permissions.IsAuthenticated",),
    "DEFAULT_FILTER_BACKENDS": (
        "django_filters.rest_framework.DjangoFilterBackend",
        "rest_framework.filters.SearchFilter",
        "rest_framework.filters.OrderingFilter",
    ),
    "DEFAULT_PAGINATION_CLASS": "apps.core.pagination.StandardPagination",
    "PAGE_SIZE": 20,
    "DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema",
    "DEFAULT_RENDERER_CLASSES": ("rest_framework.renderers.JSONRenderer",),
    "EXCEPTION_HANDLER": "apps.core.exceptions.custom_exception_handler",
    "DEFAULT_THROTTLE_CLASSES": (
        "rest_framework.throttling.AnonRateThrottle",
        "rest_framework.throttling.UserRateThrottle",
    ),
    "DEFAULT_THROTTLE_RATES": {
        # ── Defaults ──────────────────────────────────────
        "anon": "60/min",
        "user": "120/min",
        # ── Public Reports ────────────────────────────────
        "report_create_anon": "5/min",
        "report_create_user": "20/min",
        # لیست موضوعات: عمومی و cached ولی طبق انضباط پروژه scope اختصاصی.
        "public_report_subjects": "30/min",
        # ── Health ────────────────────────────────────────
        # /health/detailed/ برای anonymous به‌ازای IP محدود است (هر فراخوانی
        # ۹ چک سنگین اجرا می‌کند). /health/ و /health/ready/ عمداً throttle
        # ندارند چون probeهای orchestrator نباید محدود شوند.
        "health_detailed_anon": "10/min",
        # ── Authentication ────────────────────────────────
        "auth_login": "10/min",
        "auth_register": "5/min",
        "auth_otp_request": "3/min",
        "auth_otp_verify": "10/min",
        "auth_otp_ip": "10/min",
        # سقف per-recipient: مهاجم می‌تواند IP و اکانت عوض کند ولی شمارهٔ
        # قربانی ثابت است. این تنها لایه‌ای است که هزینهٔ پنل پیامک را در
        # برابر SMS-bombing توزیع‌شده محدود می‌کند.
        "auth_otp_target": "12/hour",
        "auth_password_reset": "3/min",
        # رفرش توکن: هر فراخوانی موفق یک ردیف blacklist می‌سازد؛ per-IP
        # (در لحظهٔ رفرش، هویت از body است نه request.user).
        "token_refresh": "30/min",
        # ── Tabyin ────────────────────────────────────────
        "tabyin_sync": "5/hour",
        # ── R4J — Reward for Justice ──────────────────────
        "r4j_browse_anon": "60/min",
        "r4j_browse_user": "120/min",
        "r4j_report_create": "5/min",
        "r4j_bounty_set": "3/min",
        # ── Madadkar — Charitable Crowdfunding ────────────
        "madadkar_browse_anon": "60/min",
        "madadkar_browse_user": "120/min",
        "madadkar_participate": "10/min",
        "madadkar_payment_verify": "30/min",
        # راستی‌آزمایی عمومی رسید: اوراکل شمارش است؛ سقف عمداً سخت‌گیرانه
        # و همیشه per-IP (مستقل از احراز هویت).
        "madadkar_receipt_verify": "10/min",
        # ── LMS — Learning Management System ────────────────
        "lms_enroll": "20/hour",
        "lms_progress": "120/min",
        "lms_quiz_start": "10/hour",
        "lms_discussion": "30/hour",
        # browse عمومی دوره‌ها: همان الگوی انضباطی browse (anon/user).
        "lms_browse_anon": "60/min",
        "lms_browse_user": "120/min",
        # تأیید عمومی گواهی‌نامه: اوراکل شمارش slug؛ per-IP و سخت‌گیرانه.
        "lms_certificate_verify": "10/min",
        # ── Kindness Wall — Divar-e Mehrabani ─────────
        "kindness_browse_anon": "60/min",
        "kindness_browse_user": "120/min",
        "kindness_listing_create": "10/hour",
        "kindness_contact_reveal": "20/hour",
        "kindness_report": "10/hour",
        # ── Support Desk — Ticketing ───────────────────────
        "support_ticket_create": "5/hour",
        "support_ticket_message": "30/hour",
        "support_attachment_upload": "20/hour",
        "support_suggest": "20/hour",
        "support_user_browse": "120/min",
        "support_admin_actions": "120/min",
    },
}

# ============================================================================
# JWT
# ============================================================================

SIMPLE_JWT = {
    # عمر access token از یک روز به ۳۰ دقیقه کاهش یافت.
    #
    # یک روز برای توکنی که قابل ابطال مستقیم نیست خیلی طولانی است: توکنِ
    # لو رفته (از لاگ، از دستگاه مشترک، از یک XSS) تا ۲۴ ساعت معتبر می‌ماند.
    # SessionAwareJWTAuthentication تا حد زیادی این را جبران می‌کرد، ولی
    # اتکای کامل به آن یعنی تمام امنیت نشست به یک بررسی در سطح اپلیکیشن
    # وابسته است؛ کوتاه کردن عمر توکن همان دفاع را در سطح خود پروتکل هم
    # می‌گذارد (defense in depth).
    #
    # هزینهٔ این تغییر، refresh مکرر‌تر است. با ROTATE_REFRESH_TOKENS و
    # BLACKLIST_AFTER_ROTATION هر refresh دو ردیف در جدول توکن می‌سازد،
    # که تسک ساعتی پاک‌سازی (یافتهٔ ۴.۶) آن را جمع می‌کند.
    "ACCESS_TOKEN_LIFETIME": timedelta(minutes=config("JWT_ACCESS_MINUTES", default=30, cast=int)),
    "REFRESH_TOKEN_LIFETIME": timedelta(days=config("JWT_REFRESH_DAYS", default=7, cast=int)),
    "ROTATE_REFRESH_TOKENS": True,
    "BLACKLIST_AFTER_ROTATION": True,
    "AUTH_HEADER_TYPES": ("Bearer",),
}

# ============================================================================
# CORS
# ============================================================================

CORS_ALLOW_ALL_ORIGINS = True

# ============================================================================
# Swagger / OpenAPI (drf-spectacular)
# ============================================================================

# گیت داکیومنت (یافتۀ P1-4 فاز 7): در production فقط staff می‌تواند
# /api/schema|docs|redoc را ببیند. تنها راه قانونی برای عمومی‌کردنِ
# عمدیِ داکیومنت، همین flag است (پیش‌فرض: خاموش). در DEBUG همیشه باز است.
API_DOCS_ALLOW_ANONYMOUS = config("API_DOCS_ALLOW_ANONYMOUS", default=False, cast=bool)

# ایمیلِ contact داخل schema عمومی؛ صراحتاً یک آدرس سازمانی، نه شخصی
# (یافتۀ P1-4 فاز 7 — ایمیل شخصی در schema عمومی collection risk می‌سازد).
API_CONTACT_EMAIL = config("API_CONTACT_EMAIL", default="dev@besat.me")

SPECTACULAR_SETTINGS = {
    "TITLE": "ستاد جنگ — API Documentation",
    "DESCRIPTION": (
        "## مستندات API پروژه ستاد جنگ\n\n"
        "این داکیومنت تمام endpointهای backend پروژه ستاد جنگ را شامل می‌شود.\n\n"
        "---\n\n"
        "### 🏗 معماری پاسخ‌ها\n\n"
        "تمام پاسخ‌های موفق در یک **envelope استاندارد** قرار می‌گیرند:\n\n"
        "```json\n"
        "{\n"
        '  "success": true,\n'
        '  "status_code": 200,\n'
        '  "message": "عملیات با موفقیت انجام شد.",\n'
        '  "data": { ... }\n'
        "}\n"
        "```\n\n"
        "تمام پاسخ‌های ناموفق نیز فرمت یکسانی دارند:\n\n"
        "```json\n"
        "{\n"
        '  "success": false,\n'
        '  "status_code": 400,\n'
        '  "message": "درخواست نامعتبر است.",\n'
        '  "errors": { ... }\n'
        "}\n"
        "```\n\n"
        "---\n\n"
        "### 🔐 احراز هویت (نسخه ۲ — چندشناسه‌ای)\n\n"
        "این API از **JWT (JSON Web Token)** و **سیستم احراز هویت چندشناسه‌ای** "
        "استفاده می‌کند.\n\n"
        "**روش‌های ثبت‌نام و ورود:**\n"
        "- ثبت‌نام با **ایمیل یا شماره موبایل** از طریق `/api/v1/auth/signup/request/`\n"
        "- ورود با **رمز عبور** از طریق `/api/v1/auth/login/password/`\n"
        "- ورود با **کد یکبارمصرف** از طریق `/api/v1/auth/login/otp/request/`\n"
        "- بروزرسانی توکن با `/api/v1/auth/token/refresh/`\n\n"
        "**مدیریت شناسه:**\n"
        "- اتصال شناسه ثانویه (ایمیل یا موبایل) از طریق "
        "`/api/v1/auth/identifiers/add/request/`\n"
        "- تغییر شناسه اصلی از طریق `/api/v1/auth/identifiers/make-primary/`\n\n"
        "> ⚠️ endpointهای نسخه ۱ (مثل `/register/` و `/login/`) هنوز فعال هستند "
        "ولی **منسوخ شده‌اند** و در نسخه‌های آینده حذف خواهند شد.\n\n"
        "---\n\n"
        "### 📦 ماژول‌های پروژه\n\n"
        "- **احراز هویت** — ثبت‌نام چندشناسه‌ای، ورود، مدیریت شناسه، بازیابی رمز\n"
        "- **گزارشات مردمی** — ثبت گزارش و مدیریت موضوعات\n"
        "- **جهاد تبیین** — همگام‌سازی محتوا از منبع خارجی و نمایش گالری\n"
        "- **جایزه‌ای برای عدالت (R4J)** — پروفایل مجرمین، گزارشات تکمیلی و "
        "جوایز اعلامی\n"
        "- **مددکار** — مشارکت خیریه سهم‌محور با اتصال به درگاه پرداخت\n"
        "- **لاگ فعالیت** — ثبت فعالیت‌های حساس سیستم\n\n"
        "---\n\n"
        "### 🚦 محدودیت‌های نرخ (Rate Limiting)\n\n"
        "هر endpoint بسته به نوعش throttle مخصوص خود را دارد. در صورت برخورد به "
        "`429 Too Many Requests`، چند ثانیه صبر کرده و دوباره تلاش کنید.\n\n"
        "---\n\n"
        "### 🛡 امنیت\n\n"
        "- **Anti-abuse:** honeypot detection، global OTP guard، "
        "constant-time responses\n"
        "- **Timing-attack mitigation:** dummy hash path در "
        "authentication backend\n"
        "- **Enumeration-safe:** endpointهای forgot password و login OTP وجود یا "
        "عدم وجود حساب را افشا نمی‌کنند\n"
        "- **High-trust operations:** عملیات حساس مثل تعیین جایزه نیازمند احراز "
        "هویت کامل (ایمیل + موبایل) و تکمیل پروفایل هستند\n"
        "- **Payment safety:** رزرو سهم با select_for_update، idempotent verify، "
        "expire خودکار تراکنش‌های راکد"
    ),
    "VERSION": "2.0.0",
    "SERVE_INCLUDE_SCHEMA": False,
    "CONTACT": {
        "name": "تیم توسعه ستاد جنگ",
        "email": API_CONTACT_EMAIL,
    },
    "LICENSE": {
        "name": "Iran_Cyber_MA",
    },
    "TAGS": [
        {
            "name": "احراز هویت — عمومی",
            "description": (
                "endpointهای عمومی احراز هویت شامل:\n"
                "- ثبت‌نام چندشناسه‌ای (ایمیل / موبایل)\n"
                "- ورود با رمز عبور یا کد یکبارمصرف\n"
                "- بازیابی رمز عبور\n"
                "- endpointهای منسوخ نسخه ۱ (deprecated)"
            ),
        },
        {
            "name": "احراز هویت — کاربر",
            "description": (
                "endpointهای مخصوص کاربر لاگین کرده:\n"
                "- مشاهده و ویرایش پروفایل\n"
                "- مدیریت شناسه‌ها (اتصال، تأیید، تغییر اصلی)\n"
                "- تغییر رمز عبور\n"
                "- خروج"
            ),
        },
        {
            "name": "احراز هویت — مدیریت",
            "description": "endpointهای مدیریتی کاربران (فقط ادمین)",
        },
        {
            "name": "گزارشات مردمی — عمومی",
            "description": "ثبت گزارش و مشاهده موضوعات (بدون نیاز به لاگین)",
        },
        {
            "name": "گزارشات مردمی — موضوعات (مدیریت)",
            "description": "CRUD کامل موضوعات گزارش (فقط ادمین)",
        },
        {
            "name": "گزارشات مردمی — گزارشات (مدیریت)",
            "description": ("مدیریت گزارش‌های دریافتی و تغییر وضعیت آن‌ها (فقط ادمین)"),
        },
        {
            "name": "تبیین — عمومی",
            "description": "نمایش محتواهای جهاد تبیین در سایت (با cache بهینه)",
        },
        {
            "name": "تبیین — مدیریت",
            "description": ("مدیریت محتواها و اجرای دستی همگام‌سازی (فقط ادمین)"),
        },
        {
            "name": "لاگ فعالیت — مدیریت",
            "description": ("مشاهده و جستجوی لاگ‌های فعالیت سیستم (فقط ادمین)"),
        },
        {
            "name": "جایزه‌ای برای عدالت — عمومی",
            "description": (
                "نمایش پروفایل مجرمین منتشرشده به همراه جوایز اعلامی (بدون نیاز به لاگین)"
            ),
        },
        {
            "name": "جایزه‌ای برای عدالت — کاربر",
            "description": ("ارسال گزارش تکمیلی برای پروفایل مجرمین (نیازمند احراز هویت پایه)"),
        },
        {
            "name": "جایزه‌ای برای عدالت — تعیین جایزه",
            "description": (
                "تعیین، ویرایش و درخواست لغو جایزه برای مجرمین "
                "(نیازمند احراز هویت کامل و تکمیل پروفایل)"
            ),
        },
        {
            "name": "جایزه‌ای برای عدالت — مدیریت",
            "description": (
                "مدیریت کامل پروفایل مجرمین، بررسی گزارشات و تأیید درخواست‌های لغو (فقط ادمین)"
            ),
        },
        {
            "name": "مددکار — عمومی",
            "description": ("نمایش حرکت‌های خیریه و مددکاران به صورت عمومی (بدون نیاز به لاگین)"),
        },
        {
            "name": "مددکار — کاربر",
            "description": ("مشارکت در حرکت‌ها از طریق خرید سهم و پرداخت (نیازمند لاگین معمولی)"),
        },
        {
            "name": "مددکار — مدیریت (مددکاران)",
            "description": "CRUD کامل نهادهای میزبان حرکت‌ها (فقط ادمین)",
        },
        {
            "name": "مددکار — مدیریت (حرکت‌ها)",
            "description": (
                "ایجاد، انتشار، بستن و مدیریت کامل حرکت‌های خیریه و گالری تصاویر آن‌ها (فقط ادمین)"
            ),
        },
        {
            "name": "مددکار — مدیریت (تحلیل و گزارش)",
            "description": (
                "مشاهده جزئیات مشارکت‌کنندگان، رتبه‌بندی و خروجی Excel "
                "حرفه‌ای از پرداخت‌های هر حرکت (فقط ادمین)"
            ),
        },
    ],
    "SERVERS": [
        {
            "url": config("OPENAPI_SERVER_URL", default="http://127.0.0.1:8000"),
            "description": config(
                "OPENAPI_SERVER_DESCRIPTION",
                default="محیط توسعه (Local Development)",
            ),
        },
    ],
    "SWAGGER_UI_SETTINGS": {
        "deepLinking": True,
        "persistAuthorization": True,
        "displayOperationId": False,
        "defaultModelsExpandDepth": 1,
        "defaultModelExpandDepth": 2,
        "docExpansion": "none",
        "filter": True,
        "tryItOutEnabled": True,
        "tagsSorter": "alpha",
        "operationsSorter": "alpha",
    },
    "REDOC_UI_SETTINGS": {
        "lazyRendering": True,
        "hideHostname": False,
        "expandResponses": "200,201",
        "pathInMiddlePanel": True,
        "theme": {
            "colors": {
                "primary": {
                    "main": "#1976D2",
                },
            },
        },
    },
    "SCHEMA_PATH_PREFIX": r"/api/v[0-9]+/",
    "SCHEMA_PATH_PREFIX_TRIM": False,
    "COMPONENT_SPLIT_REQUEST": False,
    "COMPONENT_NO_READ_ONLY_REQUIRED": False,
    "ENUM_NAME_OVERRIDES": {
        "ReportStatusEnum": "apps.public_reports.choices.ReportStatus",
        "TabyinSyncModeEnum": "apps.tabyin.choices.SyncMode",
        "TabyinMediaTypeEnum": "apps.tabyin.choices.MediaType",
        "AuthGenderEnum": "apps.authentication.choices.Gender",
        "AuthRiskSignalTypeEnum": "apps.authentication.choices.AuthRiskSignalType",
        "RiskReviewStatusEnum": (
            ("reviewed", "بررسی‌شده"),
            ("dismissed", "ردشده"),
            ("escalated", "ارجاع‌شده"),
        ),
        "R4JGenderEnum": "apps.r4j.choices.Gender",
        "R4JSocialPlatformEnum": "apps.r4j.choices.SocialPlatform",
        "R4JCriminalAttachmentKindEnum": "apps.r4j.choices.CriminalAttachmentKind",
        "R4JEvidenceCustodyEventTypeEnum": "apps.r4j.choices.EvidenceCustodyEventType",
        "R4JReportStatusEnum": "apps.r4j.choices.ReportStatus",
        "R4JReportFieldChangeStatusEnum": "apps.r4j.choices.ReportFieldChangeStatus",
        "R4JBountyStatusEnum": "apps.r4j.choices.BountyStatus",
        "MadadkarCampaignStatusEnum": "apps.madadkar.choices.CampaignStatus",
        "MadadkarParticipationStatusEnum": "apps.madadkar.choices.ParticipationStatus",
        "MadadkarPaymentStatusEnum": "apps.madadkar.choices.PaymentStatus",
        "MadadkarRefundReasonEnum": "apps.madadkar.choices.RefundReason",
        "MadadkarRefundStatusEnum": "apps.madadkar.choices.RefundStatus",
        "MadadkarFinancialAdjustmentTypeEnum": "apps.madadkar.choices.FinancialAdjustmentType",
        "MadadkarFinancialAdjustmentStatusEnum": "apps.madadkar.choices.FinancialAdjustmentStatus",
        "MadadkarDisbursementStatusEnum": "apps.madadkar.choices.DisbursementStatus",
        "MadadkarRiskSignalTypeEnum": "apps.madadkar.choices.MadadkarRiskSignalType",
        "MadadkarRiskSeverityEnum": "apps.madadkar.choices.MadadkarRiskSeverity",
        "MadadkarRiskStatusEnum": "apps.madadkar.choices.MadadkarRiskStatus",
        "LMSCourseLevelEnum": "apps.lms.choices.CourseLevel",
        "LMSCourseStatusEnum": "apps.lms.choices.CourseStatus",
        "LMSEnrollmentStatusEnum": "apps.lms.choices.EnrollmentStatus",
        "LMSDiscussionStatusEnum": "apps.lms.choices.DiscussionStatus",
        "LMSDiscussionReportStatusEnum": "apps.lms.choices.DiscussionReportStatus",
        "LMSQuizAttemptStatusEnum": "apps.lms.choices.QuizAttemptStatus",
        "LMSCertificateStatusEnum": "apps.lms.choices.CertificateStatus",
        "LMSBadgeLevelEnum": "apps.lms.choices.BadgeLevel",
        "LMSVideoProviderEnum": "apps.lms.choices.VideoProvider",
        "LMSVideoProcessingStatusEnum": "apps.lms.choices.VideoProcessingStatus",
        "LMSLearningStatementVerbEnum": "apps.lms.choices.LearningStatementVerb",
        "KindnessMatchStatusEnum": "apps.kindness_wall.choices.MatchStatus",
        "KindnessReportReasonEnum": "apps.kindness_wall.choices.ReportReason",
        "SupportTicketStatusEnum": "apps.support_desk.choices.TicketStatus",
        "SupportTicketPriorityEnum": "apps.support_desk.choices.TicketPriority",
        "SupportTicketSeverityEnum": "apps.support_desk.choices.TicketSeverity",
        "SupportAttachmentKindEnum": "apps.support_desk.choices.AttachmentKind",
        "SupportAttachmentVisibilityEnum": "apps.support_desk.choices.AttachmentVisibility",
        "SupportDuplicateReviewStatusEnum": "apps.support_desk.choices.DuplicateReviewStatus",
        "HealthStatusEnum": ("ok", "error", "degraded"),
    },
    "POSTPROCESSING_HOOKS": [
        "drf_spectacular.hooks.postprocess_schema_enums",
    ],
    "DISABLE_ERRORS_AND_WARNINGS": False,
    "ENFORCE_NON_BLANK_FIELDS": False,
}

# ============================================================================
# Custom User & Authentication Backends
# ============================================================================

AUTH_USER_MODEL = "authentication.User"
AUTHENTICATION_BACKENDS = [
    "apps.authentication.backends.MultiIdentifierBackend",
]

# ============================================================================
# Email (Django 6.1 → MAILERS)
# ============================================================================
# از Django 6.1 تنظیمات `EMAIL_*` منسوخ شده‌اند (RemovedInDjango70Warning) و
# در 7.0 حذف می‌شوند؛ جایگزین رسمی `MAILERS` است که aliasهای نام‌دار و
# per-backend OPTIONS دارد. نام متغیرهای محیطی (EMAIL_HOST و ...) عمداً حفظ
# شده تا قرارداد deployment/.env تغییر نکند؛ فقط ساختار settings عوض شده.
#
# نکتهٔ مهم: OPTIONS فقط باید شامل کلیدهایی باشد که backend انتخابی می‌پذیرد
# (BaseEmailBackend با alias ست، روی کلید ناشناخته InvalidMailer می‌دهد).
# پس OPTIONS فقط برای SMTP ساخته می‌شود؛ console/locmem/custom بدون OPTIONS.
_EMAIL_BACKEND = config(
    "EMAIL_BACKEND",
    default="apps.core.email_backends.ReadableConsoleEmailBackend",
)

_EMAIL_SMTP_OPTIONS: dict[str, object] = {}
if "smtp" in _EMAIL_BACKEND.lower():
    _EMAIL_SMTP_OPTIONS = {
        "host": config("EMAIL_HOST", default="smtp-relay.brevo.com"),
        "port": config("EMAIL_PORT", default=587, cast=int),
        "use_tls": config("EMAIL_USE_TLS", default=True, cast=bool),
        "timeout": config("EMAIL_TIMEOUT", default=15, cast=int),
        "username": config("EMAIL_HOST_USER", default=""),
        "password": config("EMAIL_HOST_PASSWORD", default=""),
    }

MAILERS = {
    "default": {
        "BACKEND": _EMAIL_BACKEND,
        "OPTIONS": _EMAIL_SMTP_OPTIONS,
    },
}
DEFAULT_FROM_EMAIL = config(
    "DEFAULT_FROM_EMAIL",
    default="noreply@setadjang.local",
)

# ============================================================================
# Authentication / OTP
# ============================================================================

NOTIFICATIONS_ASYNC_DISPATCH = config("NOTIFICATIONS_ASYNC_DISPATCH", default=True, cast=bool)
NOTIFICATIONS_EMAIL_ENABLED = config("NOTIFICATIONS_EMAIL_ENABLED", default=False, cast=bool)
NOTIFICATIONS_SMS_ENABLED = config("NOTIFICATIONS_SMS_ENABLED", default=False, cast=bool)
KINDNESS_MATCH_NOTIFICATION_THRESHOLD = config(
    "KINDNESS_MATCH_NOTIFICATION_THRESHOLD", default=80, cast=int
)

OTP_PROVIDER = config("OTP_PROVIDER", default="email")
OTP_EMAIL_PROVIDER = config("OTP_EMAIL_PROVIDER", default="django_email")
OTP_SMS_PROVIDER = config("OTP_SMS_PROVIDER", default="console")

# --- OTP tunables -----------------------------------------------------------
# این مقادیر قبلاً ثابت‌های سطح ماژول در `apps/authentication/otp.py` و
# `anti_abuse.py` بودند. نتیجه‌اش این بود که نه از settings قابل تنظیم بودند و
# نه در تست قابل override — و بدتر، `AUTH_OTP_GLOBAL_THRESHOLD` که فقط در
# production.py تعریف شده بود هرگز خوانده نمی‌شد. حالا تنها مرجع همین‌جاست.

# طول کد OTP. ۶ رقم استاندارد صنعتی است؛ ۵ رقم یعنی فضای جستجوی ۱۰۰٬۰۰۰
# حالته که هم brute-force آنلاین را ارزان می‌کند و هم شکستن offline را.
AUTH_OTP_CODE_LENGTH = config("AUTH_OTP_CODE_LENGTH", default=6, cast=int)
AUTH_OTP_TTL_SECONDS = config("AUTH_OTP_TTL_SECONDS", default=300, cast=int)
AUTH_OTP_MAX_ATTEMPTS = config("AUTH_OTP_MAX_ATTEMPTS", default=5, cast=int)
AUTH_OTP_COOLDOWN_SECONDS = config("AUTH_OTP_COOLDOWN_SECONDS", default=60, cast=int)

# گارد ناهنجاری سراسری: اگر نرخ کل صدور OTP در پنجرهٔ زمانی از آستانه بگذرد،
# صدور موقتاً متوقف می‌شود. پیش‌فرض عمداً با production.py یکسان است تا دوباره
# اختلاف پیش‌فرض‌ها (۵۰۰ در برابر ۱۰۰۰) پیش نیاید.
AUTH_OTP_GLOBAL_THRESHOLD = config("AUTH_OTP_GLOBAL_THRESHOLD", default=500, cast=int)
AUTH_OTP_GLOBAL_WINDOW_SECONDS = config("AUTH_OTP_GLOBAL_WINDOW_SECONDS", default=60, cast=int)

# --- IranPayamak (الگوی تأییدشده/Pattern) — برای OTP_SMS_PROVIDER=iranpayamak ---
# API key راز است: فقط در .env. کد الگوها و شمارهٔ خط، خروجی پنل‌اند و در .env
# می‌آیند (پیش‌فرض‌های خالی = fail loud در readiness، نه ترافیک نیمه‌کاره).
SMS_IRANPAYAMAK_API_KEY = config("SMS_IRANPAYAMAK_API_KEY", default="")
SMS_IRANPAYAMAK_PATTERN_URL = config(
    "SMS_IRANPAYAMAK_PATTERN_URL",
    default="https://api.iranpayamak.com/ws/v1/sms/pattern",
)
SMS_IRANPAYAMAK_LINE_NUMBER = config("SMS_IRANPAYAMAK_LINE_NUMBER", default="50002178584000")
SMS_IRANPAYAMAK_NUMBER_FORMAT = config("SMS_IRANPAYAMAK_NUMBER_FORMAT", default="persian")
SMS_IRANPAYAMAK_TIMEOUT_SECONDS = config("SMS_IRANPAYAMAK_TIMEOUT_SECONDS", default=10, cast=int)
SMS_IRANPAYAMAK_PATTERN_LOGIN = config("SMS_IRANPAYAMAK_PATTERN_LOGIN", default="")
SMS_IRANPAYAMAK_PATTERN_SIGNUP = config("SMS_IRANPAYAMAK_PATTERN_SIGNUP", default="")
SMS_IRANPAYAMAK_PATTERN_PASSWORD_RESET = config(
    "SMS_IRANPAYAMAK_PATTERN_PASSWORD_RESET",
    default="",
)
SMS_IRANPAYAMAK_PATTERN_IDENTIFIER_ADD = config(
    "SMS_IRANPAYAMAK_PATTERN_IDENTIFIER_ADD",
    default="",
)

SMS_API_URL = config("SMS_API_URL", default="")
SMS_API_KEY = config("SMS_API_KEY", default="")
SMS_SENDER = config("SMS_SENDER", default="")
SMS_TIMEOUT_SECONDS = config("SMS_TIMEOUT_SECONDS", default=10, cast=int)
LOGIN_URL = "/admin/login/"

# ============================================================================
# Django Admin — login guard (یافتهٔ P1-۳ فاز ۷)
# ============================================================================
# صفحهٔ لاگین ادمین view معمولی جانگو است و throttleهای DRF به آن نمی‌رسند؛
# این سه مقدار، سیاست قفلِ مبتنی‌بر‌کشِ `apps.core.admin_guard` را تعریف
# می‌کنند (شمارش بر اساس ورودی نامعتبر، نه تعداد درخواست).

# حداکثر ورودیِ نامعتبر برای هر جفت (IP, نام‌کاربری) پیش از قفل.
ADMIN_LOGIN_MAX_FAILURES = config("ADMIN_LOGIN_MAX_FAILURES", default=5, cast=int)
# سقف تجمیعی هر IP روی همهٔ نام‌های کاربری (ضد credential-stuffing پخش‌شده).
ADMIN_LOGIN_MAX_FAILURES_PER_IP = config("ADMIN_LOGIN_MAX_FAILURES_PER_IP", default=20, cast=int)
# مدت قفل موقت (ثانیه).
ADMIN_LOGIN_LOCKOUT_SECONDS = config("ADMIN_LOGIN_LOCKOUT_SECONDS", default=900, cast=int)

# ============================================================================
# Shared Redis settings
# ============================================================================

REDIS_URL = config("REDIS_URL", default="redis://127.0.0.1:6379/1")

# ============================================================================
# Observability / Logging
# ============================================================================

LOG_FORMAT = config("LOG_FORMAT", default="text").strip().lower()
PROMETHEUS_METRICS_ENABLED = config("PROMETHEUS_METRICS_ENABLED", default=True, cast=bool)

# توکن اسکرپ متریک‌ها (یافتهٔ P1 فاز ۷): در production تنها راه خواندن
# /api/v1/metrics/ هدر `Authorization: Bearer <این مقدار>` است و اگر تنظیم
# نشده باشد endpoint عملاً 404 می‌شود (fail-closed). در scrape-config
# Prometheus همین را زیر `authorization: credentials:` بگذار.
# تولید: python -c "import secrets; print(secrets.token_urlsafe(32))"
PROMETHEUS_METRICS_TOKEN = config("PROMETHEUS_METRICS_TOKEN", default="")
SENTRY_DSN = config("SENTRY_DSN", default="")
SENTRY_TRACES_SAMPLE_RATE = config("SENTRY_TRACES_SAMPLE_RATE", default=0.0, cast=float)
SENTRY_PROFILES_SAMPLE_RATE = config("SENTRY_PROFILES_SAMPLE_RATE", default=0.0, cast=float)
OTEL_ENABLED = config("OTEL_ENABLED", default=False, cast=bool)
OTEL_SERVICE_NAME = config("OTEL_SERVICE_NAME", default="setad-jang-api")

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "filters": {
        "request_id": {
            "()": "apps.core.middleware.RequestIDLogFilter",
        },
    },
    "formatters": {
        "verbose": {
            "format": "{asctime} [{levelname}] [{request_id}] {name}: {message}",
            "style": "{",
        },
        "simple": {
            "format": "[{levelname}] [{request_id}] {message}",
            "style": "{",
        },
        "json": {
            "()": "apps.core.logging.JSONLogFormatter",
        },
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": "json" if LOG_FORMAT == "json" else "verbose",
            "filters": ["request_id"],
        },
    },
    "loggers": {
        "django": {
            "handlers": ["console"],
            "level": "INFO",
            "propagate": False,
        },
        "django.request": {
            "handlers": ["console"],
            "level": "ERROR",
            "propagate": False,
        },
        "apps": {
            "handlers": ["console"],
            "level": "INFO",
            "propagate": False,
        },
        "apps.core": {
            "handlers": ["console"],
            "level": "INFO",
            "propagate": False,
        },
        "apps.core.cache": {
            "handlers": ["console"],
            "level": "INFO",
            "propagate": False,
        },
        "apps.authentication": {
            "handlers": ["console"],
            "level": "INFO",
            "propagate": False,
        },
        "apps.audit_logs": {
            "handlers": ["console"],
            "level": "INFO",
            "propagate": False,
        },
        "apps.public_reports": {
            "handlers": ["console"],
            "level": "INFO",
            "propagate": False,
        },
        "apps.tabyin": {
            "handlers": ["console"],
            "level": "INFO",
            "propagate": False,
        },
        "apps.r4j": {
            "handlers": ["console"],
            "level": "INFO",
            "propagate": False,
        },
        "apps.madadkar": {
            "handlers": ["console"],
            "level": "INFO",
            "propagate": False,
        },
        "celery": {
            "handlers": ["console"],
            "level": "INFO",
            "propagate": False,
        },
        "celery.beat": {
            "handlers": ["console"],
            "level": "INFO",
            "propagate": False,
        },
        "celery.worker": {
            "handlers": ["console"],
            "level": "INFO",
            "propagate": False,
        },
    },
}

# ============================================================================
# Cache Configuration
# ============================================================================

CACHE_BACKEND = config("CACHE_BACKEND", default="locmem")

if CACHE_BACKEND == "redis":
    CACHES = {
        "default": {
            "BACKEND": "django_redis.cache.RedisCache",
            "LOCATION": REDIS_URL,
            "OPTIONS": {
                "CLIENT_CLASS": "django_redis.client.DefaultClient",
                "SERIALIZER": "django_redis.serializers.json.JSONSerializer",
                "COMPRESSOR": "django_redis.compressors.zlib.ZlibCompressor",
                "CONNECTION_POOL_KWARGS": {
                    "max_connections": 50,
                    "retry_on_timeout": True,
                },
                "IGNORE_EXCEPTIONS": True,
            },
            "KEY_PREFIX": "setadjang",
            "TIMEOUT": 300,
        },
    }

    DJANGO_REDIS_IGNORE_EXCEPTIONS = True
    DJANGO_REDIS_LOG_IGNORED_EXCEPTIONS = True

else:
    CACHES = {
        "default": {
            "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
            "LOCATION": "setadjang-locmem",
            "TIMEOUT": 300,
        },
    }

# ============================================================================
# Celery Configuration
# ============================================================================

CELERY_BROKER_URL = config("CELERY_BROKER_URL", default=REDIS_URL)
CELERY_RESULT_BACKEND = config("CELERY_RESULT_BACKEND", default=CELERY_BROKER_URL)

CELERY_ACCEPT_CONTENT = ["json"]
CELERY_TASK_SERIALIZER = "json"
CELERY_RESULT_SERIALIZER = "json"

CELERY_TIMEZONE = TIME_ZONE
CELERY_ENABLE_UTC = USE_TZ

CELERY_TASK_TRACK_STARTED = True
CELERY_TASK_SEND_SENT_EVENT = True
CELERY_WORKER_SEND_TASK_EVENTS = True

CELERY_BROKER_CONNECTION_RETRY_ON_STARTUP = True

# ---------------------------------------------------------------------------
# تحویل at-least-once
# ---------------------------------------------------------------------------
# پیش‌فرض Celery ``acks_late=False`` است: پیام **قبل از** اجرای تسک ack
# می‌شود. اگر worker وسط کار بمیرد (OOM، SIGKILL هنگام deploy، از دست رفتن
# نود) تسک برای همیشه گم می‌شود و هیچ ردی هم باقی نمی‌ماند. برای تسک‌های
# مالی، نوتیفیکیشن و audit این رفتار قابل قبول نیست.
#
# با ``acks_late=True`` پیام فقط پس از اتمام موفق تسک ack می‌شود و در صورت
# مرگ worker دوباره تحویل داده می‌شود. هزینه‌اش این است که تسک ممکن است
# بیش از یک بار اجرا شود.
#
# قرارداد لازم: هر تسک این پروژه باید idempotent یا نسبت به تکرار بی‌تفاوت
# باشد. این شرط برای همهٔ تسک‌های فعلی بررسی و تأیید شده است — یا بر پایهٔ
# فیلتر وضعیت کار می‌کنند، یا از ``get_or_create``/``update`` استفاده
# می‌کنند، یا عمداً append-only هستند (snapshot مالی، audit log) که در
# آن‌ها یک ردیف تکراری از یک رکورد گم‌شده به‌مراتب کم‌ضررتر است.
CELERY_TASK_ACKS_LATE = True

# اگر worker بدون ack شدن پیام از بین برود، پیام به‌جای ack شدن reject و
# دوباره صف می‌شود. بدون این گزینه ``acks_late`` دقیقاً در سناریوی مرگ
# ناگهانی worker — یعنی همان چیزی که می‌خواهیم پوشش دهیم — بی‌اثر است.
CELERY_TASK_REJECT_ON_WORKER_LOST = True

# visibility_timeout مخصوص brokerهای مبتنی بر Redis است: اگر تسکی طولانی‌تر
# از این مقدار طول بکشد، Redis آن را «گم‌شده» فرض کرده و به worker دیگری
# تحویل می‌دهد — یعنی اجرای همزمان دوتایی. مقدار باید قاطعانه بزرگ‌تر از
# ``CELERY_TASK_TIME_LIMIT`` باشد تا این حالت هرگز رخ ندهد.
CELERY_TASK_TIME_LIMIT = 60 * 30
CELERY_BROKER_TRANSPORT_OPTIONS = {
    "visibility_timeout": CELERY_TASK_TIME_LIMIT * 2,
}

CELERY_TASK_SOFT_TIME_LIMIT = 60 * 25
CELERY_RESULT_EXPIRES = 60 * 60 * 24

CELERY_WORKER_PREFETCH_MULTIPLIER = 1
CELERY_WORKER_MAX_TASKS_PER_CHILD = 100

CELERY_TASK_DEFAULT_QUEUE = "default"
CELERY_TASK_ROUTES = {
    "apps.core.tasks.revalidate_frontend_task": {
        "queue": "default",
    },
    "apps.core.tasks.process_cache_invalidation_event_task": {
        "queue": "default",
    },
    "apps.core.tasks.process_pending_cache_invalidation_events_task": {
        "queue": "default",
    },
    "apps.tabyin.tasks.sync_tabyin_incremental_task": {
        "queue": "tabyin_sync",
    },
    "apps.tabyin.tasks.sync_tabyin_full_task": {
        "queue": "tabyin_sync",
    },
    "apps.madadkar.tasks.expire_stale_participations_task": {
        "queue": "madadkar",
    },
    "apps.madadkar.tasks.close_expired_campaigns_task": {
        "queue": "madadkar",
    },
    "apps.madadkar.tasks.generate_financial_control_snapshot_task": {
        "queue": "madadkar",
    },
    "apps.lms.tasks.process_lesson_video_job_task": {
        "queue": "default",
    },
    "apps.support_desk.tasks.mark_support_sla_breaches_task": {
        "queue": "default",
    },
    "apps.support_desk.tasks.cleanup_stale_support_drafts_task": {
        "queue": "default",
    },
    "apps.support_desk.tasks.daily_support_digest_task": {
        "queue": "default",
    },
    "apps.notifications.tasks.dispatch_notification_event_task": {
        "queue": "default",
    },
    "apps.authentication.tasks.flush_expired_jwt_tokens_task": {
        "queue": "default",
    },
    "apps.kindness_wall.tasks.expire_old_listings_task": {
        "queue": "default",
    },
    "apps.audit_logs.tasks.enforce_audit_retention_task": {
        "queue": "default",
    },
}

CELERY_BEAT_SCHEDULE = {
    "cache-invalidation-outbox-every-minute": {
        "task": "apps.core.tasks.process_pending_cache_invalidation_events_task",
        "schedule": crontab(minute="*"),
    },
    "tabyin-incremental-sync-every-30-minutes": {
        "task": "apps.tabyin.tasks.sync_tabyin_incremental_task",
        "schedule": crontab(minute="*/30"),
    },
    "tabyin-full-sync-daily": {
        "task": "apps.tabyin.tasks.sync_tabyin_full_task",
        "schedule": crontab(minute=0, hour=3),
    },
    "madadkar-expire-stale-participations-every-5-minutes": {
        "task": "apps.madadkar.tasks.expire_stale_participations_task",
        "schedule": crontab(minute="*/5"),
    },
    "madadkar-close-expired-campaigns-every-10-minutes": {
        "task": "apps.madadkar.tasks.close_expired_campaigns_task",
        "schedule": crontab(minute="*/10"),
    },
    "madadkar-financial-control-daily": {
        "task": "apps.madadkar.tasks.generate_financial_control_snapshot_task",
        "schedule": crontab(minute=30, hour=6),
    },
    "support-mark-sla-breaches-every-5-minutes": {
        "task": "apps.support_desk.tasks.mark_support_sla_breaches_task",
        "schedule": crontab(minute="*/5"),
    },
    "support-cleanup-stale-drafts-daily": {
        "task": "apps.support_desk.tasks.cleanup_stale_support_drafts_task",
        "schedule": crontab(minute=20, hour=2),
    },
    "support-daily-digest": {
        "task": "apps.support_desk.tasks.daily_support_digest_task",
        "schedule": crontab(minute=0, hour=8),
    },
    # پاک‌سازی توکن‌های JWT منقضی. با ROTATE_REFRESH_TOKENS و
    # BLACKLIST_AFTER_ROTATION هر refresh دو ردیف جدید می‌سازد، پس بدون این
    # زمان‌بندی جدول‌های token_blacklist بی‌نهایت رشد می‌کنند و چون مسیر
    # احراز هویت در هر درخواست به آن‌ها می‌خورد، کل API تدریجاً کند می‌شود.
    # اجرای ساعتی (نه روزانه) باعث می‌شود هر نوبت حجم کمی حذف شود.
    "auth-flush-expired-jwt-tokens-hourly": {
        "task": "apps.authentication.tasks.flush_expired_jwt_tokens_task",
        "schedule": crontab(minute=15),
    },
    # آگهی‌های دیوار مهربانی. تسک این کار از قبل وجود داشت ولی یک stub خالی
    # بود و هیچ زمان‌بندی‌ای هم نداشت، پس عملاً هیچ آگهی‌ای منقضی نمی‌شد و
    # آگهی‌های تاریخ‌گذشته برای همیشه در فهرست عمومی می‌ماندند.
    "kindness-expire-due-listings-hourly": {
        "task": "apps.kindness_wall.tasks.expire_old_listings_task",
        "schedule": crontab(minute=5),
    },
    # سیاست نگهداشت audit تعریف شده بود ولی مجری نداشت. این اجرا غیرمخرب
    # است و فقط بدهی نگهداشت را مرئی می‌کند.
    "audit-enforce-retention-daily": {
        "task": "apps.audit_logs.tasks.enforce_audit_retention_task",
        "schedule": crontab(minute=45, hour=4),
    },
}

# ============================================================================
# Excel exports
# ============================================================================

# سقف تعداد ردیف داده در یک فایل export. حتی با نوشتن جریانی، یک گزارش
# بی‌کران فایلی می‌سازد که نه دانلود می‌شود و نه در اکسل باز می‌شود، و در
# همان مدت یک worker را اشغال می‌کند. عبور از این سقف خطای روشن می‌دهد.
EXPORT_MAX_ROWS = config("EXPORT_MAX_ROWS", default=200_000, cast=int)


# ============================================================================
# Upload limits — enforced by Django before application code runs
# ============================================================================

# سقف حجم پیوست فقط در validator سریالایزر بررسی می‌شد. مشکل اینجاست که آن
# validator تازه *بعد از* کامل شدن آپلود اجرا می‌شود: تا آن لحظه جنگو کل بدنهٔ
# درخواست را خوانده و روی دیسک (یا در حافظه) نوشته است. یعنی یک مهاجم
# می‌توانست فایل ۵۰۰ مگابایتی بفرستد، منابع سرور را مصرف کند و در نهایت فقط
# یک پاسخ ۴۰۰ بگیرد — که برای او هزینه‌ای ندارد و برای ما دارد.
#
# این تنظیمات همان سقف را به لایهٔ پارس درخواست جنگو منتقل می‌کنند، جایی که
# با RequestDataTooBig رد می‌شود و خواندن بدنه همان‌جا متوقف می‌شود.

# ۲۵ مگابایت: کمی بالاتر از سقف ۲۰ مگابایتی پیوست، تا فضای سربار multipart
# (مرزها، هدرها، فیلدهای همراه) باعث رد شدن یک آپلود *معتبر* نشود.
DATA_UPLOAD_MAX_MEMORY_SIZE = config(
    "DATA_UPLOAD_MAX_MEMORY_SIZE", default=25 * 1024 * 1024, cast=int
)

# بالاتر از این حجم، فایل به‌جای حافظه در فایل موقت دیسک بافر می‌شود.
# ۲.۵ مگابایت پیش‌فرض خود جنگوست و برای این پروژه منطقی است.
FILE_UPLOAD_MAX_MEMORY_SIZE = config("FILE_UPLOAD_MAX_MEMORY_SIZE", default=2621440, cast=int)

# سد در برابر حملهٔ hash-collision/parse با فرم‌های دارای هزاران فیلد.
DATA_UPLOAD_MAX_NUMBER_FIELDS = config("DATA_UPLOAD_MAX_NUMBER_FIELDS", default=1000, cast=int)

# هیچ endpointی در این پروژه آپلود دسته‌ای انبوه ندارد.
DATA_UPLOAD_MAX_NUMBER_FILES = config("DATA_UPLOAD_MAX_NUMBER_FILES", default=20, cast=int)

# مجوز دسترسی فایل‌های آپلودی. بدون این، فایل‌های بزرگ (که از مسیر فایل
# موقت می‌آیند) ممکن است با مجوز 0o600 ذخیره شوند و فایل‌های کوچک با
# مجوزی دیگر — یعنی رفتار غیرقابل‌پیش‌بینی بسته به حجم آپلود.
FILE_UPLOAD_PERMISSIONS = 0o644


# ============================================================================
# Madadkar (Charitable Crowdfunding) Configuration
# ============================================================================

# Payment provider — "sandbox" در development، "zarinpal" یا دیگر providerها در production
MADADKAR_PAYMENT_PROVIDER = config(
    "MADADKAR_PAYMENT_PROVIDER",
    default="sandbox",
)

# Base URL برای callback پرداخت (بدون trailing slash)
MADADKAR_PAYMENT_CALLBACK_BASE_URL = config(
    "MADADKAR_PAYMENT_CALLBACK_BASE_URL",
    default="http://127.0.0.1:8000",
)

# Base URL صفحهٔ نتیجهٔ پرداخت روی **فرانت** (بدون trailing slash).
#
# کاربر پس از اتمام کار در صفحهٔ درگاه، ابتدا به endpoint بک‌اند
# (/api/v1/madadkar/payment/verify/) برمی‌گردد تا تراکنش verify شود؛ سپس
# view او را با 302 به این مسیر فرانت می‌فرستد:
#   {MADADKAR_PAYMENT_RESULT_BASE_URL}/madadkar/paydone/?authority=…&result=…
# بدون این تنظیم، کاربر روی JSON خامِ API بک‌اند فرود می‌آمد.
MADADKAR_PAYMENT_RESULT_BASE_URL = config(
    "MADADKAR_PAYMENT_RESULT_BASE_URL",
    default="http://127.0.0.1:3000",
)

# مدت زمان معتبر بودن یک تراکنش PENDING (دقیقه) — بعد از این مدت expire می‌شود
# اندازه استخر اتصال Session مشترک زرین‌پال (keep-alive بین‌درخواستی).
ZARINPAL_HTTP_POOL_MAXSIZE = config("ZARINPAL_HTTP_POOL_MAXSIZE", default=16, cast=int)
MADADKAR_PAYMENT_TIMEOUT_MINUTES = config(
    "MADADKAR_PAYMENT_TIMEOUT_MINUTES",
    default=15,
    cast=int,
)

# تنظیمات Zarinpal
MADADKAR_ZARINPAL_MERCHANT_ID = config(
    "MADADKAR_ZARINPAL_MERCHANT_ID",
    default="",
)
# default از DEBUG پیروی می‌کند: در dev/test خودبه‌خود sandbox (که با
# merchant واقعی کار نمی‌کند و نباید هم بکند)، در production خودبه‌خود
# واقعی. خطای قبلی: default ثابت True یعنی فراموشیِ تنظیم در سرورِ عملیاتی
# ترافیک پرداخت را بی‌سروصدا به درگاه sandbox می‌فرستاد.
MADADKAR_ZARINPAL_SANDBOX = config(
    "MADADKAR_ZARINPAL_SANDBOX",
    default=DEBUG,
    cast=bool,
)

# ============================================================================
# Observability bootstrap (optional, env-driven)
# ============================================================================

bootstrap_observability(
    sentry_dsn=SENTRY_DSN,
    sentry_environment=("production" if not DEBUG else "development"),
    sentry_traces_sample_rate=SENTRY_TRACES_SAMPLE_RATE,
    sentry_profiles_sample_rate=SENTRY_PROFILES_SAMPLE_RATE,
    otel_enabled=OTEL_ENABLED,
    otel_service_name=OTEL_SERVICE_NAME,
)

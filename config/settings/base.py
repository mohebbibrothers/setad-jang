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
]

INSTALLED_APPS = DJANGO_APPS + THIRD_PARTY_APPS + LOCAL_APPS

# ============================================================================
# Middleware
# ============================================================================

MIDDLEWARE = [
    "apps.core.middleware.RequestIDMiddleware",
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "corsheaders.middleware.CorsMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

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

DATABASE_PATH = config(
    "DATABASE_PATH",
    default=str(BASE_DIR / "db.sqlite3"),
)

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
    },
    {
        "NAME": "django.contrib.auth.password_validation.CommonPasswordValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.NumericPasswordValidator",
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

MEDIA_URL = "/media/"
MEDIA_ROOT = BASE_DIR / "media"

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# ============================================================================
# Django REST Framework
# ============================================================================

REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": (
        "rest_framework_simplejwt.authentication.JWTAuthentication",
    ),
    "DEFAULT_PERMISSION_CLASSES": (
        "rest_framework.permissions.IsAuthenticated",
    ),
    "DEFAULT_FILTER_BACKENDS": (
        "django_filters.rest_framework.DjangoFilterBackend",
        "rest_framework.filters.SearchFilter",
        "rest_framework.filters.OrderingFilter",
    ),
    "DEFAULT_PAGINATION_CLASS": "apps.core.pagination.StandardPagination",
    "PAGE_SIZE": 20,
    "DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema",
    "DEFAULT_RENDERER_CLASSES": (
        "rest_framework.renderers.JSONRenderer",
    ),
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
        # ── Authentication ────────────────────────────────
        "auth_login": "10/min",
        "auth_register": "5/min",
        "auth_otp_request": "3/min",
        "auth_otp_verify": "10/min",
        "auth_otp_ip": "10/min",
        "auth_password_reset": "3/min",
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
        # ── LMS — Learning Management System ────────────────
        "lms_enroll": "20/hour",
        "lms_progress": "120/min",
        "lms_quiz_start": "10/hour",
        "lms_discussion": "30/hour",
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
    "ACCESS_TOKEN_LIFETIME": timedelta(days=1),
    "REFRESH_TOKEN_LIFETIME": timedelta(days=7),
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
        "email": "m.h.mohebbi.1386@gmail.com",
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
            "description": (
                "مدیریت گزارش‌های دریافتی و تغییر وضعیت آن‌ها (فقط ادمین)"
            ),
        },
        {
            "name": "تبیین — عمومی",
            "description": "نمایش محتواهای جهاد تبیین در سایت (با cache بهینه)",
        },
        {
            "name": "تبیین — مدیریت",
            "description": (
                "مدیریت محتواها و اجرای دستی همگام‌سازی (فقط ادمین)"
            ),
        },
        {
            "name": "لاگ فعالیت — مدیریت",
            "description": (
                "مشاهده و جستجوی لاگ‌های فعالیت سیستم (فقط ادمین)"
            ),
        },
        {
            "name": "جایزه‌ای برای عدالت — عمومی",
            "description": (
                "نمایش پروفایل مجرمین منتشرشده به همراه جوایز اعلامی "
                "(بدون نیاز به لاگین)"
            ),
        },
        {
            "name": "جایزه‌ای برای عدالت — کاربر",
            "description": (
                "ارسال گزارش تکمیلی برای پروفایل مجرمین "
                "(نیازمند احراز هویت پایه)"
            ),
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
                "مدیریت کامل پروفایل مجرمین، بررسی گزارشات و "
                "تأیید درخواست‌های لغو (فقط ادمین)"
            ),
        },
        {
            "name": "مددکار — عمومی",
            "description": (
                "نمایش حرکت‌های خیریه و مددکاران به صورت عمومی "
                "(بدون نیاز به لاگین)"
            ),
        },
        {
            "name": "مددکار — کاربر",
            "description": (
                "مشارکت در حرکت‌ها از طریق خرید سهم و پرداخت "
                "(نیازمند لاگین معمولی)"
            ),
        },
        {
            "name": "مددکار — مدیریت (مددکاران)",
            "description": "CRUD کامل نهادهای میزبان حرکت‌ها (فقط ادمین)",
        },
        {
            "name": "مددکار — مدیریت (حرکت‌ها)",
            "description": (
                "ایجاد، انتشار، بستن و مدیریت کامل حرکت‌های خیریه "
                "و گالری تصاویر آن‌ها (فقط ادمین)"
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
            "url": "http://127.0.0.1:8000",
            "description": "محیط توسعه (Local Development)",
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
        "R4JGenderEnum": "apps.r4j.choices.Gender",
        "R4JSocialPlatformEnum": "apps.r4j.choices.SocialPlatform",
        "R4JCriminalAttachmentKindEnum": "apps.r4j.choices.CriminalAttachmentKind",
        "R4JReportStatusEnum": "apps.r4j.choices.ReportStatus",
        "R4JReportFieldChangeStatusEnum": "apps.r4j.choices.ReportFieldChangeStatus",
        "R4JBountyStatusEnum": "apps.r4j.choices.BountyStatus",
        "MadadkarCampaignStatusEnum": "apps.madadkar.choices.CampaignStatus",
        "MadadkarParticipationStatusEnum": "apps.madadkar.choices.ParticipationStatus",
        "MadadkarPaymentStatusEnum": "apps.madadkar.choices.PaymentStatus",
        "LMSCourseLevelEnum": "apps.lms.choices.CourseLevel",
        "LMSCourseStatusEnum": "apps.lms.choices.CourseStatus",
        "LMSEnrollmentStatusEnum": "apps.lms.choices.EnrollmentStatus",
        "LMSDiscussionStatusEnum": "apps.lms.choices.DiscussionStatus",
        "LMSDiscussionReportStatusEnum": "apps.lms.choices.DiscussionReportStatus",
        "LMSQuizAttemptStatusEnum": "apps.lms.choices.QuizAttemptStatus",
        "LMSCertificateStatusEnum": "apps.lms.choices.CertificateStatus",
        "LMSBadgeLevelEnum": "apps.lms.choices.BadgeLevel",
        "LMSVideoProviderEnum": "apps.lms.choices.VideoProvider",
        "KindnessMatchStatusEnum": "apps.kindness_wall.choices.MatchStatus",
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
# Email
# ============================================================================

EMAIL_BACKEND = config(
    "EMAIL_BACKEND",
    default="apps.core.email_backends.ReadableConsoleEmailBackend",
)
EMAIL_HOST = config("EMAIL_HOST", default="smtp.gmail.com")
EMAIL_PORT = config("EMAIL_PORT", default=587, cast=int)
EMAIL_USE_TLS = config("EMAIL_USE_TLS", default=True, cast=bool)
EMAIL_HOST_USER = config("EMAIL_HOST_USER", default="")
EMAIL_HOST_PASSWORD = config("EMAIL_HOST_PASSWORD", default="")
DEFAULT_FROM_EMAIL = config(
    "DEFAULT_FROM_EMAIL",
    default="noreply@setadjang.local",
)

# ============================================================================
# Authentication / OTP
# ============================================================================

OTP_PROVIDER = config("OTP_PROVIDER", default="email")
LOGIN_URL = "/admin/login/"

# ============================================================================
# Shared Redis settings
# ============================================================================

REDIS_URL = config("REDIS_URL", default="redis://127.0.0.1:6379/1")

# ============================================================================
# Logging
# ============================================================================

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
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": "verbose",
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

CELERY_TASK_TIME_LIMIT = 60 * 30
CELERY_TASK_SOFT_TIME_LIMIT = 60 * 25
CELERY_RESULT_EXPIRES = 60 * 60 * 24

CELERY_WORKER_PREFETCH_MULTIPLIER = 1
CELERY_WORKER_MAX_TASKS_PER_CHILD = 100

CELERY_TASK_DEFAULT_QUEUE = "default"
CELERY_TASK_ROUTES = {
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
}

CELERY_BEAT_SCHEDULE = {
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
}

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

# مدت زمان معتبر بودن یک تراکنش PENDING (دقیقه) — بعد از این مدت expire می‌شود
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
MADADKAR_ZARINPAL_SANDBOX = config(
    "MADADKAR_ZARINPAL_SANDBOX",
    default=True,
    cast=bool,
)

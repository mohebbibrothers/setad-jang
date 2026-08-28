"""
Test environment settings for Setad Jang project.

این فایل تنها تنظیمات مخصوص اجرای تست‌ها را روی base/development اعمال
می‌کند و به‌صورت env-driven است:

- ``DATABASE_ENGINE=sqlite``  (پیش‌فرض)  → همان SQLite توسعه؛ بدون نیاز به
  هیچ سرویس خارجی، مناسب اجرای local و توسعهٔ سریع.
- ``DATABASE_ENGINE=postgres``          → PostgreSQL واقعی؛ همان موتوری که
  production استفاده می‌کند. CI با این حالت اجرا می‌شود تا:
    * ``select_for_update`` (قفل‌های ردیفی) واقعاً در SQL ظاهر شود، نه
      اینکه جنگو آن را بی‌صدا حذف کند؛
    * شاخهٔ PostgreSQL فول‌تکست/trigram در ``apps/core/search.py``
      اجرا و تست شود؛
    * اختلاف رفتار بین SQLite و PostgreSQL (خالی/NULL، case sensitivity،
      قفل‌ها) قبل از استقرار در CI کشف شود.

چرا جدا از development.py؟
    توسعه‌دهنده نباید بابت postgres تست‌نویسی کند؛ ولی CI هم نباید
    بی‌صدا روی SQLite بماند. این فایل هر دو دنیا را با یک متغیر جدا
    می‌کند و هیچ تغییری در رفتار development/production نمی‌دهد.

نکته: مقادیر پیش‌فرض POSTGRES_* در این‌جا با docker-compose و CI
هماهنگ‌اند؛ ولی مقادیر واقعی همیشه از environment خوانده می‌شوند.
"""

from .base import config
from .development import *

# ============================================================
# Database — SQLite (default) یا PostgreSQL (واقعی، مثل production)
# ============================================================

_DATABASE_ENGINE = config("DATABASE_ENGINE", default="sqlite").strip().lower()

if _DATABASE_ENGINE == "postgres":
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.postgresql",
            "NAME": config("POSTGRES_DB", default="setadjang"),
            "USER": config("POSTGRES_USER", default="setadjang"),
            "PASSWORD": config("POSTGRES_PASSWORD", default="strong-postgres-password"),
            "HOST": config("POSTGRES_HOST", default="127.0.0.1"),
            "PORT": config("POSTGRES_PORT", default="5432"),
            # در تست، اتصال بلندمدت هیچ سودی ندارد و فقط حالت کهنه‌شدن
            # اتصال بین تست‌ها (مخصوصاً تست‌های thread) را خطرناک می‌کند.
            "CONN_MAX_AGE": 0,
            "CONN_HEALTH_CHECKS": True,
            "OPTIONS": {
                "connect_timeout": config("POSTGRES_CONNECT_TIMEOUT", default=10, cast=int),
            },
            "TEST": {
                "NAME": config("POSTGRES_TEST_DB", default="test_setadjang"),
            },
        },
    }
elif _DATABASE_ENGINE != "sqlite":
    raise RuntimeError(
        "DATABASE_ENGINE نامعتبر است. مقدارهای مجاز برای محیط تست: postgres, sqlite.",
    )
# مقدار "sqlite" همان پیش‌فرض base/development است؛ بدون هیچ تغییری پایین
# می‌آید. اسم دیتابیس تست هم به‌طور خودکار از NAME مشتق می‌شود
# (test_db.sqlite3) و --reuse-db با آن کار می‌کند.

"""
Development environment overrides for Setad Jang project.

این فایل فقط overrideهای مختص محیط توسعه را روی base.py اعمال می‌کند.
هیچ منطق business یا تنظیمات production-grade در اینجا قرار نمی‌گیرد.
"""

from .base import *

# ─── Debug ──────────────────────────────────────────────
DEBUG = True

# ─── REST Framework ─────────────────────────────────────
# اضافه کردن BrowsableAPIRenderer برای دیدن آسان API در مرورگر.
REST_FRAMEWORK = REST_FRAMEWORK.copy()
REST_FRAMEWORK["DEFAULT_RENDERER_CLASSES"] = (
    "rest_framework.renderers.JSONRenderer",
    "rest_framework.renderers.BrowsableAPIRenderer",
)

# ─── Logging level overrides ────────────────────────────
# در محیط توسعه، می‌خواهیم سطح log برای زیرساخت‌های critical
# (cache و کل sub-tree اپ تبیین) به DEBUG برسد تا:
# - cache hit/miss دیده شود
# - فعالیت‌های جزئی sync engine، client، parser و provider قابل ردیابی باشد
#
# نکته:
# با تنظیم سطح روی logger والد `apps.tabyin`، تمام sub-loggerهای آن
# (apps.tabyin.sync.engine, apps.tabyin.sync.client,
#  apps.tabyin.sync.parser, apps.tabyin.providers.mohtavanegar,
#  apps.tabyin.tasks, ...) به‌صورت hierarchical همان سطح را به ارث می‌برند.

LOGGING["loggers"]["apps.core.cache"]["level"] = "DEBUG"
LOGGING["loggers"]["apps.tabyin"]["level"] = "DEBUG"

# برای دیدن SQL query ها (پرفشار — فقط در صورت نیاز فعال کن):
# LOGGING["loggers"]["django.db.backends"] = {
#     "handlers": ["console"],
#     "level": "DEBUG",
#     "propagate": False,
# }

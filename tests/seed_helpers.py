"""
Idempotent re-seeding helpers for tests that depend on data migrations.

چرا وجود دارند؟
هر تستی که با ``django_db(transaction=True)`` اجرا شود، بعد از خودش
``flush`` کامل دیتابیس را صدا می‌زند (``TransactionTestCase._fixture_teardown``).
روی PostgreSQL این یعنی ``TRUNCATE`` روی همهٔ جدول‌ها — از جمله ردیف‌هایی که
مایگریشن‌های data-seed ساخته‌اند. بنابراین پس از اولین تست تراکنشی، seedها
ناپدید می‌شوند و هر تستی که به آن‌ها تکیه دارد باید خودش آن‌ها را بازسازی
کند (این رفتار روی SQLite دیده نمی‌شود، برای همین قبلاً پنهان بود).

این توابع دقیقاً همان منطق مایگریشن را با apps واقعی و به‌صورت idempotent
(همه از ``get_or_create`` استفاده می‌کنند) دوباره اجرا می‌کنند — مثل
executing مجدد مایگریشن روی دادهٔ موجود، که امن است.
"""

from __future__ import annotations

from importlib import import_module

from django.apps import apps as django_apps
from django.db import connection


def reseed_support_taxonomy() -> None:
    """بازسازی taxonomy پیش‌فرض میز پشتیبانی (idempotent)."""
    module = import_module("apps.support_desk.migrations.0002_seed_support_taxonomy")
    module.seed_support_taxonomy(django_apps, connection.schema_editor())


def reseed_notification_templates() -> None:
    """بازسازی قالب‌های پیش‌فرض اعلان‌ها (idempotent)."""
    module = import_module("apps.notifications.migrations.0003_seed_notification_templates")
    module.seed_templates(django_apps, connection.schema_editor())

"""
AppConfig اپ مددکار.

این اپ سیستم مشارکت خیریه سهم‌محور را مدیریت می‌کند.
شامل: مددکاران (Sponsor)، حرکت‌ها (Campaign)، مشارکت (Participation)،
پرداخت (Payment) و زیرساخت اتصال به درگاه پرداخت.
"""

from django.apps import AppConfig


class MadadkarConfig(AppConfig):
    """تنظیمات اپ مددکار — مشارکت خیریه سهم‌محور."""

    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.madadkar"
    verbose_name = "مددکار"

    def ready(self) -> None:
        """Register public cache invalidation signal handlers."""
        from . import signals  # noqa: F401

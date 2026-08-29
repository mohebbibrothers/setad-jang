"""
AppConfig for the Tabyin ingestion application.
"""

from django.apps import AppConfig


class TabyinConfig(AppConfig):
    """Application configuration for TabyinConfig."""

    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.tabyin"
    verbose_name = "جهاد تبیین"

    def ready(self) -> None:
        """اتصال signalها — به‌روزرسانی خودکار نام پدیدآورنده در خروجی عمومی."""
        from django.contrib.auth import get_user_model
        from django.db.models.signals import post_save

        from apps.tabyin.signals import on_user_saved_invalidate_author_cache

        post_save.connect(
            on_user_saved_invalidate_author_cache,
            sender=get_user_model(),
            dispatch_uid="tabyin.invalidate_author_cache_on_user_save",
        )

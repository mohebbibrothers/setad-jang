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
        """
        اتصال signalها.

        - کاربر → به‌روزرسانیِ خودکارِ نامِ پدیدآورنده در خروجیِ عمومی؛
        - محتوا و پیوست (save/delete از هر مسیر، از جمله ادمین جنگو) →
          invalidate کش‌های عمومی تا دیوارِ خانه و فید هرگز محتوای حذف‌شده
          یا نشانیِ کهنه نمایش ندهند.
        """
        from django.contrib.auth import get_user_model
        from django.db.models.signals import post_delete, post_save

        from apps.tabyin.models import TabyinAttachment, TabyinContent
        from apps.tabyin.signals import (
            on_attachment_changed_invalidate_public,
            on_content_deleted_invalidate_public,
            on_content_saved_invalidate_public,
            on_user_saved_invalidate_author_cache,
        )

        post_save.connect(
            on_user_saved_invalidate_author_cache,
            sender=get_user_model(),
            dispatch_uid="tabyin.invalidate_author_cache_on_user_save",
        )
        post_save.connect(
            on_content_saved_invalidate_public,
            sender=TabyinContent,
            dispatch_uid="tabyin.invalidate_public_on_content_save",
        )
        post_delete.connect(
            on_content_deleted_invalidate_public,
            sender=TabyinContent,
            dispatch_uid="tabyin.invalidate_public_on_content_delete",
        )
        post_save.connect(
            on_attachment_changed_invalidate_public,
            sender=TabyinAttachment,
            dispatch_uid="tabyin.invalidate_public_on_attachment_save",
        )
        post_delete.connect(
            on_attachment_changed_invalidate_public,
            sender=TabyinAttachment,
            dispatch_uid="tabyin.invalidate_public_on_attachment_delete",
        )

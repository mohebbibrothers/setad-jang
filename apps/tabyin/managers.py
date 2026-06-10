"""
Managers و QuerySets سفارشی برای مدل‌های اپ تبیین.

از pattern استاندارد `Manager.from_queryset()` استفاده می‌کنیم
تا تمام متدهای QuerySet به‌صورت خودکار روی Manager هم در دسترس باشند.
"""

from django.db import models


class TabyinContentQuerySet(models.QuerySet):
    """QuerySet سفارشی برای محتوای تبیین."""

    def active(self) -> TabyinContentQuerySet:
        """فقط محتواهای فعال و حذف‌نشده در منبع."""
        return self.filter(is_active=True, is_deleted_in_source=False)

    def with_attachments(self) -> TabyinContentQuerySet:
        """Prefetch پیوست‌ها برای جلوگیری از N+1 query."""
        return self.prefetch_related("attachments")

    def deleted_in_source(self) -> TabyinContentQuerySet:
        """محتواهایی که در منبع حذف شده‌اند."""
        return self.filter(is_deleted_in_source=True)


# ─────────────────────────────────────────────────────────────
# Manager پیش‌فرض — فقط محتوای فعال
# با from_queryset، همه متدهای QuerySet (active, with_attachments, ...)
# به‌صورت خودکار روی Manager هم در دسترس هستند.
# ─────────────────────────────────────────────────────────────
class TabyinContentManager(models.Manager.from_queryset(TabyinContentQuerySet)):
    """Manager پیش‌فرض — به‌صورت خودکار فقط محتوای فعال را برمی‌گرداند."""

    def get_queryset(self) -> TabyinContentQuerySet:
        return super().get_queryset().active()


# ─────────────────────────────────────────────────────────────
# Manager برای دسترسی به همه رکوردها (شامل غیرفعال و soft-deleted)
# ─────────────────────────────────────────────────────────────
class TabyinContentAllManager(models.Manager.from_queryset(TabyinContentQuerySet)):
    """Manager برای دسترسی به همه رکوردها — استفاده در ادمین و sync."""

    pass

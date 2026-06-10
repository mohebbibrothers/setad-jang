"""
Managers و QuerySets سفارشی برای مدل‌های اپ تبیین.

از pattern استاندارد `Manager.from_queryset()` استفاده می‌کنیم
تا تمام متدهای QuerySet به‌صورت خودکار روی Manager هم در دسترس باشند.
"""

from __future__ import annotations

from django.db import models

from apps.tabyin.choices import SubmissionStatus


class TabyinContentQuerySet(models.QuerySet):
    """QuerySet سفارشی برای محتوای تبیین."""

    def active(self) -> TabyinContentQuerySet:
        """فقط محتواهای فعال، حذف‌نشده و تأییدشده برای نمایش عمومی."""
        return self.filter(
            is_active=True,
            is_deleted_in_source=False,
            submission_status=SubmissionStatus.APPROVED,
        )

    def pending_review(self) -> TabyinContentQuerySet:
        """محتواهای ارسالی کاربران که هنوز توسط ادمین بررسی نشده‌اند."""
        return self.filter(submission_status=SubmissionStatus.PENDING_REVIEW)

    def user_submitted(self) -> TabyinContentQuerySet:
        """محتواهای ایجادشده توسط کاربران سایت."""
        return self.filter(origin="user_submitted")

    def with_attachments(self) -> TabyinContentQuerySet:
        """Prefetch پیوست‌ها برای جلوگیری از N+1 query."""
        return self.prefetch_related("attachments")

    def deleted_in_source(self) -> TabyinContentQuerySet:
        """محتواهایی که در منبع حذف شده‌اند."""
        return self.filter(is_deleted_in_source=True)


class TabyinContentManager(models.Manager.from_queryset(TabyinContentQuerySet)):
    """Manager پیش‌فرض — فقط محتوای قابل نمایش عمومی را برمی‌گرداند."""

    def get_queryset(self) -> TabyinContentQuerySet:
        return super().get_queryset().active()


class TabyinContentAllManager(models.Manager.from_queryset(TabyinContentQuerySet)):
    """Manager برای دسترسی به همه رکوردها — استفاده در ادمین و sync."""

"""Celery tasks نگهداشت دیوار مهربانی."""

from __future__ import annotations

import logging

from celery import shared_task

logger = logging.getLogger("apps.kindness_wall")


@shared_task(
    name="apps.kindness_wall.tasks.expire_old_listings_task",
    acks_late=True,
    reject_on_worker_lost=True,
    ignore_result=True,
)
def expire_old_listings_task() -> int:
    """منقضی‌کردن دسته‌ای آگهی‌هایی که ``expires_at`` آن‌ها گذشته است.

    دیوار مهربانی بدون این تسک به تابلوی آگهی‌های مرده تبدیل می‌شود؛ برای
    همین در beat تنظیمات روزانه اجرا می‌شود. چون به‌جای save حلقه‌ای از
    bulk ``update`` استفاده می‌شود (سیگنال post_save نمی‌فرستد)، انتهای
    این تابع کش عمومی دامنه صریحاً invalid می‌شود تا تخته با واقعیت بسازد.

    Returns:
        تعداد آگهی‌های منقضی‌شده در این اجرا.
    """
    from apps.core.cache_invalidation import invalidate_public_domain

    from .services import expire_due_listings

    expired_count = expire_due_listings()
    if expired_count:
        invalidate_public_domain("kindness")
        logger.info("Kindness wall listings expired count=%d", expired_count)
    return expired_count


@shared_task(
    name="apps.kindness_wall.tasks.purge_listing_view_marks_task",
    acks_late=True,
    reject_on_worker_lost=True,
    ignore_result=True,
)
def purge_listing_view_marks_task() -> int:
    """پاک‌سازیِ اثرهای بازدیدِ قدیمی (نگهداشتِ جدولِ dedupe).

    جدولِ `KindnessListingView` با هر «بینندهٔ یکتا در هر پنجره» یک ردیف
    می‌گیرد؛ بدونِ پاک‌سازی در طولِ سال بی‌دلیل رشد می‌کند. دو پنجرهٔ آخر
    (پیش‌فرض ۶ ساعته ⇒ ۱۲ ساعت) نگه داشته می‌شود، بقیه حذف.

    Returns:
        تعداد ردیف‌های حذف‌شده در این اجرا.
    """
    from .services import purge_stale_listing_views

    deleted = purge_stale_listing_views()
    return deleted

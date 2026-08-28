"""Celery tasks for Kindness Wall maintenance."""

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
    """Expire published listings whose ``expires_at`` has passed.

    این تسک قبلاً یک stub بود که فقط ``None`` برمی‌گرداند، و در ضمن نه در
    routing تنظیمات بود و نه در beat و نه هیچ‌جای کد صدا زده می‌شد. یعنی
    سه لایه سکوت روی هم: کد مرده‌ای که هیچ‌کس متوجه مرده بودنش نمی‌شد.

    پیامد واقعی‌اش این بود که **هیچ آگهی دیوار مهربانی هرگز منقضی نمی‌شد**.
    فیلد ``expires_at`` پر می‌شد، سرویس ``expire_due_listings`` هم کامل
    پیاده‌سازی شده بود، ولی چیزی صدایش نمی‌زد؛ پس آگهی‌ها برای همیشه در
    وضعیت PUBLISHED می‌ماندند و در فهرست عمومی نمایش داده می‌شدند.

    Returns:
        تعداد آگهی‌هایی که در این اجرا منقضی شدند.
    """
    from .services import expire_due_listings

    expired_count = expire_due_listings()
    if expired_count:
        logger.info("Kindness wall listings expired count=%d", expired_count)
    return expired_count

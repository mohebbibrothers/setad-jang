"""
Celery tasks اپ مددکار.

این ماژول tasks دوره‌ای را شامل می‌شود که در Celery Beat schedule
(در config/settings/base.py) ثبت شده‌اند:

- expire_stale_participations_task: هر 5 دقیقه
    Participationهای PENDING_PAYMENT که از MADADKAR_PAYMENT_TIMEOUT_MINUTES
    دقیقه گذشته را به EXPIRED تغییر می‌دهد و سهم رزرو شده را آزاد می‌کند.

- close_expired_campaigns_task: هر 10 دقیقه
    Campaignهای PUBLISHED با deadline منقضی شده را به CLOSED تغییر می‌دهد.

اصول طراحی:
- هیچ business logic مستقیم در taskها نیست — همه delegate به service layer.
- هر آیتم در حلقه به‌صورت مستقل پردازش می‌شود — اگر یکی fail شود، بقیه ادامه پیدا می‌کنند.
- Task results شامل شمارش‌های دقیق برای monitoring است.
- Error logging کامل با exc_info برای دیباگ.
- Idempotent: اجرای دوباره بدون side-effect (سرویس‌ها idempotent هستند).
- Queue: تمام taskها به queue "madadkar" routing می‌شوند (در settings.CELERY_TASK_ROUTES).
"""

from __future__ import annotations

import logging
from typing import Any

from celery import shared_task

from apps.madadkar.selectors import get_campaigns_due_for_closing
from apps.madadkar.services import (
    close_campaign_due_to_deadline,
    expire_stale_participation,
    generate_financial_control_snapshot,
    get_stale_participations,
)

logger = logging.getLogger("apps.madadkar")


# ===========================================================================
# Expire stale participations
# ===========================================================================


@shared_task(
    name="apps.madadkar.tasks.expire_stale_participations_task",
    bind=True,
    max_retries=3,
    default_retry_delay=60,
)
def expire_stale_participations_task(self) -> dict[str, Any]:
    """
    Periodic task: expire کردن participationهای PENDING_PAYMENT راکد.

    این task هر 5 دقیقه اجرا می‌شود و Participationهایی که از
    MADADKAR_PAYMENT_TIMEOUT_MINUTES دقیقه پیش در حالت PENDING_PAYMENT
    مانده‌اند را EXPIRED می‌کند و سهم رزرو شده را آزاد می‌نماید.

    Returns:
        dict شامل آمار اجرا:
        - total_found: تعداد participationهای پیدا شده برای expire
        - expired_count: تعداد موفق expire شده
        - failed_count: تعداد ناموفق
        - error_details: لیست خطاهای رخ داده (در صورت وجود)

    Error handling:
    - هر participation به‌صورت مستقل پردازش می‌شود.
    - یک شکست باعث توقف کل task نمی‌شود.
    - شکست‌ها لاگ می‌شوند و در نتیجه نهایی گزارش می‌شوند.
    """
    logger.info(
        "Madadkar expire_stale_participations_task started task_id=%s",
        self.request.id,
    )

    stale_participations = list(get_stale_participations())
    total_found = len(stale_participations)

    expired_count = 0
    failed_count = 0
    error_details: list[dict[str, Any]] = []

    for participation in stale_participations:
        try:
            expire_stale_participation(participation=participation)
            expired_count += 1
        except Exception as exc:
            failed_count += 1
            logger.error(
                "Madadkar expire_stale failed participation_id=%s error=%s",
                participation.pk,
                exc,
                exc_info=True,
            )
            error_details.append(
                {
                    "participation_id": participation.pk,
                    "error": str(exc),
                },
            )

    result = {
        "total_found": total_found,
        "expired_count": expired_count,
        "failed_count": failed_count,
        "error_details": error_details,
    }

    logger.info(
        "Madadkar expire_stale_participations_task finished task_id=%s "
        "total=%s expired=%s failed=%s",
        self.request.id,
        total_found,
        expired_count,
        failed_count,
    )

    return result


# ===========================================================================
# Close expired campaigns
# ===========================================================================


@shared_task(
    name="apps.madadkar.tasks.close_expired_campaigns_task",
    bind=True,
    max_retries=3,
    default_retry_delay=60,
)
def close_expired_campaigns_task(self) -> dict[str, Any]:
    """
    Periodic task: بستن خودکار campaignهای با deadline منقضی شده.

    این task هر 10 دقیقه اجرا می‌شود و Campaignهای PUBLISHED که deadline
    آن‌ها گذشته را به CLOSED تغییر می‌دهد.

    Returns:
        dict شامل آمار اجرا:
        - total_found: تعداد campaign پیدا شده برای بستن
        - closed_count: تعداد موفق بسته شده
        - failed_count: تعداد ناموفق
        - error_details: لیست خطاهای رخ داده (در صورت وجود)

    Error handling:
    - هر campaign به‌صورت مستقل پردازش می‌شود.
    - یک شکست باعث توقف کل task نمی‌شود.
    """
    logger.info(
        "Madadkar close_expired_campaigns_task started task_id=%s",
        self.request.id,
    )

    expired_campaigns = list(get_campaigns_due_for_closing())
    total_found = len(expired_campaigns)

    closed_count = 0
    failed_count = 0
    error_details: list[dict[str, Any]] = []

    for campaign in expired_campaigns:
        try:
            close_campaign_due_to_deadline(campaign=campaign)
            closed_count += 1
        except Exception as exc:
            failed_count += 1
            logger.error(
                "Madadkar close_expired_campaign failed campaign_id=%s error=%s",
                campaign.pk,
                exc,
                exc_info=True,
            )
            error_details.append(
                {
                    "campaign_id": campaign.pk,
                    "error": str(exc),
                },
            )

    result = {
        "total_found": total_found,
        "closed_count": closed_count,
        "failed_count": failed_count,
        "error_details": error_details,
    }

    logger.info(
        "Madadkar close_expired_campaigns_task finished task_id=%s total=%s closed=%s failed=%s",
        self.request.id,
        total_found,
        closed_count,
        failed_count,
    )

    return result


# ===========================================================================
# Financial control snapshot
# ===========================================================================


@shared_task(
    name="apps.madadkar.tasks.generate_financial_control_snapshot_task",
    bind=True,
    max_retries=3,
    default_retry_delay=300,
)
def generate_financial_control_snapshot_task(self) -> dict[str, Any]:
    """Periodic task: generate daily Madadkar finance-ops control snapshot."""
    logger.info("Madadkar financial control snapshot task started task_id=%s", self.request.id)
    snapshot = generate_financial_control_snapshot(generated_by_task_id=self.request.id)
    result = {
        "snapshot_id": snapshot.pk,
        "generated_for_date": snapshot.generated_for_date.isoformat(),
        "severity": snapshot.severity,
        "summary": snapshot.summary,
    }
    logger.info(
        "Madadkar financial control snapshot task finished task_id=%s snapshot_id=%s severity=%s",
        self.request.id,
        snapshot.pk,
        snapshot.severity,
    )
    return result

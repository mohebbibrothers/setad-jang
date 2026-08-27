"""
Celery tasks for audit logging.

این ماژول تسک‌های async مربوط به ثبت لاگ فعالیت را شامل می‌شود.

اصول طراحی:
- تسک در برابر خطاهای گذرا مقاوم است (retry با backoff نمایی + jitter).
- `acks_late` فعال است: اگر worker وسط کار کشته شود، پیام دوباره تحویل
  داده می‌شود و رکورد امنیتی گم نمی‌شود.
- تمام آرگومان‌ها JSON-serializable هستند.

چرا این رفتار عوض شد:
    نسخه‌ی قبلی `max_retries=0` و `acks_late=False` داشت و هر exception را
    می‌بلعید. یعنی یک قطعی لحظه‌ای دیتابیس یا کشته‌شدن worker حین deploy،
    رکورد audit را **برای همیشه** حذف می‌کرد و فقط یک خط لاگ باقی می‌ماند.
    برای سیستمی که خودش را append-only و forensic معرفی می‌کند این یک
    تناقض بنیادی بود. حالا خطاهای گذرا retry می‌شوند و فقط پس از اتمام
    تلاش‌ها، خطا به‌صورت CRITICAL ثبت می‌شود تا alerting آن را ببیند.
"""

from __future__ import annotations

import logging
from typing import Any

from celery import shared_task
from django.db import DatabaseError

logger = logging.getLogger("apps.audit_logs")

#: حداکثر تعداد تلاش مجدد برای خطاهای گذرای دیتابیس
AUDIT_TASK_MAX_RETRIES = 5


@shared_task(
    name="apps.audit_logs.tasks.create_audit_log_task",
    bind=True,
    max_retries=AUDIT_TASK_MAX_RETRIES,
    acks_late=True,
    reject_on_worker_lost=True,
    autoretry_for=(DatabaseError,),
    retry_backoff=True,
    retry_backoff_max=60,
    retry_jitter=True,
    ignore_result=True,
)
def create_audit_log_task(
    self,
    *,
    user_id: int | None = None,
    action: str,
    resource_type: str,
    resource_id: str | None = None,
    ip_address: str | None = None,
    request_id: str | None = None,
    user_agent: str = "",
    path: str = "",
    method: str = "",
    changes: dict[str, Any] | None = None,
    extra_data: dict[str, Any] | None = None,
) -> None:
    """
    Celery task برای ثبت audit log به‌صورت async.

    خطاهای گذرای دیتابیس به‌صورت خودکار retry می‌شوند. خطاهای غیرقابل
    بازیابی (مثلاً داده‌ی نامعتبر) با سطح CRITICAL ثبت می‌شوند تا alert
    بدهند، ولی worker را از کار نمی‌اندازند.
    """
    from .services import create_audit_log

    try:
        create_audit_log(
            user_id=user_id,
            action=action,
            resource_type=resource_type,
            resource_id=resource_id,
            ip_address=ip_address,
            request_id=request_id,
            user_agent=user_agent,
            path=path,
            method=method,
            changes=changes,
            extra_data=extra_data,
        )
    except DatabaseError:
        # autoretry_for این را می‌گیرد و با backoff دوباره تلاش می‌کند؛
        # در آخرین تلاش دوباره raise می‌شود و در لاگ Celery می‌نشیند.
        logger.warning(
            "Transient DB error while writing audit log action=%s resource=%s:%s retry=%s",
            action,
            resource_type,
            resource_id,
            self.request.retries,
        )
        raise
    except Exception as exc:
        logger.critical(
            "AUDIT RECORD LOST action=%s resource=%s:%s user_id=%s error=%s",
            action,
            resource_type,
            resource_id,
            user_id,
            exc,
            exc_info=True,
        )

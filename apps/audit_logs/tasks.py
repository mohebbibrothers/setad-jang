"""
Celery tasks for audit logging.

این ماژول تسک‌های async مربوط به ثبت لاگ فعالیت را شامل می‌شود.

اصول طراحی:
- تسک idempotent است (duplicate call مشکلی ایجاد نمی‌کند)
- fail-safe: اگر write fail شود، فقط log می‌زند و retry نمی‌کند
  (audit log از نوع best-effort async است)
- تمام آرگومان‌ها JSON-serializable هستند
"""

from __future__ import annotations

import logging
from typing import Any

from celery import shared_task

logger = logging.getLogger("apps.audit_logs")


@shared_task(
    name="apps.audit_logs.tasks.create_audit_log_task",
    bind=True,
    max_retries=0,
    acks_late=False,
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
    changes: dict[str, Any] | None = None,
    extra_data: dict[str, Any] | None = None,
) -> None:
    """
    Celery task برای ثبت audit log به‌صورت async.

    fail-safe: اگر DB write خطا بدهد، فقط ERROR log می‌زند
    و exception را swallow می‌کند تا worker crash نکند.
    """
    try:
        from .services import create_audit_log

        create_audit_log(
            user_id=user_id,
            action=action,
            resource_type=resource_type,
            resource_id=resource_id,
            ip_address=ip_address,
            request_id=request_id,
            changes=changes,
            extra_data=extra_data,
        )
    except Exception as exc:
        logger.error(
            "Failed to create audit log async action=%s resource=%s:%s error=%s",
            action,
            resource_type,
            resource_id,
            exc,
        )

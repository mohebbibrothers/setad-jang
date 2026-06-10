"""
Audit Log Service Layer.

این ماژول business logic مربوط به ثبت لاگ فعالیت را شامل می‌شود.

اصول طراحی:
- log_action(): ثبت synchronous — برای مواردی که consistency مهم‌تر است
- log_action_async(): ثبت asynchronous — برای مواردی که latency مهم‌تر است
- هر دو از یک create function مرکزی استفاده می‌کنند
- request metadata (IP, request_id) به‌صورت اختیاری قابل ارسال است
"""

from __future__ import annotations

import logging
from typing import Any

from .models import AuditLog

logger = logging.getLogger("apps.audit_logs")


def create_audit_log(
    *,
    user_id: int | None = None,
    action: str,
    resource_type: str,
    resource_id: str | None = None,
    ip_address: str | None = None,
    request_id: str | None = None,
    changes: dict[str, Any] | None = None,
    extra_data: dict[str, Any] | None = None,
) -> AuditLog:
    """
    ثبت یک لاگ فعالیت در دیتابیس.

    این تابع مستقیماً write می‌کند و برای استفاده در Celery task
    یا مستقیم در service layer مناسب است.
    """
    audit_log = AuditLog.objects.create(
        user_id=user_id,
        action=action,
        resource_type=resource_type,
        resource_id=resource_id,
        ip_address=ip_address,
        request_id=request_id,
        changes=changes,
        extra_data=extra_data,
    )

    logger.info(
        "Audit log created action=%s resource=%s:%s user_id=%s ip=%s request_id=%s",
        action,
        resource_type,
        resource_id,
        user_id,
        ip_address,
        request_id,
    )

    return audit_log


def log_action(
    *,
    user_id: int | None = None,
    action: str,
    resource_type: str,
    resource_id: str | None = None,
    ip_address: str | None = None,
    request_id: str | None = None,
    changes: dict[str, Any] | None = None,
    extra_data: dict[str, Any] | None = None,
) -> AuditLog:
    """
    Synchronous audit log — برای مواردی که consistency مهم‌تر از latency است.

    مثال: admin soft-deletes a user → باید قبل از response ثبت شود.
    """
    return create_audit_log(
        user_id=user_id,
        action=action,
        resource_type=resource_type,
        resource_id=resource_id,
        ip_address=ip_address,
        request_id=request_id,
        changes=changes,
        extra_data=extra_data,
    )


def log_action_async(
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
    Asynchronous audit log — برای مواردی که latency مهم‌تر از consistency است.

    مثال: user login → نباید response را کند کند.
    """
    from .tasks import create_audit_log_task

    create_audit_log_task.delay(
        user_id=user_id,
        action=action,
        resource_type=resource_type,
        resource_id=resource_id,
        ip_address=ip_address,
        request_id=request_id,
        changes=changes,
        extra_data=extra_data,
    )

    logger.info(
        "Audit log dispatched async action=%s resource=%s:%s user_id=%s",
        action,
        resource_type,
        resource_id,
        user_id,
    )

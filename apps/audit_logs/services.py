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
    user_agent: str = "",
    path: str = "",
    method: str = "",
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
        user_agent=user_agent,
        path=path,
        method=method,
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
    user_agent: str = "",
    path: str = "",
    method: str = "",
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
        user_agent=user_agent,
        path=path,
        method=method,
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
    user_agent: str = "",
    path: str = "",
    method: str = "",
    changes: dict[str, Any] | None = None,
    extra_data: dict[str, Any] | None = None,
) -> None:
    """
    Asynchronous audit log — برای مواردی که latency مهم‌تر از consistency است.

    مثال: user login → نباید response را کند کند.

    تضمین مهم: این تابع هرگز نباید request را بشکند. در نسخهٔ قبلی اگر
    broker (Redis) در دسترس نبود، ``kombu.OperationalError`` مستقیم به
    view نشت می‌کرد و کل flow کاربری (شروع/ثبت آزمون، login، verify
    پرداخت و...) با ۵۰۰ می‌ساخت — آن‌هم وقتی که کارِ کسب‌وکار قبلاً با
    موفقیت commit شده بود. اکنون:

    1. تلاش برای dispatch تسک (مسیر عادی، بدون latency اضافه).
    2. در صورت هر خطایی (broker down، worker نبودن صف، timeout):
       نوشتن همزمان رکورد audit در همان request تا هیچ رویدادی گم نشود.
    3. اگر نوشتنِ sync هم شکست بخورد (مثلاً DB problem) فقط لاگ می‌گیریم؛
       خطای audit هیچ‌وقت نباید علت ۵۰۰ شدنِ یک درخواست کاربر باشد —
       برای این مسیر fire-and-forget این trade-off آگاهانه است. مسیر
       syncِ ``log_action`` (که audit جزو الزاماتش است) همچنان raise
       می‌کند و تغییر نکرده.
    """
    kwargs: dict[str, Any] = {
        "user_id": user_id,
        "action": action,
        "resource_type": resource_type,
        "resource_id": resource_id,
        "ip_address": ip_address,
        "request_id": request_id,
        "user_agent": user_agent,
        "path": path,
        "method": method,
        "changes": changes,
        "extra_data": extra_data,
    }

    from .tasks import create_audit_log_task

    try:
        create_audit_log_task.delay(**kwargs)
    except Exception:
        logger.warning(
            "audit_logs.async: broker unavailable برای «%s» — نوشتن همزمان به‌عنوان fallback",
            action,
            exc_info=True,
        )
        try:
            create_audit_log(**kwargs)
        except Exception:
            logger.exception(
                "audit_logs.async: fallback sync هم شکست خورد action=%s",
                action,
            )

    logger.info(
        "Audit log dispatched async action=%s resource=%s:%s user_id=%s",
        action,
        resource_type,
        resource_id,
        user_id,
    )

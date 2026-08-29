"""
Celery Tasks — همگام‌سازی غیرهمزمان محتوای تبیین.

این فایل taskهای asynchronous مربوط به app تبیین را نگه می‌دارد.
Taskها فقط orchestration لایه async را انجام می‌دهند و business logic
اصلی داخل service layer باقی می‌ماند.

نکته:
- منطق اصلی sync داخل `apps.tabyin.services.run_sync` قرار دارد.
- این taskها مسئول execution در background، retry و logging هستند.
- خروجی task به‌شکل JSON-serializable برگردانده می‌شود تا Celery/Flower
  بتوانند نتیجه را بدون خطای serialization نمایش دهند.
- outcome audit (started / succeeded / failed) مستقیماً در worker
  و به‌صورت synchronous ثبت می‌شود، اما به‌صورت fail-safe تا اگر
  audit write مشکل داشت، خود task business logic نشکند.
"""

from __future__ import annotations

import logging
from dataclasses import asdict, is_dataclass
from datetime import date, datetime
from typing import Any, Literal

from celery import shared_task

from apps.audit_logs import actions as audit_actions
from apps.audit_logs.services import log_action
from apps.tabyin.services import run_sync
from apps.tabyin.sync.engine import SyncStats

logger = logging.getLogger("apps.tabyin.tasks")


# ============================================================
# JSON serialization helpers
# ============================================================


def _normalize_for_json(value: Any) -> Any:
    """
    تبدیل مقدارهای Python به ساختار قابل JSON serialization.

    چون Celery result backend با serializer=JSON تنظیم شده،
    خروجی task نباید شامل objectهای غیرقابل serialization مثل datetime
    یا dataclass خام باشد.
    """
    if is_dataclass(value):
        return _normalize_for_json(asdict(value))

    if isinstance(value, dict):
        return {str(key): _normalize_for_json(item) for key, item in value.items()}

    if isinstance(value, (list, tuple, set)):
        return [_normalize_for_json(item) for item in value]

    if isinstance(value, (datetime, date)):
        return value.isoformat()

    if value is None or isinstance(value, (str, int, float, bool)):
        return value

    return str(value)


def _serialize_sync_stats(stats: SyncStats) -> dict[str, Any]:
    """
    تبدیل SyncStats به payload نهایی و JSON-friendly.

    اگر SyncStats یک dataclass باشد، به dict تبدیل می‌شود.
    اگر در آینده ساختارش تغییر کند، همچنان این serializer تلاش می‌کند
    خروجی قابل اتکا و قابل نمایش تولید کند.
    """
    normalized = _normalize_for_json(stats)

    if isinstance(normalized, dict):
        return normalized

    return {
        "value": normalized,
    }


# ============================================================
# Audit helpers
# ============================================================


def _safe_log_sync_audit(
    *,
    user_id: int | None,
    action: str,
    task_id: str | None,
    request_id: str | None,
    dispatch_ip: str | None,
    extra_data: dict[str, Any] | None = None,
) -> None:
    """
    ثبت امن audit log برای task outcome.

    اگر خود audit write fail شود، exception swallow می‌شود تا
    business task نشکند.
    """
    try:
        log_action(
            user_id=user_id,
            action=action,
            resource_type="tabyin_sync",
            resource_id=task_id,
            ip_address=dispatch_ip,
            request_id=request_id,
            extra_data=extra_data,
        )
    except Exception:
        logger.exception(
            "Failed to write tabyin sync audit action=%s task_id=%s",
            action,
            task_id,
        )


# ============================================================
# Shared task orchestration
# ============================================================


def _run_sync_task(
    *,
    mode: Literal["incremental", "full"],
    task_id: str | None,
    retries: int,
    max_retries: int,
    triggered_by_user_id: int | None = None,
    request_id: str | None = None,
    dispatch_ip: str | None = None,
) -> dict[str, Any]:
    """
    اجرای orchestration مشترک برای taskهای full و incremental.

    رفتار audit:
    - در شروع هر attempt → TABYIN_SYNC_STARTED
    - در موفقیت → TABYIN_SYNC_SUCCEEDED
    - در failure نهایی → TABYIN_SYNC_FAILED
    - در failureهای میانی فقط log می‌زنیم و task retry می‌شود

    دلیل:
    - تمام execution attemptها قابل مشاهده باشند
    - audit با retry noise بی‌مورد از FAILED پر نشود
    - final outcome شفاف بماند
    """
    attempt = retries + 1

    _safe_log_sync_audit(
        user_id=triggered_by_user_id,
        action=audit_actions.TABYIN_SYNC_STARTED,
        task_id=task_id,
        request_id=request_id,
        dispatch_ip=dispatch_ip,
        extra_data={
            "mode": mode,
            "attempt": attempt,
            "retries_used": retries,
            "max_retries": max_retries,
        },
    )

    logger.info(
        "Background tabyin sync started mode=%s task_id=%s retries=%s",
        mode,
        task_id,
        retries,
    )

    try:
        stats = run_sync(mode=mode)
        serialized_stats = _serialize_sync_stats(stats)

        _safe_log_sync_audit(
            user_id=triggered_by_user_id,
            action=audit_actions.TABYIN_SYNC_SUCCEEDED,
            task_id=task_id,
            request_id=request_id,
            dispatch_ip=dispatch_ip,
            extra_data={
                "mode": mode,
                "attempt": attempt,
                "retries_used": retries,
                "stats": serialized_stats,
            },
        )

        logger.info(
            "Background tabyin sync finished mode=%s task_id=%s stats=%s",
            mode,
            task_id,
            serialized_stats,
        )

        return serialized_stats

    except Exception as exc:
        is_final_failure = retries >= max_retries

        if is_final_failure:
            _safe_log_sync_audit(
                user_id=triggered_by_user_id,
                action=audit_actions.TABYIN_SYNC_FAILED,
                task_id=task_id,
                request_id=request_id,
                dispatch_ip=dispatch_ip,
                extra_data={
                    "mode": mode,
                    "attempt": attempt,
                    "retries_used": retries,
                    "max_retries": max_retries,
                    "error_type": exc.__class__.__name__,
                    "error_message": str(exc),
                },
            )
        else:
            logger.warning(
                (
                    "Background tabyin sync failed and will retry "
                    "mode=%s task_id=%s retries=%s max_retries=%s error_type=%s"
                ),
                mode,
                task_id,
                retries,
                max_retries,
                exc.__class__.__name__,
            )

        logger.exception(
            "Background tabyin sync task failed mode=%s task_id=%s retries=%s",
            mode,
            task_id,
            retries,
        )
        raise


# ============================================================
# Celery tasks
# ============================================================


@shared_task(
    bind=True,
    name="apps.tabyin.tasks.sync_tabyin_incremental_task",
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_backoff_max=600,
    retry_jitter=True,
    retry_kwargs={"max_retries": 3},
)
def sync_tabyin_incremental_task(
    self,
    *,
    triggered_by_user_id: int | None = None,
    request_id: str | None = None,
    dispatch_ip: str | None = None,
) -> dict[str, Any]:
    """
    اجرای incremental sync محتوای تبیین در پس‌زمینه.

    این task معمولاً توسط Celery Beat هر ۳۰ دقیقه اجرا می‌شود،
    اما می‌تواند توسط هر trigger دیگری نیز صدا زده شود.
    """
    task_id = self.request.id
    retries = int(self.request.retries)
    max_retries = int(self.max_retries or 0)

    logger.info(
        ("Incremental tabyin sync task triggered task_id=%s retries=%s triggered_by_user_id=%s"),
        task_id,
        retries,
        triggered_by_user_id,
    )

    return _run_sync_task(
        mode="incremental",
        task_id=task_id,
        retries=retries,
        max_retries=max_retries,
        triggered_by_user_id=triggered_by_user_id,
        request_id=request_id,
        dispatch_ip=dispatch_ip,
    )


@shared_task(
    bind=True,
    name="apps.tabyin.tasks.sync_tabyin_full_task",
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_backoff_max=600,
    retry_jitter=True,
    retry_kwargs={"max_retries": 2},
)
def sync_tabyin_full_task(
    self,
    *,
    triggered_by_user_id: int | None = None,
    request_id: str | None = None,
    dispatch_ip: str | None = None,
) -> dict[str, Any]:
    """
    اجرای full sync محتوای تبیین در پس‌زمینه.

    این task برای sync کامل و زمان‌بندی‌شده استفاده می‌شود
    و چون سنگین‌تر از incremental sync است، معمولاً با فاصله زمانی
    بیشتری اجرا می‌شود.
    """
    task_id = self.request.id
    retries = int(self.request.retries)
    max_retries = int(self.max_retries or 0)

    logger.info(
        "Full tabyin sync task triggered task_id=%s retries=%s triggered_by_user_id=%s",
        task_id,
        retries,
        triggered_by_user_id,
    )

    return _run_sync_task(
        mode="full",
        task_id=task_id,
        retries=retries,
        max_retries=max_retries,
        triggered_by_user_id=triggered_by_user_id,
        request_id=request_id,
        dispatch_ip=dispatch_ip,
    )


@shared_task(
    bind=True,
    name="apps.tabyin.tasks.mirror_tabyin_user_attachments_task",
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_backoff_max=300,
    retry_jitter=True,
    retry_kwargs={"max_retries": 2},
)
def mirror_tabyin_user_attachments_task(self, *, content_id: int) -> dict[str, Any]:
    """
    آینه‌سازیِ پیوست‌های نشانی‌محورِ یک روایتِ مردمی روی استوریج خودمان.

    چرا وجود دارد؟ پیوستی که با نشانیِ بیرونی ثبت شود، با ازدست‌رفتن آن
    نشانی روایتِ منتشرشده را می‌شکند؛ این task آن‌ها را با سدِ SSRF و سقف
    حجم دانلود و محلی می‌کند. خودِ منطق دانلود در apps.tabyin.uploading
    است و این task فقط orchestration است. خرابی هر پیوست به‌صورت مجزا و
    با mirror_status=failed ثبت می‌شود و کل task را نمی‌شکند (نشانیِ
    اصلی به‌عنوان fallback دست‌نخورده می‌ماند).
    """
    logger.info(
        "Mirror user-attachments task started task_id=%s content_id=%s retries=%s",
        self.request.id,
        content_id,
        self.request.retries,
    )
    from apps.tabyin import services

    result = services.mirror_user_content_attachments(content_id=content_id)
    logger.info(
        "Mirror user-attachments task finished task_id=%s result=%s",
        self.request.id,
        result,
    )
    return result

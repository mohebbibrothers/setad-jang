"""
Service Layer — business logic محتوای تبیین.

این فایل تنها مرجع business logic در app تبیین است.
- توابع نوشتن و logicهای پیچیده اینجا قرار می‌گیرند.
- هر عملیاتی که داده را تغییر می‌دهد، cache مربوطه را invalidate می‌کند.
- اجرای async sync نیز از همین لایه به Celery dispatch می‌شود تا
  view مستقیم با Celery internals درگیر نشود.

اصول طراحی:
- View هرگز مستقیماً با Celery AsyncResult کار نمی‌کند.
- این فایل تنها نقطه‌ای است که می‌داند Celery چه taskهایی را اجرا می‌کند.
- تمام خروجی‌های مربوط به taskها به‌صورت ساختار قابل serialize برمی‌گردند.
- metadata مربوط به dispatch به‌صورت optional به task پاس داده می‌شود
  تا worker بتواند outcome audit دقیق‌تری ثبت کند.
"""

from __future__ import annotations

import logging
from dataclasses import asdict, is_dataclass
from datetime import date, datetime
from typing import Any, Literal

from celery.result import AsyncResult
from django.db import transaction
from django.utils import timezone

from apps.core.cache import cache_delete_namespace
from apps.tabyin.choices import SUBMISSION_REVIEWABLE_STATUSES, ContentOrigin, SubmissionStatus
from apps.tabyin.models import TabyinAttachment, TabyinContent
from apps.tabyin.providers import get_tabyin_provider
from apps.tabyin.selectors import (
    PUBLIC_DETAIL_NAMESPACE,
    PUBLIC_LIST_NAMESPACE,
)
from apps.tabyin.sync.engine import SyncEngine, SyncStats

logger = logging.getLogger("apps.tabyin")


SyncMode = Literal["full", "incremental"]


# ============================================================
# Cache invalidation
# ============================================================


def _invalidate_public_caches() -> None:
    """
    Invalidation تمام cacheهای عمومی محتوای تبیین.

    این تابع پس از هر تغییر داده (sync, toggle, ...) صدا زده می‌شود
    تا کاربران داده‌های قدیمی نبینند.
    """
    cache_delete_namespace(PUBLIC_LIST_NAMESPACE)
    cache_delete_namespace(PUBLIC_DETAIL_NAMESPACE)
    logger.info("Public tabyin caches invalidated")



# ============================================================
# Exceptions
# ============================================================


class TabyinServiceError(Exception):
    """Base exception for Tabyin service layer errors."""


class SubmissionNotReviewable(TabyinServiceError):
    """Raised when an admin tries to review a non-pending submission."""


# ============================================================
# User submissions
# ============================================================


@transaction.atomic
def submit_user_content(
    *,
    user: Any,
    title: str,
    description: str,
    attachments: list[dict[str, Any]] | None = None,
) -> TabyinContent:
    """
    Create a user-submitted Tabyin content item in pending-review state.

    User submissions are never public immediately. They become public only after
    admin approval, while externally-synced content remains auto-approved.
    """
    now = timezone.now()
    content = TabyinContent.objects.create(
        title=title,
        description=description,
        origin=ContentOrigin.USER_SUBMITTED,
        submitted_by=user,
        submission_status=SubmissionStatus.PENDING_REVIEW,
        is_active=False,
        is_deleted_in_source=False,
        author_username=getattr(user, "primary_identifier_value", "") or getattr(user, "email", "") or "",
        source_created_at=now,
        source_updated_at=now,
        raw_payload={"source": "user_submission"},
    )

    for index, attachment in enumerate(attachments or []):
        TabyinAttachment.objects.create(
            content=content,
            url=attachment["url"],
            relative_url=attachment.get("url", ""),
            media_type=attachment.get("media_type", "other"),
            title=attachment.get("title", ""),
            order=attachment.get("order", index),
        )

    logger.info(
        "User Tabyin submission created content_id=%s external_id=%s user_id=%s attachments=%s",
        content.pk,
        content.external_id,
        getattr(user, "pk", None),
        len(attachments or []),
    )
    return content


@transaction.atomic
def approve_user_submission(
    *,
    content: TabyinContent,
    admin: Any,
    admin_note: str = "",
) -> TabyinContent:
    """Approve a pending user submission and make it visible publicly."""
    if content.submission_status not in SUBMISSION_REVIEWABLE_STATUSES:
        raise SubmissionNotReviewable("این محتوا قبلاً بررسی شده و قابل بررسی مجدد نیست.")

    content.submission_status = SubmissionStatus.APPROVED
    content.reviewed_by = admin
    content.reviewed_at = timezone.now()
    content.admin_note = admin_note
    content.is_active = True
    content.is_deleted_in_source = False
    content.save(
        update_fields=[
            "submission_status",
            "reviewed_by",
            "reviewed_at",
            "admin_note",
            "is_active",
            "is_deleted_in_source",
            "updated_at",
        ]
    )
    _invalidate_public_caches()
    logger.info(
        "User Tabyin submission approved content_id=%s admin_id=%s",
        content.pk,
        getattr(admin, "pk", None),
    )
    from apps.notifications.domain import notify_tabyin_submission_reviewed

    notify_tabyin_submission_reviewed(submission=content, actor=admin, approved=True)
    return content


@transaction.atomic
def reject_user_submission(
    *,
    content: TabyinContent,
    admin: Any,
    admin_note: str = "",
) -> TabyinContent:
    """Reject a pending user submission and keep it hidden from public listings."""
    if content.submission_status not in SUBMISSION_REVIEWABLE_STATUSES:
        raise SubmissionNotReviewable("این محتوا قبلاً بررسی شده و قابل بررسی مجدد نیست.")

    content.submission_status = SubmissionStatus.REJECTED
    content.reviewed_by = admin
    content.reviewed_at = timezone.now()
    content.admin_note = admin_note
    content.is_active = False
    content.save(
        update_fields=[
            "submission_status",
            "reviewed_by",
            "reviewed_at",
            "admin_note",
            "is_active",
            "updated_at",
        ]
    )
    _invalidate_public_caches()
    logger.info(
        "User Tabyin submission rejected content_id=%s admin_id=%s",
        content.pk,
        getattr(admin, "pk", None),
    )
    from apps.notifications.domain import notify_tabyin_submission_reviewed

    notify_tabyin_submission_reviewed(submission=content, actor=admin, approved=False)
    return content


# ============================================================
# Toggle visibility
# ============================================================


def toggle_content_visibility(
    content: TabyinContent,
    *,
    is_active: bool,
) -> TabyinContent:
    """
    فعال/غیرفعال کردن نمایش یک محتوا روی سایت.

    ادمین می‌تواند محتوایی را از نمایش عمومی حذف/اضافه کند.
    پس از تغییر، cache عمومی invalidate می‌شود.
    """
    content.is_active = is_active
    content.save(update_fields=["is_active", "updated_at"])

    _invalidate_public_caches()

    action = "activated" if is_active else "deactivated"
    logger.info("Content %s %s by admin", content.external_id, action)

    return content


# ============================================================
# Synchronous sync (used by Celery tasks and management commands)
# ============================================================


def run_sync(*, mode: SyncMode = "incremental") -> SyncStats:
    """
    اجرای همگام‌سازی به‌صورت synchronous.

    این تابع توسط:
    - taskهای Celery (در محیط worker)
    - management command `sync_tabyin`
    صدا زده می‌شود.

    View ادمین مستقیماً این تابع را صدا نمی‌زند تا API بلاک نشود.
    """
    logger.info("Running sync via service layer mode=%s", mode)

    with get_tabyin_provider() as provider:
        engine = SyncEngine(provider=provider)

        if mode == "full":
            stats = engine.sync_full()
        else:
            stats = engine.sync_incremental()

    if stats.created > 0 or stats.updated > 0 or stats.soft_deleted > 0:
        _invalidate_public_caches()
        logger.info(
            "Sync changed data created=%d updated=%d soft_deleted=%d caches cleared",
            stats.created,
            stats.updated,
            stats.soft_deleted,
        )
    else:
        logger.info("Sync had no data changes — caches preserved")

    return stats


# ============================================================
# Async sync — dispatch & status
# ============================================================


def dispatch_sync_task(
    *,
    mode: SyncMode = "incremental",
    triggered_by_user_id: int | None = None,
    request_id: str | None = None,
    dispatch_ip: str | None = None,
) -> str:
    """
    قرار دادن task مربوط به sync در صف Celery و بازگرداندن task_id.

    این تابع تنها interface مجاز View برای اجرای async sync است.
    View نباید مستقیم با Celery یا taskها کار کند.

    Note:
    - metadata مربوط به trigger انسانی optional است.
    - Celery Beat و callهای قدیمی بدون این metadata همچنان سازگار می‌مانند.
    """
    # Local import برای جلوگیری از circular import در زمان bootstrap
    from apps.tabyin.tasks import (
        sync_tabyin_full_task,
        sync_tabyin_incremental_task,
    )

    task = sync_tabyin_full_task if mode == "full" else sync_tabyin_incremental_task

    async_result = task.delay(
        triggered_by_user_id=triggered_by_user_id,
        request_id=request_id,
        dispatch_ip=dispatch_ip,
    )
    logger.info(
        (
            "Sync task dispatched mode=%s task_id=%s "
            "triggered_by_user_id=%s request_id=%s"
        ),
        mode,
        async_result.id,
        triggered_by_user_id,
        request_id,
    )

    return async_result.id


def _normalize_for_json(value: Any) -> Any:
    """
    تبدیل مقادیر Python به ساختار قابل JSON serialization.

    هدف: یکپارچه‌سازی خروجی task status برای response API
    حتی اگر task با dataclass یا datetime برگردد.
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


def get_sync_task_status(*, task_id: str) -> dict[str, Any]:
    """
    خواندن وضعیت یک task پس‌زمینه‌ی sync از Celery result backend.

    خروجی این تابع برای `AdminSyncTaskStatusSerializer` آماده است
    و قراردادهای زیر را رعایت می‌کند:
    - state: یکی از مقادیر استاندارد Celery
    - ready: True اگر task به وضعیت نهایی رسیده باشد
    - successful: True/False برای taskهای ready
    - result: payload SyncStats در حالت SUCCESS
    - error: پیام خطا در حالت FAILURE
    """
    async_result = AsyncResult(task_id)

    state = async_result.state
    is_ready = async_result.ready()

    payload: dict[str, Any] = {
        "task_id": task_id,
        "state": state,
        "ready": is_ready,
        "successful": None,
        "result": None,
        "error": None,
    }

    if not is_ready:
        return payload

    payload["successful"] = async_result.successful()

    if async_result.successful():
        raw_result = async_result.result
        normalized = _normalize_for_json(raw_result)

        if isinstance(normalized, dict):
            payload["result"] = normalized
        else:
            payload["result"] = {"value": normalized}
        return payload

    failure_info = async_result.result
    if isinstance(failure_info, BaseException):
        payload["error"] = f"{failure_info.__class__.__name__}: {failure_info}"
    else:
        payload["error"] = str(failure_info)

    return payload

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
from apps.core.cache_invalidation import invalidate_public_domain
from apps.tabyin import uploading
from apps.tabyin.choices import (
    SUBMISSION_REVIEWABLE_STATUSES,
    ContentOrigin,
    MediaType,
    MirrorStatus,
    SubmissionStatus,
)
from apps.tabyin.models import TabyinAttachment, TabyinContent
from apps.tabyin.providers import get_tabyin_provider
from apps.tabyin.selectors import (
    PUBLIC_DETAIL_NAMESPACE,
    PUBLIC_LIST_NAMESPACE,
)
from apps.tabyin.sync.engine import SyncEngine, SyncStats
from apps.tabyin.uploading import StoredMedia

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
    invalidate_public_domain("tabyin")
    logger.info("Public tabyin caches invalidated")


# نامِ عمومی برای مصارف بیرونی (مثلاً signal به‌روزرسانی نام پدیدآورنده).
invalidate_public_caches = _invalidate_public_caches


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


def _create_attachment_rows(
    content: TabyinContent,
    attachments: list[dict[str, Any]],
) -> None:
    """
    ساختِ سطرهای پیوست برای یک محتوای مردمی — منطقِ مشترکِ ثبت و ویرایش.

    - نشانیِ بومی (/media/ خودمان): نتیجه‌ی «آپلود مستقیم» است؛ بلافاصله
      mirrored حساب می‌شود و متادیتا (ابعاد/مدت/حجم) همان‌جا از استوریج
      بازخوانی می‌شود تا قراردادِ متادیتا با محتوای منبع خارجی یکی بماند.
    - نشانیِ بیرونی: برای انتشارِ پایدار باید روی سرور خودمان آینه شود؛
      نشانیِ اصلی در origin_url می‌ماند (rastrear؛ graceful fallback) و
      وضعیت، pending است تا تَسکِ آینه‌سازی آن را بردارد.
    """
    for index, attachment in enumerate(attachments):
        url = str(attachment["url"]).strip()
        media_type = attachment.get("media_type", MediaType.OTHER)
        meta = {"size": "", "duration": 0, "file_size": 0}
        origin_url = ""
        mirror_status = MirrorStatus.NONE
        mime_type = ""

        if uploading.is_local_media_url(url):
            mirror_status = MirrorStatus.MIRRORED
            name = uploading.local_media_name_from_url(url)
            if name:
                stored_meta = uploading.local_attachment_meta(name, media_type) or {}
                meta = {**meta, **stored_meta}
                mime_type = uploading.mimetypes.guess_type(name)[0] or ""
        else:
            origin_url = url
            mirror_status = MirrorStatus.PENDING

        TabyinAttachment.objects.create(
            content=content,
            url=url,
            relative_url=url,
            media_type=media_type,
            title=attachment.get("title", ""),
            order=attachment.get("order", index),
            origin_url=origin_url,
            mirror_status=mirror_status,
            mime_type=mime_type,
            size=str(meta.get("size") or ""),
            duration=int(meta.get("duration") or 0),
            file_size=int(meta.get("file_size") or 0),
        )


def _schedule_mirror_if_needed(content: TabyinContent) -> None:
    """اگر پیوستِ درانتظارِ آینه دارد، تَسک را پس از commit به صف بفرست."""
    if content.attachments.filter(mirror_status=MirrorStatus.PENDING).exists():
        transaction.on_commit(lambda: _dispatch_attachment_mirror(content.pk))


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
        author_username=getattr(user, "primary_identifier_value", "")
        or getattr(user, "email", "")
        or "",
        source_created_at=now,
        source_updated_at=now,
        raw_payload={"source": "user_submission"},
    )

    _create_attachment_rows(content, list(attachments or []))
    _schedule_mirror_if_needed(content)

    logger.info(
        "User Tabyin submission created content_id=%s external_id=%s user_id=%s attachments=%s",
        content.pk,
        content.external_id,
        getattr(user, "pk", None),
        len(attachments or []),
    )
    return content


@transaction.atomic
def update_user_submission(
    *,
    content: TabyinContent,
    title: str | None = None,
    description: str | None = None,
    attachments: list[dict[str, Any]] | None = None,
) -> TabyinContent:
    """
    ویرایشِ روایتِ خود کاربر — با قانونِ «بررسیِ مجدد پس از هر تغییر».

    امنیتِ محتوا: هر ویرایش روی روایتی که قبلاً نتیجه‌ی بررسی گرفته
    (تأیید/رد) آن را دوباره به صفِ بررسی برمی‌گرداند (pending_review،
    مخفی از نمایشِ عمومی، پاک‌شدنِ برگه‌ی بررسیِ قبلی) تا هیچ متن یا
    رسانه‌ای که ادمین ندیده، بی‌واسطه روی دیوارِ عمومی بنشیند؛ مدیر با
    تأییدِ مجدد همان روایت را دوباره منتشر می‌کند؛ روایتی که هنوز در
    انتظار بررسی است (هنوز نتیجه‌ای نگرفته) در همان صف می‌ماند و وضعیتش
    تکراری pending نمی‌شود — صرفاً محتوایش جایگزین می‌گردد.

    پیوست‌ها — اگر ارسال شوند — جایگزینِ کاملِ فهرستِ قبلی می‌شوند
    (replace-all): سطرهای قدیمی پاک و سطرهای جدید با همان قوانینِ ثبت
    (بومی→mirrored / بیرونی→pending + صفِ آینه) ساخته می‌شوند. فایلِ
    فیزیکیِ رسانه‌های حذف‌شده آگاهانه پاک *نمی‌شود*: نامِ فایل‌ها
    یکتاست اما همان نشانی می‌تواند در روایتِ دیگری هم پیوست شده باشد؛
    پاک‌سازیِ استوریج مسئولیتِ تکلیفِ مجزاست، نه ویرایشِ روایت.
    """
    update_fields: set[str] = set()
    if title is not None:
        content.title = title
        update_fields.add("title")
    if description is not None:
        content.description = description
        update_fields.add("description")

    re_pended = False
    if content.submission_status != SubmissionStatus.PENDING_REVIEW:
        re_pended = True
        content.submission_status = SubmissionStatus.PENDING_REVIEW
        content.reviewed_by = None
        content.reviewed_at = None
        content.admin_note = ""
        content.is_active = False
        update_fields.update(
            {"submission_status", "reviewed_by", "reviewed_at", "admin_note", "is_active"}
        )

    if update_fields:
        update_fields.add("updated_at")
        content.save(update_fields=sorted(update_fields))

    if attachments is not None:
        content.attachments.all().delete()
        _create_attachment_rows(content, attachments)
        _schedule_mirror_if_needed(content)

    transaction.on_commit(_invalidate_public_caches)
    logger.info(
        "User Tabyin submission updated content_id=%s re_pended=%s attachments_replaced=%s",
        content.pk,
        re_pended,
        attachments is not None,
    )
    return content


@transaction.atomic
def delete_user_submission(*, content: TabyinContent) -> None:
    """
    حذفِ کاملِ روایتِ خود کاربر (hard-delete).

    سطرِ محتوا و — به‌واسطه‌ی cascade — همه‌ی پیوسته‌اش پاک می‌شوند؛ از آن
    لحظه روایت در دیوارِ خانه، فید، جزئیات و جست‌وجو هیچ‌جا دیده نمی‌شود.
    invalidationِ کش‌های عمومی توسط signalهای post_delete (on_commit)
    انجام می‌شود تا هم حذفِ کاربر، هم حذفِ ادمین و هم حذف‌های برنامه‌ای —
    از جمله از Django admin — را یک‌جا پوشش دهد. فایلِ فیزیکیِ استوریج —
    مثل ویرایش — عمداً باقی می‌ماند.
    """
    logger.info(
        "User Tabyin submission deleted content_id=%s external_id=%s",
        content.pk,
        content.external_id,
    )
    content.delete()


def _dispatch_attachment_mirror(content_pk: int) -> None:
    """Dispatch تَسک آینه‌سازی پیوست‌ها — مقاوم در برابر نبودِ Celery."""
    try:
        from apps.tabyin.tasks import mirror_tabyin_user_attachments_task

        mirror_tabyin_user_attachments_task.delay(content_id=content_pk)
    except Exception:
        logger.exception(
            "Could not dispatch attachment-mirror task for tabyin content %s",
            content_pk,
        )


def mirror_user_content_attachments(*, content_id: int) -> dict[str, Any]:
    """
    آینه‌سازیِ همه‌ی پیوست‌های درانتظار/ناموفقِ یک محتوای ارسالی.

    خروجی JSON-friendly برای تَسک Celery؛ منطقِ دانلودِ دفاعی در
    apps.tabyin.uploading زندگی می‌کند و این تابع فقط orchestrate می‌کند.
    """
    content = TabyinContent.all_objects.filter(pk=content_id).first()
    if content is None:
        return {"content_id": content_id, "mirrored": 0, "failed": 0, "skipped": "missing"}
    attachments = content.attachments.filter(
        mirror_status__in=[MirrorStatus.PENDING, MirrorStatus.FAILED]
    )
    mirrored = 0
    failed = 0
    for attachment in attachments:
        if uploading.mirror_attachment_to_local(attachment):
            mirrored += 1
        else:
            failed += 1
    result = {
        "content_id": content_id,
        "mirrored": mirrored,
        "failed": failed,
        "total": attachments.count(),
    }
    logger.info("Tabyin attachment mirror finished: %s", result)
    return result


def store_user_media_upload(*, user: Any, uploaded_file: Any) -> StoredMedia:
    """نگه‌داشتنِ لایه‌ی view به دور از جزئیاتِ ماژول uploading."""
    return uploading.store_user_upload(uploaded_file=uploaded_file, user=user)


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

    from apps.tabyin.signals import suppress_signal_invalidation

    with get_tabyin_provider() as provider:
        engine = SyncEngine(provider=provider)

        # همگام‌سازی انبوه: signalهای save/delete هر سطر نباید جداگانه کش
        # عمومی را invalidate کنند (طوفانِ invalidate) — این سرویس در پایان،
        # یک‌بار و فقط هنگام تغییرِ واقعی، این کار را انجام می‌دهد.
        with suppress_signal_invalidation():
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
        ("Sync task dispatched mode=%s task_id=%s triggered_by_user_id=%s request_id=%s"),
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

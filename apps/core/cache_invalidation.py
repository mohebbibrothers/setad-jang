"""
Central public cache invalidation helpers.

این ماژول دو مشکل جدی نسخه‌ی قبل را حل می‌کند.

۱) invalidate شدن کش **قبل از commit** (باگ صحت)
    سیگنال‌های `post_save` داخل transaction اجرا می‌شوند. نسخه‌ی قبل
    بلافاصله نسخه‌ی namespace را بالا می‌برد، ولی داده هنوز commit نشده بود.
    نتیجه:

        t0  writer  UPDATE campaign ...            (commit نشده)
        t1  writer  post_save → version V → V+1
        t2  reader  miss روی V+1 → SELECT → داده‌ی **قدیمی**
        t3  reader  cache.set(V+1, داده‌ی قدیمی, hard_ttl)
        t4  writer  COMMIT
        →   تا پایان hard_ttl (تا ۱۵ دقیقه در public_reports) کش
            «داده‌ی قدیمیِ نسخه‌ی جدید» را سرو می‌کند.

    حالا افزایش نسخه هم مثل dispatch به `transaction.on_commit` منتقل شده،
    پس نسخه‌ی جدید فقط زمانی ساخته می‌شود که داده واقعاً قابل خواندن باشد.

۲) طوفان invalidate (باگ کارایی)
    یک donation منجر به ۲۱ بار invalidate کردن namespaceها و ۷ رویداد
    outbox می‌شد، چون هر `.save()` در طول تراکنش یک invalidate مستقل
    می‌ساخت. عملاً کش عمومی مددکار هرگز warm نمی‌شد و ISR فرانت‌اند
    مدام کوبیده می‌شد.

    حالا invalidateها در طول یک transaction جمع (coalesce) می‌شوند: هر
    domain حداکثر یک بار invalidate و یک رویداد outbox تولید می‌کند،
    با اجتماع همه‌ی tag/pathهای درخواست‌شده.

رفتار در برابر rollback:
    صف به دوره‌ی transaction گره خورده و به‌صورت closure به callback پاس
    داده می‌شود. اگر transaction رollback شود، هم callbackهایش توسط جنگو
    دور ریخته می‌شوند و هم صفش در فراخوانی بعدی تشخیص داده و رها می‌شود.
    در سناریوهای گوشه‌ای (rollback یک savepoint) ممکن است یک domain دو بار
    invalidate شود؛ یعنی خطای ممکن همیشه در جهت «invalidate اضافی» است و
    هرگز «invalidate ازدست‌رفته» — که سمت امن این trade-off است.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from functools import partial

from django.conf import settings
from django.db import transaction

from apps.core.cache import cache_delete_namespace
from apps.core.cache_policy import get_cache_policy
from apps.core.frontend_revalidation import revalidate_frontend
from apps.core.models import CacheInvalidationEvent

logger = logging.getLogger("apps.core.cache_invalidation")

#: نام attributeای که وضعیت invalidate روی شیء connection نگه داشته می‌شود.
#: چون به connection وصل است، به‌طور طبیعی per-thread و per-transaction است.
_STATE_ATTR = "_setadjang_pending_public_invalidations"


@dataclass(slots=True)
class _PendingInvalidation:
    """یک invalidate جمع‌شده برای یک domain در طول transaction جاری."""

    domain: str
    tags: set[str] = field(default_factory=set)
    paths: set[str] = field(default_factory=set)


def _pending_queue(using: str | None = None) -> dict[str, _PendingInvalidation]:
    """
    برگرداندن صف invalidate مربوط به transaction جاری.

    شناسه‌ی «دوره‌ی transaction» خودِ شیء لیست `connection.run_on_commit`
    است. جنگو این لیست را در commit، rollback و rollback یک savepoint
    **جایگزین** می‌کند (نه اینکه خالی کند). پس اگر شیء عوض شده باشد یعنی
    transaction قبلی تمام شده و صف قدیمی باید دور انداخته شود.

    بدون این بررسی، یک transaction که rollback می‌شد صفش را روی connection
    باقی می‌گذاشت و تراکنش موفق بعدی آن را تخلیه می‌کرد — یعنی invalidate
    برای تغییری که هرگز رخ نداده بود.
    """
    connection = transaction.get_connection(using)
    epoch = connection.run_on_commit
    state = getattr(connection, _STATE_ATTR, None)
    if state is None or state[0] is not epoch:
        state = (epoch, {})
        setattr(connection, _STATE_ATTR, state)
    return state[1]


def enqueue_cache_invalidation_event(*, domain: str, tags: list[str], paths: list[str]) -> None:
    """Persist and dispatch one cache invalidation outbox event."""
    event = CacheInvalidationEvent.objects.create(domain=domain, tags=tags, paths=paths)

    try:
        from apps.core.tasks import process_cache_invalidation_event_task

        process_cache_invalidation_event_task.delay(event_id=event.pk)
        logger.info("Cache invalidation outbox event queued id=%s domain=%s", event.pk, domain)
    except Exception:
        logger.exception("Failed to queue cache invalidation outbox event id=%s domain=%s", event.pk, domain)


def _apply_invalidation(entry: _PendingInvalidation) -> None:
    """اجرای واقعی یک invalidate جمع‌شده — فقط پس از commit فراخوانی می‌شود."""
    policy = get_cache_policy(entry.domain)
    for namespace in policy.backend_namespaces:
        cache_delete_namespace(namespace)

    tags = sorted(entry.tags)
    paths = sorted(entry.paths)

    if getattr(settings, "CACHE_INVALIDATION_OUTBOX_ENABLED", True):
        enqueue_cache_invalidation_event(domain=entry.domain, tags=tags, paths=paths)
    else:
        revalidate_frontend(tags=tags, paths=paths)

    logger.info(
        "Public domain invalidated domain=%s tags=%s paths=%s",
        entry.domain,
        tags,
        paths,
    )


def _flush_pending_invalidations(queue: dict[str, _PendingInvalidation]) -> None:
    """
    تخلیه‌ی صف invalidate پس از commit موفق transaction.

    صف به‌صورت closure پاس داده می‌شود، نه از روی connection خوانده می‌شود:
    این تضمین می‌کند هر callback دقیقاً همان صفی را تخلیه کند که در
    transaction خودش ساخته شده، حتی اگر تا زمان اجرا transaction دیگری
    شروع شده باشد.
    """
    if not queue:
        return

    drained = list(queue.values())
    queue.clear()

    for entry in drained:
        try:
            _apply_invalidation(entry)
        except Exception:
            logger.exception("Public cache invalidation failed domain=%s", entry.domain)


def invalidate_public_domain(
    domain: str,
    *,
    extra_tags: list[str] | None = None,
    extra_paths: list[str] | None = None,
    using: str | None = None,
) -> None:
    """
    زمان‌بندی invalidate کش backend و revalidation فرانت‌اند پس از commit.

    فراخوانی‌های متعدد روی یک domain در طول یک transaction به یک invalidate
    واحد تبدیل می‌شوند. اعتبارسنجی domain بلافاصله انجام می‌شود تا نام
    اشتباه در همان نقطه‌ی فراخوانی خطا بدهد، نه بعداً داخل callback.
    """
    policy = get_cache_policy(domain)

    queue = _pending_queue(using)
    entry = queue.get(domain)
    if entry is None:
        entry = _PendingInvalidation(
            domain=domain,
            tags=set(policy.frontend_tags),
            paths=set(policy.frontend_paths),
        )
        queue[domain] = entry
        transaction.on_commit(partial(_flush_pending_invalidations, queue), using=using)

    entry.tags.update(extra_tags or ())
    entry.paths.update(extra_paths or ())

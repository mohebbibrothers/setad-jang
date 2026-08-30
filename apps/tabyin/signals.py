"""
Signalهای اپ تبیین — نگهبانِ زنده‌بودنِ کش‌های عمومی.

دو خانواده‌ی hook داریم:

۱) نامِ پدیدآورنده: وقتی حساب کاربری ویرایش می‌شود (نام، ایمیل، موبایل)،
   cacheهای عمومیِ تبیین باطل می‌شوند تا «نام پدیدآورنده»‌ی روایت‌های
   مردمی — که پویا از حساب کاربر خوانده می‌شود — در دیوارِ خانه، فید
   روایت‌ها، جزئیات و جست‌وجو بلافاصله به‌روز بماند.

۲) خودِ محتوا: هر تغییرِ معنادارِ یک TabyinContent (save/delete از هر
   مسیر — Django admin، shell، سرویس‌ها) یا تغییرِ پیوسته‌اش (آینه‌سازی
   که url را محلی می‌کند، جایگزینیِ فهرست در ویرایش، حذفِ cascade) کش‌های
   عمومی را باطل می‌کند. در نبودِ این hookها، حذفِ محتوا از ادمین جنگو
   روی «دیوار جهادتبیین» و فیدِ خانه تا انقضای TTL کش می‌ماند و کلیک
   روی آن به ۴۰۴ می‌رسید — ریشه‌ی گزارشِ کاربر دقیقاً همین بود.

قواعدِ سختِ این فایل:
- invalidation همیشه با transaction.on_commit به بعد از commit موکول
  می‌شود؛ signal در دلِ transactionِ نویسنده اجرا می‌شود و invalidateِ
  زودهنگام، کش «داده‌ی قدیمیِ نسخه‌ی جدید» می‌سازد (race).
- خرابیِ invalidation هرگز عملیاتِ دیتابیس را نمی‌شکند.
- موتورِ همگام‌سازی انبوه با suppress_signal_invalidation این hookها را
  ساکت می‌کند و خودِ services.run_sync یک‌بار در پایان invalidate می‌کند.
"""

from __future__ import annotations

import logging
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

from django.db import transaction

logger = logging.getLogger("apps.tabyin.signals")

# فیلدهایی که تغییرشان بر نامِ نمایشیِ پدیدآورنده اثر دارد.
_AUTHOR_FIELDS = frozenset({"first_name", "last_name", "email", "phone_number"})

# فیلدهای صرفاً bookkeeping‌ای که تغییرشان خروجیِ عمومی (عنوان، شرح،
# نویسنده، رسانه، قابلیت‌مشاهده) را عوض نمی‌کند؛ saveهایی که فقط همین‌ها
# را لمس کنند — مثل کتاب‌داریِ آخرِ یک sync — نیازی به invalidate ندارند.
_NON_PUBLIC_FIELDS = frozenset(
    {
        "updated_at",
        "last_synced_at",
        "content_hash",
        "raw_payload",
        "source_entity_id",
        "source_status",
        "source_type",
    }
)


# ──────────────────────────────────────────────────────────────────────
#  سرکوبِ موقت — ضدِ طوفانِ invalidate در همگام‌سازیِ انبوه
# ──────────────────────────────────────────────────────────────────────

_state = threading.local()


def invalidation_suppressed() -> bool:
    """آیا invalidationِ سیگنالی در thread جاری خاموش است؟"""
    return getattr(_state, "suppress_depth", 0) > 0


@contextmanager
def suppress_signal_invalidation() -> Iterator[None]:
    """
    خاموش‌کردنِ موقتِ invalidationِ سیگنالی در همین thread (قابل‌تودرتو).

    موتورِ sync صدها save/delete می‌کند؛ اگر هر save یک invalidate راه
    بیندازد، هم دیتابیس و هم صفِ outbox خفه می‌شوند و ISR فرانت مدام
    کوبیده می‌شود. خودِ run_sync در پایان — و فقط هنگام تغییرِ واقعی —
    کش‌ها را invalidate می‌کند، پس نبودِ این حلقه هیچ invalidateای از
    دست نمی‌رود.
    """
    _state.suppress_depth = getattr(_state, "suppress_depth", 0) + 1
    try:
        yield
    finally:
        _state.suppress_depth = max(0, _state.suppress_depth - 1)


def _defer_public_cache_invalidation(*, reason: str) -> None:
    """
    invalidate کش‌های عمومیِ تبیین — به‌موکولِ commitِ transactionِ جاری.

    on_commit در autocommit بلافاصله اجرا می‌شود (رفتارِ مطلوب برای
    shell/admin) و داخلِ atomic فقط پس از موفقیتِ کاملِ transaction —
    و هرگز پس از rollback. coalescingِ invalidate_public_domain فلushesِ
    متعددِ یک transaction (مثلاً حذفِ محتوا + cascade پیوست‌هایش) را به
    یک رویداد تبدیل می‌کند.
    """
    if invalidation_suppressed():
        return

    def _invalidate() -> None:
        try:
            from apps.tabyin.services import invalidate_public_caches

            invalidate_public_caches()
            logger.info("Tabyin public caches invalidated (%s)", reason)
        except Exception:
            logger.exception("Could not invalidate tabyin caches (%s)", reason)

    transaction.on_commit(_invalidate)


# ──────────────────────────────────────────────────────────────────────
#  کاربر → نامِ پدیدآورنده‌ی پویا
# ──────────────────────────────────────────────────────────────────────


def on_user_saved_invalidate_author_cache(
    sender: type,
    instance: Any,
    update_fields: frozenset[str] | set[str] | list[str] | tuple[str, ...] | None = None,
    **kwargs: Any,
) -> None:
    """
    Invalidate کش‌های عمومیِ تبیین پس از تغییر نام/شناسه‌های کاربر.

    - ذخیره‌هایی که update_fields مشخص دارند و به فیلدهای نویسنده ربطی
      ندارند (مثل به‌روزرسانی last_login هنگام ورود) نادیده گرفته می‌شوند
      تا کش دم بماند؛
    - ذخیره‌ی کامل (update_fields=None) محتاطانه invalidate می‌کند؛
    - خرابیِ invalidation هرگز ذخیره‌ی کاربر را نمی‌شکند.
    """
    if update_fields is not None and not _AUTHOR_FIELDS.intersection(set(update_fields)):
        return
    _defer_public_cache_invalidation(reason="user_profile_save")


# ──────────────────────────────────────────────────────────────────────
#  محتوا → دیوارِ خانه / فید / جزئیات / جست‌وجو
# ──────────────────────────────────────────────────────────────────────


def on_content_saved_invalidate_public(
    sender: type,
    instance: Any,
    update_fields: frozenset[str] | set[str] | list[str] | tuple[str, ...] | None = None,
    raw: bool = False,
    **kwargs: Any,
) -> None:
    """
    Invalidate پس از ذخیره‌ی هر محتوای تبیین (ساخت/ویرایش/فعال‌سازی).

    هر مسیرِ نوشتن پوشش داده می‌شود — باز/بستنِ is_active و ویرایشِ فیلدها
    از فرمِ ادمین جنگو، تأیید/ردّ در سرویس‌ها، ویرایش‌های دستیِ shell.
    saveهایی که فقط فیلدهای bookkeeping را لمس می‌کنند (مثل زدنِ هش در
    آخرِ sync) و fixtureها (raw=True) کش را بیهوده نمی‌کوبند.
    """
    if raw:
        return
    if update_fields is not None and not set(update_fields).difference(_NON_PUBLIC_FIELDS):
        return
    _defer_public_cache_invalidation(reason="content_save")


def on_content_deleted_invalidate_public(
    sender: type,
    instance: Any,
    **kwargs: Any,
) -> None:
    """
    Invalidate پس از حذفِ هر محتوای تبیین — از هر مسیری.

    این hook ریشه‌ی باگِ «حذف از ادمین ولی نمایش در دیوارِ خانه» را خشک
    می‌کند: queryset.delete() جنگو برای مدلی که signalَش وصل است مسیرِ
    کامل (نه fast-path) را می‌رود و post_delete برای هر نمونه — چه از
    اکشنِ گروهیِ ادمین، چه از فرمِ حذف، چه از shell — اینجا می‌رسد.
    """
    _defer_public_cache_invalidation(reason="content_delete")


def on_attachment_changed_invalidate_public(
    sender: type,
    instance: Any,
    raw: bool = False,
    **kwargs: Any,
) -> None:
    """
    Invalidate پس از هر تغییرِ پیوست (save یا delete).

    دو سناریوی حساس را پوشش می‌دهد: (الف) تَسکِ آینه‌سازی که url پیوستِ
    یک روایتِ تأییدشده را از نشانیِ بیرونی به نشانیِ محلی تعویض می‌کند —
    بدونِ این hook، کشِ جزئیاتِ عمومی تا انقضای TTL نشانیِ قدیمی را سرو
    می‌کرد؛ (ب) جایگزینی/حذفِ پیوست در ویرایشِ کاربر یا cascade حذفِ
    محتوا. saveهای کتاب‌داری داخلِ sync با suppression ساکت‌اند.
    """
    if raw:
        return
    _defer_public_cache_invalidation(reason="attachment_change")

"""
Signalهای اپ تبیین.

تنها signal فعلی: وقتی حساب کاربری ویرایش می‌شود (نام، ایمیل، موبایل)،
cacheهای عمومیِ تبیین باطل می‌شوند تا «نام پدیدآورنده»‌ی روایت‌های
مردمی — که پویا از حساب کاربر خوانده می‌شود — در دیوارِ خانه، فید
روایت‌ها، جزئیات و جست‌وجو بلافاصله به‌روز بماند.
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger("apps.tabyin.signals")

# فیلدهایی که تغییرشان بر نامِ نمایشیِ پدیدآورنده اثر دارد.
_AUTHOR_FIELDS = frozenset({"first_name", "last_name", "email", "phone_number"})


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
    try:
        from apps.tabyin.services import invalidate_public_caches

        invalidate_public_caches()
        logger.info(
            "Tabyin public caches invalidated after user profile save user_id=%s",
            getattr(instance, "pk", None),
        )
    except Exception:
        logger.exception("Could not invalidate tabyin caches after user save")

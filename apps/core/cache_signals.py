"""
Shared registration helper for public-cache invalidation signal handlers.

چرا این ماژول وجود دارد:

هر پنج اپ عمومی (madadkar, r4j, lms, kindness_wall, public_reports) دقیقاً
یک الگو را تکرار می‌کردند و هر پنج‌تا یک اشتباه مشترک داشتند:

    @receiver(post_save)                      # ← بدون sender!
    def invalidate_public_cache_on_save(sender, instance, **kwargs):
        if sender in PUBLIC_INVALIDATION_MODELS:
            ...

ثبت receiver بدون `sender` یعنی Django آن را برای **هر مدل پروژه** صدا
می‌زند و فیلتر کردن در پایتون انجام می‌شود. با ۵ اپ × ۲ سیگنال، هر
`.save()` یا `.delete()` روی هر یک از ۹۵ مدل پروژه — از OTPCode تا
AuditLog تا NotificationDelivery — ده گیرنده‌ی اضافی را اجرا می‌کرد.

این helper همان قرارداد را با `sender=` صریح ثبت می‌کند، پس هر گیرنده
فقط برای مدل‌های خودش فراخوانی می‌شود.

نکات پیاده‌سازی:
- `weak=False` لازم است چون handler یک closure محلی است و در غیر این صورت
  بلافاصله garbage collect می‌شود.
- `dispatch_uid` یکتا از ثبت دوباره در صورت import مجدد ماژول جلوگیری می‌کند.
"""

from __future__ import annotations

import logging
from collections.abc import Iterable
from typing import Any

from django.db.models import Model
from django.db.models.signals import post_delete, post_save

from apps.core.cache_invalidation import invalidate_public_domain


def register_public_cache_invalidation(
    *,
    domain: str,
    models: Iterable[type[Model]],
    logger: logging.Logger,
) -> None:
    """
    اتصال گیرنده‌های post_save/post_delete برای مدل‌های یک domain عمومی.

    Args:
        domain: نام domain در رجیستری سیاست کش (`apps.core.cache_policy`).
        models: مدل‌هایی که تغییرشان روی داده‌ی عمومی اثر دارد.
        logger: لاگر اپ فراخوان، تا خطاها زیر نام همان اپ ثبت شوند.
    """

    def _invalidate(sender: type[Model], instance: Any, **kwargs: Any) -> None:
        """درخواست invalidate کش عمومی برای یک رویداد مدل."""
        try:
            invalidate_public_domain(domain)
        except Exception:
            logger.exception(
                "Public cache invalidation failed domain=%s sender=%s pk=%s",
                domain,
                sender.__name__,
                getattr(instance, "pk", None),
            )

    for model in models:
        label = model._meta.label_lower
        post_save.connect(
            _invalidate,
            sender=model,
            weak=False,
            dispatch_uid=f"public-cache-invalidation:save:{domain}:{label}",
        )
        post_delete.connect(
            _invalidate,
            sender=model,
            weak=False,
            dispatch_uid=f"public-cache-invalidation:delete:{domain}:{label}",
        )

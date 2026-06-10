"""
ابزارهای cache سطح پایین برای استفاده در serviceها و selectorها.

به جای استفاده از @cache_page (که با DRF سازگاری کامل ندارد)،
از این helperها برای cache کردن دقیق و قابل کنترل داده‌ها استفاده می‌کنیم.

ویژگی‌ها:
- کلیدسازی استاندارد و خوانا
- پشتیبانی از cache versioning برای invalidation سریع کل یک namespace
- Type hints کامل
- Logging حرفه‌ای
- پشتیبانی از هر backend cache جنگو (locmem, redis, memcached, ...)
"""

import hashlib
import logging
from collections.abc import Callable
from typing import Any, TypeVar

from django.core.cache import cache

logger = logging.getLogger(__name__)

T = TypeVar("T")

# پیشوند تمام cache keyهای پروژه — جلوگیری از تداخل با اپلیکیشن‌های دیگر
_CACHE_KEY_PREFIX = "setadjang"


def make_cache_key(namespace: str, *parts: Any) -> str:
    """
    ساخت cache key استاندارد و یکدست.

    اگر طول قسمت‌ها زیاد باشد، با هش SHA-256 کوتاه می‌شود تا از محدودیت
    طول کلید در backendهایی مثل memcached جلوگیری شود.

    Args:
        namespace: فضای نام (مثلاً "tabyin:public_list")
        *parts: قسمت‌های متغیر کلید (مثلاً page=1, page_size=20)

    Returns:
        کلید نهایی به شکل: "setadjang:tabyin:public_list:1:20"

    Examples:
        >>> make_cache_key("tabyin:public_list", 1, 20)
        'setadjang:tabyin:public_list:1:20'
    """
    raw_parts = [str(part) for part in parts]
    raw_key = ":".join([_CACHE_KEY_PREFIX, namespace, *raw_parts])

    # اگر کلید خیلی طولانی شد، هش‌اش کن
    if len(raw_key) > 200:
        digest = hashlib.sha256(raw_key.encode("utf-8")).hexdigest()[:32]
        return f"{_CACHE_KEY_PREFIX}:{namespace}:hashed:{digest}"

    return raw_key


def cache_get_or_set(
    key: str,
    factory: Callable[[], T],
    timeout: int = 60,
) -> T:
    """
    دریافت مقدار از cache یا ساخت و ذخیره آن در صورت عدم وجود.

    این تابع یک wrapper تمیز روی `cache.get_or_set` جنگو با logging است.

    Args:
        key: کلید cache (از `make_cache_key` استفاده کن)
        factory: تابعی که مقدار اولیه را می‌سازد (در صورت cache miss صدا زده می‌شود)
        timeout: زمان اعتبار cache به ثانیه (پیش‌فرض ۶۰ ثانیه)

    Returns:
        مقدار cache شده یا ساخته‌شده توسط factory.

    Examples:
        >>> data = cache_get_or_set(
        ...     key=make_cache_key("tabyin:public_list", 1, 20),
        ...     factory=lambda: list(get_public_contents()[:20]),
        ...     timeout=60,
        ... )
    """
    cached = cache.get(key)
    if cached is not None:
        logger.debug("Cache HIT: %s", key)
        return cached

    logger.debug("Cache MISS: %s — building...", key)
    value = factory()
    cache.set(key, value, timeout=timeout)
    return value


def cache_delete(key: str) -> None:
    """حذف یک کلید مشخص از cache."""
    cache.delete(key)
    logger.debug("Cache DELETED: %s", key)


def cache_delete_namespace(namespace: str) -> None:
    """
    Invalidation کل یک namespace با افزایش version.

    این روش بسیار سریع‌تر از حذف تک‌تک کلیدهاست — به جای حذف،
    ورژن namespace را افزایش می‌دهیم و کلیدهای قدیمی خود به خود از طریق timeout منقضی می‌شوند.

    Args:
        namespace: فضای نام (مثلاً "tabyin:public_list")

    Note:
        برای استفاده از این مکانیسم، باید در `make_cache_key` نسخه را
        به‌عنوان یکی از parts ارسال کنی. مثال:

        >>> version = get_namespace_version("tabyin:public_list")
        >>> key = make_cache_key("tabyin:public_list", version, page, page_size)
    """
    version_key = f"{_CACHE_KEY_PREFIX}:version:{namespace}"
    try:
        new_version = cache.incr(version_key)
    except ValueError:
        # کلید version هنوز وجود ندارد — مقدار اولیه می‌گذاریم
        new_version = 1
        cache.set(version_key, new_version, timeout=None)

    logger.info(
        "Cache namespace invalidated: %s (new version=%d)",
        namespace,
        new_version,
    )


def get_namespace_version(namespace: str) -> int:
    """
    دریافت نسخه فعلی یک namespace برای ساخت cache key.

    اگر نسخه‌ای وجود نداشته باشد، ۱ برمی‌گرداند.

    Args:
        namespace: فضای نام

    Returns:
        نسخه فعلی namespace (عدد صحیح ≥ ۱)
    """
    version_key = f"{_CACHE_KEY_PREFIX}:version:{namespace}"
    version = cache.get(version_key)
    if version is None:
        cache.set(version_key, 1, timeout=None)
        return 1
    return int(version)

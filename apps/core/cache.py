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
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, TypeVar

from django.core.cache import cache

from apps.core.metrics import CACHE_INVALIDATIONS_TOTAL, CACHE_OPERATIONS_TOTAL

logger = logging.getLogger(__name__)

T = TypeVar("T")


@dataclass(slots=True)
class SwrCacheEnvelope:
    """Serializable cache envelope for stale-while-revalidate reads."""

    value: Any
    created_at: float
    soft_expires_at: float
    hard_expires_at: float

    def is_fresh(self, now: float) -> bool:
        """Return True while the soft TTL is still valid."""
        return now < self.soft_expires_at

    def is_usable(self, now: float) -> bool:
        """Return True while the hard TTL is still valid."""
        return now < self.hard_expires_at


def _make_swr_envelope(*, value: Any, now: float, soft_ttl: int, hard_ttl: int) -> dict[str, Any]:
    """Build a JSON-serializable SWR envelope for Redis JSON serializers."""
    return {
        "__swr_cache_envelope__": True,
        "value": value,
        "created_at": now,
        "soft_expires_at": now + soft_ttl,
        "hard_expires_at": now + hard_ttl,
    }


def _is_swr_envelope(value: Any) -> bool:
    """Return whether a cached value is a supported SWR envelope."""
    return isinstance(value, (dict, SwrCacheEnvelope)) and (
        isinstance(value, SwrCacheEnvelope) or value.get("__swr_cache_envelope__") is True
    )


def _envelope_value(envelope: dict[str, Any] | SwrCacheEnvelope) -> Any:
    """Extract payload from a supported SWR envelope."""
    if isinstance(envelope, SwrCacheEnvelope):
        return envelope.value
    return envelope["value"]


def _envelope_is_fresh(envelope: dict[str, Any] | SwrCacheEnvelope, now: float) -> bool:
    """Return whether an SWR envelope is still within soft TTL."""
    if isinstance(envelope, SwrCacheEnvelope):
        return envelope.is_fresh(now)
    return now < float(envelope["soft_expires_at"])


def _envelope_is_usable(envelope: dict[str, Any] | SwrCacheEnvelope, now: float) -> bool:
    """Return whether an SWR envelope is still within hard TTL."""
    if isinstance(envelope, SwrCacheEnvelope):
        return envelope.is_usable(now)
    return now < float(envelope["hard_expires_at"])

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
    namespace = key.split(":", 2)[1] if ":" in key else "unknown"
    if cached is not None:
        CACHE_OPERATIONS_TOTAL.labels(namespace=namespace, operation="get", outcome="hit").inc()
        logger.debug("Cache HIT: %s", key)
        return cached

    CACHE_OPERATIONS_TOTAL.labels(namespace=namespace, operation="get", outcome="miss").inc()
    logger.debug("Cache MISS: %s — building...", key)
    value = factory()
    cache.set(key, value, timeout=timeout)
    CACHE_OPERATIONS_TOTAL.labels(namespace=namespace, operation="set", outcome="success").inc()
    return value



def cache_get_or_set_swr(
    *,
    key: str,
    factory: Callable[[], T],
    soft_ttl: int,
    hard_ttl: int,
    lock_ttl: int = 15,
) -> T:
    """Return cached data using stale-while-revalidate with dogpile protection.

    On soft-expired values, one request refreshes synchronously while other
    concurrent requests may serve the stale value until hard_ttl. If the refresh
    fails and a usable stale value exists, stale data is returned (fail-open).
    """
    now = time.time()
    namespace = key.split(":", 2)[1] if ":" in key else "unknown"
    envelope = cache.get(key)

    if _is_swr_envelope(envelope):
        if _envelope_is_fresh(envelope, now):
            CACHE_OPERATIONS_TOTAL.labels(namespace=namespace, operation="swr_get", outcome="fresh").inc()
            return _envelope_value(envelope)
        if _envelope_is_usable(envelope, now):
            lock_key = f"{key}:lock"
            if cache.add(lock_key, "1", timeout=lock_ttl):
                try:
                    value = factory()
                except Exception:
                    CACHE_OPERATIONS_TOTAL.labels(namespace=namespace, operation="swr_refresh", outcome="error_stale").inc()
                    logger.exception("SWR refresh failed for %s; serving stale value", key)
                    return _envelope_value(envelope)
                finally:
                    cache.delete(lock_key)
                refreshed = _make_swr_envelope(
                    value=value,
                    now=now,
                    soft_ttl=soft_ttl,
                    hard_ttl=hard_ttl,
                )
                cache.set(key, refreshed, timeout=hard_ttl)
                CACHE_OPERATIONS_TOTAL.labels(namespace=namespace, operation="swr_refresh", outcome="success").inc()
                return value
            CACHE_OPERATIONS_TOTAL.labels(namespace=namespace, operation="swr_get", outcome="stale_locked").inc()
            return _envelope_value(envelope)

    CACHE_OPERATIONS_TOTAL.labels(namespace=namespace, operation="swr_get", outcome="miss").inc()
    value = factory()
    envelope = _make_swr_envelope(value=value, now=now, soft_ttl=soft_ttl, hard_ttl=hard_ttl)
    cache.set(key, envelope, timeout=hard_ttl)
    CACHE_OPERATIONS_TOTAL.labels(namespace=namespace, operation="swr_set", outcome="success").inc()
    return value

def cache_delete(key: str) -> None:
    """حذف یک کلید مشخص از cache."""
    cache.delete(key)
    namespace = key.split(":", 2)[1] if ":" in key else "unknown"
    CACHE_OPERATIONS_TOTAL.labels(namespace=namespace, operation="delete", outcome="success").inc()
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

    CACHE_INVALIDATIONS_TOTAL.labels(namespace=namespace).inc()
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

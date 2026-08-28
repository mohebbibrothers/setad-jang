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

# sentinel یکتا برای تشخیص «چیزی پیدا نشد» از «مقدار None کش شده».
_SWR_MISSING = object()

# سقف انتظار در مسیر کش سرد. عمداً کوتاه است: هدف حذف stampede است، نه
# سریالایز کردن درخواست‌ها پشت یک قفل کند.
_SWR_COLD_WAIT_SECONDS = 2.0
_SWR_COLD_POLL_SECONDS = 0.05


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


def _swr_store(
    *,
    key: str,
    value: Any,
    soft_ttl: int,
    hard_ttl: int,
) -> None:
    """Persist a freshly built value in a new SWR envelope.

    زمان مبنای envelope **بعد از** اجرای factory گرفته می‌شود. اگر factory سه
    ثانیه طول کشیده باشد و از `now` قبل از آن استفاده کنیم، مقدار تازه‌ساخته
    سه ثانیه از عمرش را همان لحظهٔ تولد از دست داده است.
    """
    envelope = _make_swr_envelope(
        value=value,
        now=time.time(),
        soft_ttl=soft_ttl,
        hard_ttl=hard_ttl,
    )
    cache.set(key, envelope, timeout=hard_ttl)


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

    دو نکتهٔ ظریف که این پیاده‌سازی رعایت می‌کند:

    1. قفل تا **بعد از** نوشتن مقدار در کش نگه داشته می‌شود. اگر قفل در
       `finally` و پیش از `cache.set` آزاد شود، یک پنجرهٔ کوچک باز می‌ماند که
       در آن درخواست دیگری قفل را می‌گیرد و همان کار سنگین را دوباره انجام
       می‌دهد — یعنی دقیقاً همان dogpileای که قرار بود بسته شود.
    2. مسیر «کش کاملاً خالی» هم قفل دارد. این بدترین حالت stampede است
       (استارت سرد یا درست بعد از invalidate) و بدون قفل، همهٔ درخواست‌های
       همزمان با هم factory را اجرا می‌کنند. کسی که قفل را نمی‌گیرد کوتاه
       منتظر می‌ماند تا نتیجهٔ برندهٔ قفل ظاهر شود و فقط اگر ظاهر نشد خودش
       می‌سازد (fail-open، نه fail-slow).
    """
    now = time.time()
    namespace = key.split(":", 2)[1] if ":" in key else "unknown"
    lock_key = f"{key}:lock"
    envelope = cache.get(key)

    if _is_swr_envelope(envelope):
        if _envelope_is_fresh(envelope, now):
            CACHE_OPERATIONS_TOTAL.labels(
                namespace=namespace, operation="swr_get", outcome="fresh"
            ).inc()
            return _envelope_value(envelope)

        if _envelope_is_usable(envelope, now):
            # مقدار کهنه ولی قابل‌سرو داریم: فقط یک نفر refresh می‌کند،
            # بقیه بدون هیچ انتظاری همان کهنه را می‌گیرند.
            if not cache.add(lock_key, "1", timeout=lock_ttl):
                CACHE_OPERATIONS_TOTAL.labels(
                    namespace=namespace, operation="swr_get", outcome="stale_locked"
                ).inc()
                return _envelope_value(envelope)
            try:
                value = factory()
            except Exception:
                CACHE_OPERATIONS_TOTAL.labels(
                    namespace=namespace, operation="swr_refresh", outcome="error_stale"
                ).inc()
                logger.exception("SWR refresh failed for %s; serving stale value", key)
                cache.delete(lock_key)
                return _envelope_value(envelope)
            try:
                _swr_store(key=key, value=value, soft_ttl=soft_ttl, hard_ttl=hard_ttl)
            finally:
                # قفل فقط پس از نوشتن آزاد می‌شود.
                cache.delete(lock_key)
            CACHE_OPERATIONS_TOTAL.labels(
                namespace=namespace, operation="swr_refresh", outcome="success"
            ).inc()
            return value

    # از اینجا به بعد یعنی کش خالی است یا مقدار موجود از hard_ttl هم گذشته.
    CACHE_OPERATIONS_TOTAL.labels(namespace=namespace, operation="swr_get", outcome="miss").inc()

    if not cache.add(lock_key, "1", timeout=lock_ttl):
        waited = _await_swr_value(key=key, timeout=_SWR_COLD_WAIT_SECONDS)
        if waited is not _SWR_MISSING:
            CACHE_OPERATIONS_TOTAL.labels(
                namespace=namespace, operation="swr_get", outcome="cold_awaited"
            ).inc()
            return waited
        # برندهٔ قفل به‌موقع جواب نداد؛ به‌جای بلوکه ماندن، خودمان می‌سازیم.
        CACHE_OPERATIONS_TOTAL.labels(
            namespace=namespace, operation="swr_get", outcome="cold_timeout"
        ).inc()
        value = factory()
        _swr_store(key=key, value=value, soft_ttl=soft_ttl, hard_ttl=hard_ttl)
        return value

    try:
        value = factory()
    except Exception:
        cache.delete(lock_key)
        raise
    try:
        _swr_store(key=key, value=value, soft_ttl=soft_ttl, hard_ttl=hard_ttl)
    finally:
        cache.delete(lock_key)
    CACHE_OPERATIONS_TOTAL.labels(namespace=namespace, operation="swr_set", outcome="success").inc()
    return value


def _await_swr_value(*, key: str, timeout: float) -> Any:
    """Poll briefly for another worker's in-flight SWR result.

    فقط در مسیر کش سرد استفاده می‌شود. مقدار برگشتی `_SWR_MISSING` یعنی در
    مهلت مقرر چیزی ظاهر نشد و فراخوان باید خودش مقدار را بسازد.
    """
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        time.sleep(_SWR_COLD_POLL_SECONDS)
        envelope = cache.get(key)
        if _is_swr_envelope(envelope) and _envelope_is_usable(envelope, time.time()):
            return _envelope_value(envelope)
    return _SWR_MISSING


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
        # کلید version وجود ندارد. توضیح مفصل در `_seed_namespace_version`:
        # عمداً از ۱ شروع نمی‌کنیم.
        new_version = _seed_namespace_version(version_key)

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
        return _seed_namespace_version(version_key)
    return int(version)


def _seed_namespace_version(version_key: str) -> int:
    """Create a namespace version that can never collide with an older one.

    اینجا یک باگ صحت پنهان وجود داشت. کلید version با ``timeout=None``
    ذخیره می‌شود، ولی «بدون انقضا» به معنی «حذف‌نشدنی» نیست: اگر ردیس با
    ``maxmemory-policy=allkeys-lru`` بالا آمده باشد — که پیکربندی بسیار
    رایجی است — این کلید هم مثل هر کلید دیگری قابل evict شدن است.

    در پیاده‌سازی قبلی، نبودِ کلید یعنی «برگرد به نسخهٔ ۱». پیامدش این بود:
    namespaceای که مثلاً به نسخهٔ ۷ رسیده بود، بعد از یک evict دوباره
    نسخهٔ ۱ می‌شد و سیستم شروع می‌کرد به خواندن کلیدهای نسخهٔ ۱ که هنوز
    منقضی نشده بودند — یعنی **سرو کردن دادهٔ خیلی قدیمی، بی‌صدا، و فقط
    تحت فشار حافظه**. بدترین نوع باگ: در تست هرگز دیده نمی‌شود.

    راه‌حل: به‌جای عدد ثابت ۱، از مهر زمانی یونیکس به‌عنوان مقدار اولیه
    استفاده می‌کنیم. چون زمان همیشه رو به جلو می‌رود، هر بار که کلید
    version دوباره ساخته شود مقدارش قطعاً **بزرگ‌تر از هر نسخهٔ قبلی**
    است. بنابراین کلیدهای کش قدیمی دیگر هرگز خوانده نمی‌شوند و خودشان
    با hard_ttl پاک می‌شوند. این راه‌حل مستقل از سیاست eviction ردیس کار
    می‌کند و نیازی به هماهنگی با تیم زیرساخت ندارد.
    """
    # دقت میلی‌ثانیه‌ای عمدی است: با دقت ثانیه، اگر یک namespace چند بار در
    # همان ثانیه invalidate شود و بلافاصله کلیدش evict شود، مقدار بازسازی‌شده
    # می‌تواند از آخرین نسخهٔ واقعی کوچک‌تر باشد. با میلی‌ثانیه، برای برخورد
    # باید بیش از هزار invalidate در یک میلی‌ثانیه رخ دهد.
    seed = int(time.time() * 1000)
    cache.set(version_key, seed, timeout=None)
    return seed

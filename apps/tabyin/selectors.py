"""
Selector Layer — تمام query های خواندن محتوای تبیین.

این لایه فقط وظیفه‌ی خواندن دارد:
- queryهای ساده روی مدل‌های تبیین
- نسخه‌های cache شده با invalidation هدف‌مند

اصول طراحی cache:
- در لایه‌ی cache هرگز Model instance ذخیره نمی‌کنیم؛ چون باعث وابستگی
  به Pickle و خطاهای JSON serialization می‌شود.
- به‌جای آن، یک **شناسه‌ی پایدار (external_id)** را cache می‌کنیم و دوباره
  از طریق ORM/index سریع بازمی‌خوانیم.
- این الگو با همه‌ی backendهای cache (locmem, redis, memcached) سازگار است
  و مصرف RAM در Redis را پایین نگه می‌دارد.
"""

import logging
from typing import Any

from django.db.models import QuerySet

from apps.core.cache import (
    cache_get_or_set,
    get_namespace_version,
    make_cache_key,
)
from apps.tabyin.models import TabyinContent

logger = logging.getLogger("tabyin")


# ============================================================
# Cache Configuration
# ============================================================

# Namespace‌های cache برای invalidation هدف‌مند
PUBLIC_LIST_NAMESPACE = "tabyin:public_list"
PUBLIC_DETAIL_NAMESPACE = "tabyin:public_detail"

# مدت اعتبار cache (ثانیه)
PUBLIC_LIST_CACHE_TTL = 60  # لیست عمومی: ۱ دقیقه
PUBLIC_DETAIL_CACHE_TTL = 300  # جزئیات: ۵ دقیقه

# مقدار sentinel برای ذخیره‌ی "این external_id موجود نیست" در cache.
# با این کار از stampede روی missهای ناموجود جلوگیری می‌کنیم.
_DETAIL_NOT_FOUND_SENTINEL = "__not_found__"


# ============================================================
# Public Selectors
# ============================================================


def get_public_contents() -> QuerySet[TabyinContent]:
    """
    لیست محتواهای عمومی (برای نمایش در سایت).

    - فقط فعال و حذف‌نشده در منبع
    - با prefetch پیوست‌ها
    """
    return TabyinContent.objects.with_attachments().order_by("-source_created_at")


def get_public_content_by_external_id(
    external_id: str,
) -> TabyinContent | None:
    """
    جزئیات یک محتوای عمومی با external_id.

    Returns:
        TabyinContent یا None اگر پیدا نشد.
    """
    try:
        return TabyinContent.objects.with_attachments().get(external_id=external_id)
    except TabyinContent.DoesNotExist:
        return None


def get_public_content_detail_cached(
    external_id: str,
) -> TabyinContent | None:
    """
    نسخه cache شده از get_public_content_by_external_id.

    استراتژی:
    - فقط یک "marker" در cache نگه می‌داریم: یا external_id (string)،
      یا sentinel _DETAIL_NOT_FOUND_SENTINEL.
    - object واقعی همیشه در همان لحظه از DB با index یکتای external_id
      خوانده می‌شود (که cost بسیار پایین دارد).
    - این رویکرد:
      * با هر serializer (JSON/Pickle) سازگار است
      * مصرف RAM در Redis را پایین نگه می‌دارد
      * stale data در سطح relation تولید نمی‌کند

    مدت cache: PUBLIC_DETAIL_CACHE_TTL
    Invalidation: از طریق namespace versioning (در service layer)
    """
    version = get_namespace_version(PUBLIC_DETAIL_NAMESPACE)
    key = make_cache_key(PUBLIC_DETAIL_NAMESPACE, version, external_id)

    cached_marker: str = cache_get_or_set(
        key=key,
        factory=lambda: _build_detail_cache_marker(external_id),
        timeout=PUBLIC_DETAIL_CACHE_TTL,
    )

    if cached_marker == _DETAIL_NOT_FOUND_SENTINEL:
        return None

    return get_public_content_by_external_id(cached_marker)


def _build_detail_cache_marker(external_id: str) -> str:
    """
    ساخت مقدار قابل ذخیره در cache برای get_public_content_detail_cached.

    اگر محتوا موجود و قابل نمایش بود، خود external_id را برمی‌گردانیم.
    در غیر این صورت یک sentinel که نمایانگر عدم وجود است.
    """
    content = get_public_content_by_external_id(external_id)
    if content is None:
        return _DETAIL_NOT_FOUND_SENTINEL
    return content.external_id


def get_public_contents_page_cached(
    *,
    page: int,
    page_size: int,
    filters_signature: str = "",
) -> list[dict[str, Any]] | None:
    """
    دریافت یک صفحه از داده serialize شده محتواهای عمومی از cache.

    اگر در cache نبود، None برمی‌گرداند تا view بتواند مسیر معمول را طی کند.

    Args:
        page: شماره صفحه
        page_size: تعداد آیتم در هر صفحه
        filters_signature: امضای فیلترهای اعمال‌شده (برای کلید یکتا)

    Returns:
        لیست داده‌های serialize شده یا None اگر در cache نبود.
    """
    version = get_namespace_version(PUBLIC_LIST_NAMESPACE)
    key = make_cache_key(
        PUBLIC_LIST_NAMESPACE,
        version,
        page,
        page_size,
        filters_signature,
    )

    from django.core.cache import cache

    return cache.get(key)


def set_public_contents_page_cache(
    *,
    page: int,
    page_size: int,
    filters_signature: str,
    payload: dict[str, Any],
) -> None:
    """
    ذخیره یک صفحه serialize شده در cache.

    باید همراه get_public_contents_page_cached استفاده شود.
    """
    version = get_namespace_version(PUBLIC_LIST_NAMESPACE)
    key = make_cache_key(
        PUBLIC_LIST_NAMESPACE,
        version,
        page,
        page_size,
        filters_signature,
    )

    from django.core.cache import cache

    cache.set(key, payload, timeout=PUBLIC_LIST_CACHE_TTL)


# ============================================================
# Admin Selectors
# ============================================================


def get_admin_contents() -> QuerySet[TabyinContent]:
    """
    لیست تمام محتواها برای ادمین (شامل غیرفعال و حذف‌شده).
    """
    return TabyinContent.all_objects.with_attachments().order_by("-source_created_at")


def get_admin_content_by_external_id(
    external_id: str,
) -> TabyinContent | None:
    """
    جزئیات یک محتوا برای ادمین (شامل غیرفعال).
    """
    try:
        return TabyinContent.all_objects.with_attachments().get(external_id=external_id)
    except TabyinContent.DoesNotExist:
        return None

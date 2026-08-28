"""API response caching helpers for public DRF endpoints.

طراحی کلید کش
=============
کلید کش هر endpoint عمومی از سه بخش متغیر ساخته می‌شود: شماره صفحه، اندازهٔ
صفحه و امضای فیلترها. هر سه بخش باید همزمان دو ویژگی داشته باشند:

- **کران‌دار (bounded):** مهاجم نتواند با پارامترهای دلخواه بی‌نهایت کلید
  جدید بسازد. کلید بی‌کران یعنی پر شدن حافظهٔ Redis، بیرون افتادن کلیدهای
  معتبر با LRU، و مهم‌تر از همه cache-bypass: هر درخواست یک miss و یک کوئری
  کامل به دیتابیس.
- **متعارف (canonical):** دو درخواستی که دقیقاً همان پاسخ را می‌گیرند باید
  به یک کلید برسند، وگرنه هر شکل نوشتاری متفاوتِ همان درخواست
  (``page=1`` در برابر ``page=001``) یک miss اضافی است.

قید ایمنی که هرگز نباید نقض شود
--------------------------------
متعارف‌سازی مجاز نیست دو درخواست با پاسخ *متفاوت* را به یک کلید برساند.
هر سه تابع این ماژول با همین قید نوشته شده‌اند:

- شمارهٔ صفحه فقط ``int`` می‌شود و هرگز clamp نمی‌شود. اگر ``page=99999`` را
  به آخرین صفحهٔ معتبر می‌چسباندیم، درخواست خارج از محدوده به‌جای ۴۰۴ دادهٔ
  صفحهٔ دیگری را می‌گرفت.
- اندازهٔ صفحه با همان متد خود paginator محاسبه می‌شود، پس مقدار داخل کلید
  دقیقاً همان مقداری است که واقعاً اعمال می‌شود.
- مقدار فیلترها به‌صورت کامل هش می‌شود و هرگز بریده نمی‌شود، وگرنه دو
  جستجوی متفاوت با پیشوند مشترک به یک کلید می‌رسیدند.
"""

from __future__ import annotations

import hashlib
from collections.abc import Callable
from typing import Any, TypeVar

from django_filters.constants import EMPTY_VALUES
from rest_framework.pagination import PageNumberPagination
from rest_framework.request import Request

from apps.core.cache import cache_get_or_set_swr, get_namespace_version, make_cache_key
from apps.core.cache_policy import get_cache_policy

T = TypeVar("T")

#: امضای حالتی که هیچ فیلتر مؤثری اعمال نشده است.
NO_FILTERS = "no_filters"

#: پیشوند امضای شماره صفحهٔ نامعتبر. چنین صفحه‌ای همیشه در paginator خطای
#: ``NotFound`` می‌دهد، پس عملاً هیچ‌وقت در کش نوشته نمی‌شود؛ صرفاً برای
#: جلوگیری از برخورد با صفحات معتبر مقدارش یکتا نگه داشته می‌شود.
_INVALID_PAGE_PREFIX = "p!"


def _short_digest(raw: str) -> str:
    """Return a short collision-resistant digest for one cache key part."""
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


def canonical_page(
    request: Request,
    *,
    pagination_class: type[PageNumberPagination],
) -> str:
    """Return the canonical page component of a cache key.

    منطق این تابع عمداً آینهٔ دقیق ``PageNumberPagination.get_page_number`` و
    ``django.core.paginator.Paginator.validate_number`` است:

    - پارامتر خالی یا غایب مثل ``page=1`` رفتار می‌کند (DRF از ``or 1``
      استفاده می‌کند).
    - رشته‌های ``last_page_strings`` (پیش‌فرض: ``last``) معنای خاص دارند و
      باید هویت مستقل خود را حفظ کنند، نه اینکه در سطل «نامعتبر» بیفتند.
    - هر شکل نوشتاری دیگری از یک عدد (``001``, ``+1``, ``" 1 "``) به همان
      صفحه می‌رسد، پس باید به یک کلید برسد.
    - ورودی غیرعددی هویت یکتای خودش را می‌گیرد؛ ادغام آن با صفحهٔ معتبر
      باعث می‌شد یک درخواست نامعتبر پاسخ کش‌شدهٔ یک صفحهٔ سالم را بگیرد.
    """
    raw = request.query_params.get("page") or "1"
    if raw in pagination_class.last_page_strings:
        return raw
    try:
        return str(int(raw))
    except (TypeError, ValueError):
        return f"{_INVALID_PAGE_PREFIX}{_short_digest(raw)}"


def canonical_page_size(
    request: Request,
    *,
    pagination_class: type[PageNumberPagination],
) -> str:
    """Return the *effective* page size, as the paginator itself would compute it.

    این مهم‌ترین نقطهٔ کران‌دار کردن کلید است. ``max_page_size`` مقدار را
    clamp می‌کند، پس ``page_size=101`` تا ``page_size=999999`` همگی یک پاسخ
    یکسان تولید می‌کنند. اگر مقدار خام وارد کلید شود، همان یک پاسخ زیر
    بی‌نهایت کلید متفاوت ذخیره می‌شود — یک بردار مستقیم برای پر کردن Redis.

    چون از خود ``get_page_size`` استفاده می‌کنیم، کلید و پاسخ نمی‌توانند از
    هم واگرا شوند، حتی اگر بعداً ``max_page_size`` عوض شود.
    """
    paginator = pagination_class()
    effective = paginator.get_page_size(request)
    if not effective:
        effective = paginator.page_size
    return str(effective)


def _encode_filter_value(value: Any) -> str:
    """Encode one cleaned filter value into a stable string."""
    if isinstance(value, (list, tuple)):
        # ترتیب معنادار است (مثلاً OrderingFilter)، پس مرتب‌سازی نمی‌کنیم.
        return ",".join(_encode_filter_value(item) for item in value)
    if isinstance(value, bool):
        return "1" if value else "0"
    return str(value)


def build_filter_signature(filterset: Any) -> str:
    """Build a bounded signature from the *validated* state of a FilterSet.

    امضا از ``form.cleaned_data`` ساخته می‌شود، نه از ``request.query_params``.
    این تفاوت ظریف ولی تعیین‌کننده است:

    - پارامترهای ناشناخته (``?zzz=1``) اصلاً در ``cleaned_data`` نیستند، پس
      روی کلید اثر نمی‌گذارند. حملهٔ کلاسیکِ «هزار پارامتر بی‌معنی، هزار
      cache miss» به یک hit ساده تبدیل می‌شود.
    - فیلترست نامعتبر در viewها به queryset فیلترنشده fallback می‌کند، پس
      پاسخش *دقیقاً* برابر حالت بدون فیلتر است و باید همان امضا را بگیرد.
      این یک تقریب نیست؛ عین رفتار view است.
    - مقدار خالی (``?city=``) را django-filter نادیده می‌گیرد، پس ما هم
      نادیده می‌گیریم و به امضای «بدون فیلتر» می‌رسیم.
    - مقادیر پس از validation نرمال شده‌اند (``"true"`` و ``"True"`` هر دو
      ``True`` می‌شوند)، پس اشکال نوشتاری مختلف یک فیلتر یک کلید می‌گیرند.

    باقی‌ماندهٔ پذیرفته‌شده: فیلتر متنی آزاد مثل ``search`` ذاتاً دامنهٔ
    نامحدودی از مقادیر معتبر دارد. اینجا هش کامل می‌شود (نه بریده) تا نتایج
    اشتباه سرو نشود؛ کران آن ``hard_ttl`` سیاست کش و throttle مرورگر است.
    """
    if filterset is None or not filterset.is_valid():
        return NO_FILTERS

    cleaned = filterset.form.cleaned_data
    parts = [
        f"{name}={_encode_filter_value(cleaned[name])}"
        for name in sorted(cleaned)
        if cleaned[name] not in EMPTY_VALUES
    ]
    if not parts:
        return NO_FILTERS
    return _short_digest("|".join(parts))


def build_cache_variant(
    request: Request,
    *,
    filterset: Any,
    pagination_class: type[PageNumberPagination],
) -> tuple[str, str, str]:
    """Return the bounded, canonical ``(page, page_size, filters)`` key parts.

    این تابع نقطهٔ ورود مورد انتظار برای viewهاست؛ سه بخش متغیر کلید را با
    هم و سازگار با یکدیگر تولید می‌کند تا یک view نتواند سهواً فقط بخشی از
    متعارف‌سازی را اعمال کند.
    """
    return (
        canonical_page(request, pagination_class=pagination_class),
        canonical_page_size(request, pagination_class=pagination_class),
        build_filter_signature(filterset),
    )


def cached_public_payload(
    *,
    domain: str,
    namespace: str,
    parts: tuple[Any, ...],
    factory: Callable[[], T],
) -> T:
    """Cache one serialized public API payload using the domain SWR policy."""
    policy = get_cache_policy(domain)
    version = get_namespace_version(namespace)
    key = make_cache_key(namespace, version, *parts)
    return cache_get_or_set_swr(
        key=key,
        factory=factory,
        soft_ttl=policy.soft_ttl_seconds,
        hard_ttl=policy.hard_ttl_seconds,
        lock_ttl=policy.lock_ttl_seconds,
    )

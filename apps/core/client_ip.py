"""منبع واحد تعیین «IP کلاینت» در کل پروژه — با نگاه امنیتی fail-closed.

چرا این ماژول وجود دارد (یافتهٔ P1 ممیزی مستقل):
    رفتار پیش‌فرض DRF (``SimpleRateThrottle.get_ident``) وقتی ``NUM_PROXIES``
    تنظیم نشده باشد، مقدار header ورودی ``X-Forwarded-For`` را **بدون هیچ
    راستی‌آزمایی** برمی‌گرداند. در استقرار معمولی (بدون پراکسی واسط یا با
    پراکسی‌ای که header را بازنویسی می‌کند) این یعنی:

    1. مهاجم با عوض‌کردن یک header، سهمیهٔ throttle را دور می‌زند
       (rate-limiting بی‌اثر روی floods از یک IP واقعی)؛
    2. audit trail و لاگ‌های امنیتی (امضای IP، بلاک، الگوهای abuse) با
       IP جعلی آلوده می‌شوند و بازرسی‌های امنیتی گمراه می‌شوند؛
    3. حتی وقتی ``NUM_PROXIES=k`` تنظیم شده باشد، DRF برای زنجیرهٔ کوتاه‌تر از
       k با ``addrs[-min(k, len)]`` به سراغ **چپ‌ترین** (قابل جعل‌ترین)
       مقدار می‌رود — باز هم fail-open.

قرارداد این ماژول (در همهٔ مصرف‌کننده‌ها یکسان است):
    - ``NUM_PROXIES`` پیش‌فرض پروژه **صفر** است → XFF هرگز معتبر نیست؛
    - ``NUM_PROXIES=k`` (k≥1) فقط وقتی معتبر است که زنجیرهٔ XFF حداقل k
      عنصر داشته باشد؛ IP کلاینت = k-امین عنصر از **راست** (پایین‌ترین
      پراکسیِ قابل اعتماد ضمیمه کرده است)؛
    - هر حالت معیوب (فقدان XFF، زنجیرهٔ کوتاه، مقدار خالی) → بازگشت به
      ``REMOTE_ADDR`` که WSGI/AWS ALB آن را از اتصال واقعی پر می‌کند؛
    - ``None`` به معنی «تنظیم نشده» مثل صفر رفتار می‌شود — عمداً متفاوت با
      DRF که در این حالت fail-open است.

مستندات استقرار: تعداد پراکسی‌های واقعاً قابل اعتماد (که XFF را بازنویسی
می‌کنند) را در ``NUM_PROXIES`` env تعیین کنید — نه تعداد hops شبکه.
"""

from __future__ import annotations

from typing import Any

from rest_framework.settings import api_settings


def trusted_proxy_count() -> int:
    """تعداد پراکسی‌های قابل اعتماد (``REST_FRAMEWORK.NUM_PROXIES``).

    - پیش‌فرض پروژه صفر است (در ``config.settings.base`` از env خوانده
      می‌شود)؛
    - ``None``/غیرعددی/منفی → صفر (fail-closed)؛
    - این مقدار فقط از سوی operator استقرار باید بالا برود، وقتی واقعاً
      پراکسی واسطی وجود دارد که خودش XFF را بازنویسی می‌کند.
    """
    value = getattr(api_settings, "NUM_PROXIES", None)
    try:
        count = int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError, AttributeError):
        return 0
    return count if count > 0 else 0


def _strip_port(address: str) -> str:
    """حذف پورت از آدرس XFF (که ممکن است شامل پورت باشد، برخلاف REMOTE_ADDR)."""
    addr = (address or "").strip()
    if not addr:
        return addr
    # IPv6 با براکت: [2001:db8::1]:8443 → 2001:db8::1
    if addr.startswith("["):
        closed = addr.find("]")
        return addr[1:closed] if closed != -1 else addr
    # IPv4:port
    if addr.count(".") == 3 and ":" in addr:
        return addr.rsplit(":", 1)[0]
    return addr


def get_client_ip(request: Any) -> str | None:
    """IP واقعی کلاینت، با احترام به ``NUM_PROXIES``؛ هرگز متکی به XFF جعل‌پذیر.

    Args:
        request: هر شیء دارای ``request.META`` (Django/DRF Request یا stub).

    Returns:
        آدرس IP به‌صورت str یا ``None`` وقتی قابل تعیین نیست (REMOTE_ADDR
        خالی — فقط در محیط‌های غیر معمول؛ در WSGI/ASGI همیشه پر است).
    """
    meta = getattr(request, "META", {})
    remote_addr = meta.get("REMOTE_ADDR")
    num_proxies = trusted_proxy_count()
    if num_proxies == 0:
        return remote_addr

    xff = meta.get("HTTP_X_FORWARDED_FOR")
    if not xff:
        return remote_addr
    addrs = [part.strip() for part in xff.split(",") if part.strip()]
    # زنجیرهٔ کوتاه‌تر از k پراکسی → نمی‌توانیم به آن اعتماد کنیم (fail-closed).
    if len(addrs) < num_proxies:
        return remote_addr
    return _strip_port(addrs[-num_proxies])

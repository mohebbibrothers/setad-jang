"""قفل مبتنی‌بر‌کش برای brute-force روی صفحهٔ لاگین ادمین جانگو (یافتهٔ P1-۳ فاز ۷).

چرا throttleهای DRF اینجا کافی نبودند:
    لاگین ادمین (/admin/login/) یک view معمولی جانگو است و اصلاً وارد
    لولهٔ DRF نمی‌شود؛ یعنی تمام throttleهای پروژه (و حتی کلاس‌های
    non-bypassable خودمان) از کنارش رد می‌شدند و تنها سدِ باقی‌مانده
    `limit_req` لبه‌ای nginx بود که فقط «نرخ» را می‌بیند نه «شکست».

طراحی این گارد:
    - شمارش بر پایهٔ **نتیجهٔ واقعی تلاش** است، نه تعداد درخواست: پس از
      اجرای view، پاسخِ POSTِ `/admin/login/` بررسی می‌شود — `302` یعنی
      موفق (شمارنده صفر)، `200` یعنی فرم با خطا برگشته (شکست). چرا این‌جا
      سیگنال `user_login_failed` منبع نیست؟ چون `AuthenticationForm` جانگو
      عمداً برای نام‌کاربریِ **وجودنداشته** اصلاً `authenticate()` را صدا
      نمی‌زند (جلوی افشای وجود حساب از طریق زمان/سیگنال) — و گاردی که روی
      سیگنال سوار باشد دقیقاً در همان سناریوی username-spray هیچ نمی‌شمارد.
      پاسخ‌محور بودن، هر دو حالت (نام وجود دارد / ندارد) را می‌گیرد و برای
      لاگین‌های API هم بی‌اثر است چون مسیرشان `/admin/login/` نیست.
    - دو محور، تا credential-stuffingِ پخش‌شده روی نام‌های کاربری مختلفِ
      یک IP هم بگیرد:
        * جفت (IP, username) → آستانهٔ سخت (پیش‌فرض ۵)
        * خودِ IP → آستانهٔ نرم (پیش‌فرض ۲۰)
    - عبور از آستانه → قفلِ موقت با `429 + Retry-After` روی *لاگین*؛
      بقیهٔ مسیرهای /admin/ دست‌نخورده‌اند تا ادمینِ دام‌نشده نتواند
      با یک تلاشِ ناجواب کارش را بکند.
    - لاگین موفق هر دو شمارنده را صفر می‌کند.
    - state در `django.core.cache` است: در production روی Redis مشترکِ کل
      workerها (الزام fail-fast شده) و در dev روی locmem — بدون هیچ
      جدول جدید و بدون مهاجرت.
    - username/IP خام در کلید کش ذخیره نمی‌شوند؛ HMAC-شده‌اند، همان
      الگوی apps.core.throttling.
"""

from __future__ import annotations

import logging
import time
from collections.abc import Callable
from typing import Final

from django.core.cache import cache
from django.http import HttpRequest, HttpResponse
from django.utils.crypto import salted_hmac

from apps.core.client_ip import get_client_ip

logger = logging.getLogger("apps.core.admin_guard")

#: تنها مسیری که این گارد روی آن رفتار می‌کند.
ADMIN_LOGIN_PATH: Final[str] = "/admin/login/"

#: فضای‌نام HMAC کلیدهای کش — تغییرش = بازنشستی همهٔ قفل‌ها.
_HMAC_SALT: Final[str] = "apps.core.admin_guard"

#: سقف عمر کلیدهای شمارنده/قفل؛ فقط تور ایمنی است، TTL واقعی از settings
#: خوانده می‌شود و باید کوچک‌تر از این باشد تا رفتار غیرقابل‌پیش‌بینی
#: «قفلِ ابدی» بعد از بد-تنظیمیِ env دیده نشود.
_KEY_CEILING_SECONDS: Final[int] = 24 * 60 * 60

_BLOCK_SUFFIX: Final[str] = ":block"


def _limits() -> tuple[int, int, int]:
    """Return (per_pair_threshold, per_ip_threshold, lockout_seconds) from settings.

    خوانش در زمانِ فراخوانی (نه import) تا override_settings در تست و
    تنظیمِ env در استقرار همان لحظه اثر کند — همان قراردادی که در
    `apps.authentication.otp` تثبیت شده است.
    """
    from django.conf import settings as dj_settings

    pair = int(getattr(dj_settings, "ADMIN_LOGIN_MAX_FAILURES", 5))
    per_ip = int(getattr(dj_settings, "ADMIN_LOGIN_MAX_FAILURES_PER_IP", 20))
    lockout = int(getattr(dj_settings, "ADMIN_LOGIN_LOCKOUT_SECONDS", 900))
    # محافظت در برابر بد-تنظیمی: آستانه‌ها حداقل ۱ و قفل از سقفِ کلید بزرگ‌تر
    # نشود. عمداً هیچ clamp متقابلِ pair↔ip نداریم: سناریوی مشروعِ
    # credential-stuffing یعنی آستانهٔ جفت بالا و آستانهٔ IP پایین.
    pair = max(pair, 1)
    per_ip = max(per_ip, 1)
    lockout = min(lockout, _KEY_CEILING_SECONDS)
    return pair, per_ip, lockout


def _pair_key(ip: str, username: str) -> str:
    """کشِ شمارندهٔ «این IP با این نام کاربری» (مقادیر خام، هیچ‌گاه، ذخیره نمی‌شوند)."""
    digest = salted_hmac(
        _HMAC_SALT,
        f"pair|{ip}|{username.strip().lower()}",
        algorithm="sha256",
    ).hexdigest()[:32]
    return f"admguard:pair:{digest}"


def _ip_key(ip: str) -> str:
    """کشِ شمارندهٔ تجمیعیِ یک IP روی کل نام‌های کاربری."""
    digest = salted_hmac(_HMAC_SALT, f"ip|{ip}", algorithm="sha256").hexdigest()[:32]
    return f"admguard:ip:{digest}"


def _block_key(counter_key: str) -> str:
    """کلید قفلِ متناظر با یک شمارنده."""
    return counter_key + _BLOCK_SUFFIX


def _client_identity(request: HttpRequest) -> tuple[str, str]:
    """Return (ip, username) برای شمارنده‌ها؛ هیچ‌کدام خام در کلید نمی‌نشینند."""
    ip = get_client_ip(request) or "unknown"
    username = str(request.POST.get("username", "")) if request.method == "POST" else ""
    return ip, username


def lockout_seconds_left(request: HttpRequest) -> int:
    """Return remaining block seconds for this request's admin-login identity.

    صفر یعنی آزاد. منبع حقیقت، مقدارِ ذخیره‌شده (timestampِ پایانِ قفل) است
    نه TTL خودِ کش، چون `cache` جانگو API خواندنِ TTL ندارد و timestamp
    مستقل‌تر از اختلاف ساعت است (مقادیر در همان نود نوشته/خوانده می‌شوند).
    """
    ip, username = _client_identity(request)
    keys = [_pair_key(ip, username)] if username else []
    keys.append(_ip_key(ip))
    now = time.time()
    remaining = 0
    for key in keys:
        until = cache.get(key + _BLOCK_SUFFIX)
        if isinstance(until, (int, float)) and until > now:
            remaining = max(remaining, int(until - now))
    return remaining


def record_admin_login_failure(request: HttpRequest) -> None:
    """یک شکستِ لاگین ادمین را ثبت و در صورت عبور از آستانه، قفل می‌کند."""
    pair_threshold, ip_threshold, lockout = _limits()
    ip, username = _client_identity(request)

    for key, threshold in ((_pair_key(ip, username), pair_threshold), (_ip_key(ip), ip_threshold)):
        window_ttl = max(lockout, 60)
        try:
            failures = cache.incr(key)
        except ValueError:
            cache.set(key, 1, timeout=window_ttl)
            failures = 1
        if failures >= threshold:
            cache.set(
                key + _BLOCK_SUFFIX,
                time.time() + lockout,
                timeout=window_ttl + 60,
            )
            logger.warning(
                "Admin login lockout engaged key=%s failures=%s window=%ss lockout=%ss",
                key,
                failures,
                window_ttl,
                lockout,
            )


def reset_admin_login_counters(request: HttpRequest) -> None:
    """شمارنده‌های این هویت را پاک می‌کند (ورودِ موفق).

    نام‌کاربری از خودِ POST خوانده می‌شود (کلیدها نرمال‌اند: case-insensitive و
    trim) و شمارندهٔ IP همیشه پاک می‌شود تا ادمینی که وارد شده، از قفلِ تجمیعی
    هم خارج شود.
    """
    ip, post_username = _client_identity(request)
    names = {post_username} if post_username else set()
    keys = [_pair_key(ip, name) for name in names] + [_ip_key(ip)]
    for key in keys:
        cache.delete(key)
        # قفل‌ها هم پاک شوند تا ورود موفق، فوراً از قفل خارج کند.
        cache.delete(key + _BLOCK_SUFFIX)


class AdminLoginGuardMiddleware:
    """قفل/شمارشِ نتیجه‌محور برای POST /admin/login/ — پیش و پس از view.

    الگو: «تصمیم پیش از view، ثبت پس از view». یعنی اگر قفل فعال باشد،
    درخواست اصلاً به view نمی‌رسد (هزینهٔ hash/DB هم نمی‌پردازیم) و ثبت
    شکست/موفقیت از وضعیتِ پاسخ انجام می‌شود — همان چیزی که در داکستریِ ماژول
    به‌عنوان دلیلِ کنارگذاشتن سیگنال توضیح داده شد.
    """

    def __init__(self, get_response: Callable[[HttpRequest], HttpResponse]) -> None:
        self._get_response = get_response

    def __call__(self, request: HttpRequest) -> HttpResponse:
        is_admin_login = request.method == "POST" and request.path == ADMIN_LOGIN_PATH
        if is_admin_login:
            seconds_left = lockout_seconds_left(request)
            if seconds_left > 0:
                return self._blocked_response(seconds_left)

        response = self._get_response(request)

        if is_admin_login:
            # 302 → ورود موفق (LoginView در حالت موفق حتماً redirect می‌کند)؛
            # 200 → فرم با خطای اعتبارسنجی؛ بقیه (مثلاً 403 در CSRF) شمرده
            # نمی‌شوند تا یک بدفرمت‌سازیِ ساده، قفلِ کل IP نسازد.
            if response.status_code == 302:
                reset_admin_login_counters(request)
            elif response.status_code == 200:
                record_admin_login_failure(request)
        return response

    @staticmethod
    def _blocked_response(seconds_left: int) -> HttpResponse:
        """پاسخ ۴۲۹ حداقلی — بدون افشای اینکه کدام آستانه (زوج/IP) فعال شده."""
        response = HttpResponse(
            "<h1>429 — Too Many Requests</h1>"
            "<p>تلاش‌های نامعتبر ورود بیش از حد مجاز بوده است. "
            "لطفاً پس از مدتی دوباره تلاش کنید.</p>",
            status=429,
            content_type="text/html; charset=utf-8",
        )
        response["Retry-After"] = str(seconds_left)
        return response

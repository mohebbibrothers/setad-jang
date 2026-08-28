"""
Anti-abuse helpers — defense layers beyond DRF throttling.

این ماژول شامل دو helper مستقل است:

1. Honeypot detection:
   - یک field invisible به نام HONEYPOT_FIELD_NAME در request body.
   - کاربر واقعی هرگز این field را پر نمی‌کند (در UI hidden است).
   - bots معمولاً همه‌ی fieldها را پر می‌کنند.
   - اگر این field مقدار non-empty داشته باشد یا نوع آن غیررشته‌ای باشد،
     request suspicious در نظر گرفته می‌شود.

2. Global anomaly guard:
   - یک counter Redis-backed که request های OTP کل سیستم در یک پنجره
     زمانی را می‌شمارد.
   - اگر از یک threshold عبور کرد، یک time window OTP-issuance را پاز
     می‌کند (همه‌ی identifierها، همه‌ی IPها).
   - fail-open: اگر Redis قطع باشد، عبور می‌دهد و WARNING log می‌زند.

اصول طراحی:
- هر دو helper pure و stateless هستند (state فقط در Redis cache).
- threshold و window از env قابل override هستند.
- error messages برای attacker uninformative ولی برای logging کاملاً صریح.
"""

from __future__ import annotations

import logging
from typing import Any

from django.conf import settings
from django.core.cache import cache

logger = logging.getLogger("apps.authentication")


# ============================================================
# Honeypot
# ============================================================

#: نام field invisible برای honeypot.
#: bots معمولاً همه‌ی fieldها را پر می‌کنند، پس مقدار meaningful در این field
#: یا value غیررشته‌ای می‌تواند نشانه‌ی bot باشد.
HONEYPOT_FIELD_NAME = "website"


def is_honeypot_triggered(data: dict[str, Any] | None) -> bool:
    """
    تشخیص اینکه honeypot triggered شده یا نه.

    Args:
        data: payload request (معمولاً request.data).

    Returns:
        True اگر honeypot field مقدار suspicious داشته باشد
        (string غیرخالی یا value غیررشته‌ای).
    """
    if not isinstance(data, dict):
        return False

    value = data.get(HONEYPOT_FIELD_NAME)
    if value is None:
        return False

    # اگر مقدار string غیرخالی داشت → bot
    if isinstance(value, str) and value.strip():
        return True

    # اگر string نبود، باز هم suspicious است.
    return not isinstance(value, str)


# ============================================================
# Global anomaly guard
# ============================================================

# پیکربندی گارد سراسری.
#
# قبلاً این دو مقدار مستقیماً و *در زمان import ماژول* از env خوانده می‌شدند.
# سه پیامد داشت:
#
#   ۱. `AUTH_OTP_GLOBAL_THRESHOLD` که در production.py به‌عنوان Django setting
#      تعریف شده بود، عملاً هرگز خوانده نمی‌شد — یک dead config تمام‌عیار.
#   ۲. پیش‌فرض‌ها ناسازگار بودند: ۵۰۰ در production.py و ۱۰۰۰ اینجا. آنچه
#      واقعاً اعمال می‌شد ۱۰۰۰ بود، یعنی گارد دو برابر شل‌تر از چیزی که
#      اپراتور فکر می‌کرد پیکربندی کرده است.
#   ۳. خواندن در زمان import یعنی نه `override_settings` در تست کار می‌کرد و
#      نه تغییر مقدار در runtime.
#
# حالا تنها مرجع، Django settings است و مقدار در زمان فراخوانی خوانده می‌شود.
_GLOBAL_OTP_GUARD_DEFAULTS = {
    "AUTH_OTP_GLOBAL_THRESHOLD": 500,
    "AUTH_OTP_GLOBAL_WINDOW_SECONDS": 60,
}


def _guard_setting(name: str) -> int:
    """Read a global-guard tunable from settings at call time."""
    return int(getattr(settings, name, _GLOBAL_OTP_GUARD_DEFAULTS[name]))


# نام کلید cache برای global counter
_GLOBAL_OTP_GUARD_CACHE_KEY = "auth:otp:global_counter"


def is_global_otp_guard_tripped() -> bool:
    """
    بررسی اینکه global OTP guard tripped شده یا نه.

    این تابع همزمان counter را افزایش می‌دهد. اگر counter از threshold
    عبور کرد، True برمی‌گرداند (یعنی OTP-issuance باید پاز شود).

    Fail-open: اگر Redis قطع باشد، False برمی‌گرداند (یعنی عبور می‌دهد)
    ولی WARNING log می‌زند.
    """
    threshold = _guard_setting("AUTH_OTP_GLOBAL_THRESHOLD")
    window_seconds = _guard_setting("AUTH_OTP_GLOBAL_WINDOW_SECONDS")

    try:
        # incr atomic در Django cache backend (Redis یا LocMem)
        # اگر کلید وجود نداشت، اول 1 ست می‌کنیم با ttl پنجره.
        counter = cache.get(_GLOBAL_OTP_GUARD_CACHE_KEY)
        if counter is None:
            # ست اولیه با ttl
            cache.set(
                _GLOBAL_OTP_GUARD_CACHE_KEY,
                1,
                timeout=window_seconds,
            )
            counter = 1
        else:
            try:
                counter = cache.incr(_GLOBAL_OTP_GUARD_CACHE_KEY)
            except ValueError:
                # کلید بین get و incr expire شده — set دوباره با ttl
                cache.set(
                    _GLOBAL_OTP_GUARD_CACHE_KEY,
                    1,
                    timeout=window_seconds,
                )
                counter = 1

        if counter > threshold:
            logger.warning(
                "Global OTP guard TRIPPED at counter=%d threshold=%d window=%ds",
                counter,
                threshold,
                window_seconds,
            )
            return True

        return False

    except Exception as exc:
        # fail-open: اگر cache backend قطع بود، عبور می‌دهیم ولی log می‌زنیم.
        logger.warning(
            "Global OTP guard check failed (fail-open): %s",
            exc,
        )
        return False


def reset_global_otp_guard() -> None:
    """
    Reset کردن global counter — فقط برای تست‌ها استفاده می‌شود.
    """
    cache.delete(_GLOBAL_OTP_GUARD_CACHE_KEY)

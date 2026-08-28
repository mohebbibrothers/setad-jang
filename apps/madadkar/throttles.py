"""
Throttle classes اپ مددکار.

این throttleها روی scope ratesی که در config/settings/base.py تعریف شده‌اند
سوار می‌شوند:
- madadkar_browse_anon: 60/min — لیست/جزئیات عمومی برای anonymous
- madadkar_browse_user: 120/min — لیست/جزئیات عمومی برای لاگین‌شده
- madadkar_participate: 10/min — شروع مشارکت (anti-abuse مهم)
- madadkar_payment_verify: 30/min — callback verify

نکته: throttleهای مخصوص ادمین تعریف نمی‌شوند — ادمین در سطح permission
محدود است و throttle پیش‌فرض user کافی است.
"""

from __future__ import annotations

from rest_framework.throttling import AnonRateThrottle, UserRateThrottle

from apps.core.throttling import ClientIPRateThrottle


class MadadkarBrowseAnonThrottle(AnonRateThrottle):
    """Throttle برای کاربران ناشناس در endpointهای عمومی browse."""

    scope = "madadkar_browse_anon"


class MadadkarBrowseUserThrottle(UserRateThrottle):
    """Throttle برای کاربران لاگین‌شده در endpointهای عمومی browse."""

    scope = "madadkar_browse_user"


class MadadkarParticipateThrottle(UserRateThrottle):
    """
    Throttle برای شروع مشارکت (POST participate).

    این throttle برای جلوگیری از سوءاستفاده مالی critical است:
    - جلوگیری از script-based reservation کردن سهم‌ها
    - جلوگیری از حملات DOS روی درگاه پرداخت
    """

    scope = "madadkar_participate"


class MadadkarPaymentVerifyThrottle(ClientIPRateThrottle):
    """
    Throttle برای endpoint callback verify درگاه پرداخت.

    نکته: کلید همیشه روی IP ساخته می‌شود چون callback از طرف درگاه
    می‌آید و ممکن است session احراز هویت کاربر در آن لحظه active نباشد.

    چرا ClientIPRateThrottle و نه AnonRateThrottle:
        AnonRateThrottle برای کاربر لاگین‌کرده کلید None برمی‌گرداند و
        throttle کاملاً skip می‌شود. چون کاربر پس از پرداخت با session
        فعال به callback برمی‌گردد، آن مسیر عملاً بدون محدودیت بود.
    """

    scope = "madadkar_payment_verify"


class MadadkarReceiptVerifyThrottle(ClientIPRateThrottle):
    """
    Throttle اختصاصی راستی‌آزمایی عمومی رسید (یافتهٔ ممیزی ۵.۱).

    «آیا این شمارهٔ رسید معتبر است؟» الگوی کلاسیک اوراکل شمارش است؛ با
    پیش‌فرض `anon: 60/min`، مهاجم با چرخش IP می‌توانست شمارهٔ رسیدها را
    brute-force کند. این throttle همیشه روی IP است (مستقل از احراز هویت،
    چون endpoint عمومی است) و سقفش عمداً سخت‌گیرانه‌تر از browse است.
    """

    scope = "madadkar_receipt_verify"

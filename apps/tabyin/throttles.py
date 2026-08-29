"""Throttle classes برای اپ تبیین."""

from rest_framework.throttling import AnonRateThrottle, UserRateThrottle


class TabyinPublicAnonThrottle(AnonRateThrottle):
    """نرخ محدودیت برای کاربران ناشناس — محتوای عمومی."""

    rate = "60/min"


class TabyinPublicUserThrottle(UserRateThrottle):
    """نرخ محدودیت برای کاربران لاگین — محتوای عمومی."""

    rate = "120/min"


class TabyinSyncThrottle(UserRateThrottle):
    """نرخ محدودیت برای اجرای sync — فقط ادمین."""

    scope = "tabyin_sync"
    rate = "5/hour"


class TabyinUploadThrottle(UserRateThrottle):
    """نرخ آپلود مستقیم رسانه برای روایت‌ها — سدِ سوءاستفاده‌ی حجیم."""

    rate = "15/min"

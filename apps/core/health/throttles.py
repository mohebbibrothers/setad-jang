"""
Throttleهای اختصاصی endpointهای Health.

چرا برای `/health/detailed/` throttle جدا لازم است (آپکس ممیزی ۴.۱):
    این endpoint ۹ چک سنگین اجرا می‌کند (کوئری DB، عملیات cache، بررسی
    migration state، بررسی storage) و قبلاً `throttle_classes = []` داشت —
    یعنی عملاً بدون هیچ محدودیتی. یک مهاجم منفرد می‌توانست با چند IP آن را
    بکوبد و دیتابیس را بارگذاری کند. نکتهٔ ظریف: خاموش‌کردن throttle برای
    `/health/` و `/health/ready/` عمداً درست است (probeهای orchestrator
    نباید محدود شوند)، ولی برای endpoint تفصیلی که برای داشبورد است نه.

    این throttle فقط برای درخواست‌های بدون احراز هویت اعمال می‌شود: یک
    داشبورد monitoring که با توکن کاربر (staff) polling می‌کند به سهمیهٔ
    پیش‌فرض user (۱۲۰/min) محدود است و بدون دلیل اضافه throttle نمی‌شود.
"""

from __future__ import annotations

from typing import Any

from apps.core.throttling import NonBypassableRateThrottle


class HealthDetailedAnonThrottle(NonBypassableRateThrottle):
    """
    محدودیت سخت‌گیرانهٔ per-IP فقط برای درخواست‌های anonymous.

    از `NonBypassableRateThrottle` ارث می‌برد تا برخلاف `AnonRateThrottle`
    در هیچ حالتی حفرهٔ bypass نداشته باشد؛ ولی برای کاربر احراز هویت‌شده
    عمداً bucket خالی برمی‌گرداند تا throttle کنار برود (سهمیهٔ پیش‌فرض
    user آن‌ها را پوشش می‌دهد و داشبوردها polling مکرر دارند).
    """

    scope = "health_detailed_anon"
    bucket_prefix = "hd"

    def get_bucket_ident(self, request: Any, view: Any) -> str:
        """برای anonymous → IP؛ برای احراز هویت‌شده → خالی (تشخیص‌پذیر)."""
        user = getattr(request, "user", None)
        if user is not None and getattr(user, "is_authenticated", False):
            return ""
        return str(self.get_ident(request))

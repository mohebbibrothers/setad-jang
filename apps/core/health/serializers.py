"""
Serializers برای Health Check endpoints.

این serializerها فقط برای تولید Swagger schema استفاده می‌شوند —
داده واقعی از توابع check در checks.py می‌آید.
"""

from rest_framework import serializers

# ─── Simple Health (Liveness Probe) ─────────────────────────


class SimpleHealthSerializer(serializers.Serializer):
    """پاسخ ساده health check — مناسب load balancers."""

    status = serializers.ChoiceField(
        choices=["ok", "error", "degraded"],
        help_text="وضعیت کلی سرویس",
    )
    timestamp = serializers.DateTimeField(
        help_text="زمان انجام چک",
    )


# ─── Detailed Component Checks ──────────────────────────────


class ComponentCheckSerializer(serializers.Serializer):
    """نتیجه چک یک کامپوننت (DB, Cache, ...)."""

    status = serializers.ChoiceField(
        choices=["ok", "error", "degraded"],
        help_text="وضعیت این کامپوننت",
    )
    latency_ms = serializers.FloatField(
        required=False,
        help_text="زمان پاسخ به میلی‌ثانیه",
    )
    backend = serializers.CharField(
        required=False,
        help_text="نوع backend (مثلاً locmem, redis)",
    )
    detail = serializers.CharField(
        required=False,
        help_text="جزئیات خطا (در صورت بروز)",
    )


class TabyinSyncCheckSerializer(serializers.Serializer):
    """نتیجه چک وضعیت sync تبیین."""

    status = serializers.ChoiceField(choices=["ok", "error"])
    total_contents = serializers.IntegerField(
        required=False,
        help_text="تعداد کل محتواها در دیتابیس",
    )
    active_contents = serializers.IntegerField(
        required=False,
        help_text="تعداد محتواهای فعال (قابل نمایش)",
    )
    deleted_in_source = serializers.IntegerField(
        required=False,
        help_text="تعداد محتواهای حذف‌شده در منبع",
    )
    last_synced_at = serializers.DateTimeField(
        required=False,
        allow_null=True,
        help_text="زمان آخرین همگام‌سازی موفق",
    )
    seconds_since_last_sync = serializers.IntegerField(
        required=False,
        allow_null=True,
        help_text="تعداد ثانیه‌های گذشته از آخرین همگام‌سازی",
    )
    detail = serializers.CharField(
        required=False,
        help_text="جزئیات خطا (در صورت بروز)",
    )


# ─── System Info ────────────────────────────────────────────


class SystemInfoSerializer(serializers.Serializer):
    """اطلاعات سیستمی پروژه."""

    project_name = serializers.CharField(help_text="نام پروژه")
    project_version = serializers.CharField(help_text="نسخه پروژه")
    django_version = serializers.CharField(help_text="نسخه Django")
    python_version = serializers.CharField(help_text="نسخه Python")
    debug = serializers.BooleanField(help_text="آیا حالت debug فعال است؟")
    environment = serializers.CharField(help_text="محیط اجرا (dev / staging / prod)")
    uptime_seconds = serializers.IntegerField(
        help_text="چند ثانیه از start سرور گذشته",
    )


# ─── Detailed Health Response ───────────────────────────────


class DetailedHealthSerializer(serializers.Serializer):
    """پاسخ کامل health check شامل تمام چک‌ها و اطلاعات سیستم."""

    status = serializers.ChoiceField(
        choices=["ok", "error", "degraded"],
        help_text="وضعیت کلی سرویس (جمع‌بندی همه چک‌ها)",
    )
    timestamp = serializers.DateTimeField(
        help_text="زمان انجام چک",
    )
    checks = serializers.DictField(
        help_text="نتیجه چک هر کامپوننت",
    )
    system = SystemInfoSerializer(
        help_text="اطلاعات سیستمی پروژه",
    )

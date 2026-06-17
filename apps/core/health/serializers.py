"""
Serializers برای Health Check endpoints.

این serializerها برای تولید Swagger schema استفاده می‌شوند. داده واقعی از
checks.py و views.py ساخته می‌شود و با همین قرارداد باید هم‌خوان بماند.
"""

from __future__ import annotations

from rest_framework import serializers

HEALTH_STATUS_CHOICES = ["ok", "error", "degraded"]


# ─── Simple Health (Liveness Probe) ─────────────────────────


class SimpleHealthSerializer(serializers.Serializer):
    """پاسخ ساده health check — مناسب liveness probes."""

    status = serializers.ChoiceField(
        choices=HEALTH_STATUS_CHOICES,
        help_text="وضعیت کلی سرویس",
    )
    timestamp = serializers.DateTimeField(help_text="زمان انجام چک")


# ─── Component Checks ───────────────────────────────────────


class ComponentCheckSerializer(serializers.Serializer):
    """نتیجه چک یک کامپوننت operational."""

    status = serializers.ChoiceField(
        choices=HEALTH_STATUS_CHOICES,
        help_text="وضعیت این کامپوننت",
    )
    latency_ms = serializers.FloatField(
        required=False,
        help_text="زمان پاسخ به میلی‌ثانیه",
    )
    backend = serializers.CharField(
        required=False,
        help_text="نوع backend یا label امن dependency",
    )
    detail = serializers.CharField(
        required=False,
        help_text="جزئیات امن خطا یا degraded state",
    )


class TabyinSyncCheckSerializer(serializers.Serializer):
    """نتیجه چک وضعیت sync تبیین."""

    status = serializers.ChoiceField(choices=HEALTH_STATUS_CHOICES)
    total_contents = serializers.IntegerField(required=False)
    active_contents = serializers.IntegerField(required=False)
    deleted_in_source = serializers.IntegerField(required=False)
    last_synced_at = serializers.DateTimeField(required=False, allow_null=True)
    seconds_since_last_sync = serializers.IntegerField(required=False, allow_null=True)
    detail = serializers.CharField(required=False)


class ReadinessChecksSerializer(serializers.Serializer):
    """چک‌های critical readiness برای سرو کردن traffic."""

    database = ComponentCheckSerializer()
    cache = ComponentCheckSerializer()
    celery_broker = ComponentCheckSerializer()


class DetailedChecksSerializer(ReadinessChecksSerializer):
    """چک‌های detailed شامل readiness و diagnosticهای non-critical."""

    migration_state = ComponentCheckSerializer()
    media_storage = ComponentCheckSerializer()
    audit_chain_quick = ComponentCheckSerializer()
    performance_contracts = serializers.JSONField()
    tabyin_sync = TabyinSyncCheckSerializer()


# ─── System Info ────────────────────────────────────────────


class SystemInfoSerializer(serializers.Serializer):
    """اطلاعات سیستمی پروژه."""

    project_name = serializers.CharField(help_text="نام پروژه")
    project_version = serializers.CharField(help_text="نسخه پروژه")
    django_version = serializers.CharField(help_text="نسخه Django")
    python_version = serializers.CharField(help_text="نسخه Python")
    debug = serializers.BooleanField(help_text="آیا حالت debug فعال است؟")
    environment = serializers.CharField(help_text="محیط اجرا")
    uptime_seconds = serializers.IntegerField(help_text="چند ثانیه از start سرور گذشته")


# ─── Response Serializers ───────────────────────────────────


class ReadinessHealthSerializer(serializers.Serializer):
    """پاسخ readiness شامل dependencyهای critical."""

    status = serializers.ChoiceField(choices=HEALTH_STATUS_CHOICES)
    timestamp = serializers.DateTimeField()
    checks = ReadinessChecksSerializer()


class DetailedHealthSerializer(serializers.Serializer):
    """پاسخ کامل health check شامل تمام چک‌ها و اطلاعات سیستم."""

    status = serializers.ChoiceField(choices=HEALTH_STATUS_CHOICES)
    timestamp = serializers.DateTimeField()
    checks = DetailedChecksSerializer()
    system = SystemInfoSerializer()

"""
Health Check Functions — توابع چک کردن وضعیت اجزای سیستم.

هر تابع check یک dict استاندارد برمی‌گرداند:
{
    "status": "ok" | "error",
    "latency_ms": float,
    "detail": str,  # اختیاری در صورت خطا
}

این ماژول مستقل از view است تا قابلیت reuse در management commands،
celery tasks، یا monitoring scripts را داشته باشد.
"""

import logging
import time
from typing import Any

from django.core.cache import cache
from django.db import connections
from django.db.utils import OperationalError

logger = logging.getLogger("apps.core")


# ─── Status Constants ───────────────────────────────────────

STATUS_OK = "ok"
STATUS_ERROR = "error"
STATUS_DEGRADED = "degraded"  # وقتی سرویس کار می‌کند ولی کند است


# ─── Database Check ─────────────────────────────────────────


def check_database(database_alias: str = "default") -> dict[str, Any]:
    """
    چک سلامت اتصال دیتابیس.

    یک کوئری ساده `SELECT 1` می‌زند و زمان آن را اندازه می‌گیرد.

    Args:
        database_alias: نام دیتابیس در DATABASES (پیش‌فرض: "default")

    Returns:
        dict با کلیدهای: status, latency_ms, detail (در صورت خطا)
    """
    start = time.monotonic()
    try:
        connection = connections[database_alias]
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
            cursor.fetchone()
        latency_ms = round((time.monotonic() - start) * 1000, 2)
        return {
            "status": STATUS_OK,
            "latency_ms": latency_ms,
        }
    except OperationalError as exc:
        logger.exception("Database health check failed")
        return {
            "status": STATUS_ERROR,
            "latency_ms": round((time.monotonic() - start) * 1000, 2),
            "detail": f"OperationalError: {exc}",
        }
    except Exception as exc:
        logger.exception("Unexpected error in database health check")
        return {
            "status": STATUS_ERROR,
            "latency_ms": round((time.monotonic() - start) * 1000, 2),
            "detail": f"{type(exc).__name__}: {exc}",
        }


# ─── Cache Check ────────────────────────────────────────────


def check_cache() -> dict[str, Any]:
    """
    چک سلامت سیستم cache.

    یک مقدار تستی set/get/delete می‌کند، زمان آن را اندازه می‌گیرد،
    و نوع backend فعلی را گزارش می‌کند.

    Returns:
        dict با کلیدهای: status, latency_ms, backend, detail (در صورت خطا)
    """
    test_key = "_health_check_probe"
    test_value = "ping"

    # تشخیص نوع backend از روی کلاس
    backend_name = _detect_cache_backend()

    start = time.monotonic()
    try:
        cache.set(test_key, test_value, timeout=10)
        retrieved = cache.get(test_key)
        cache.delete(test_key)

        latency_ms = round((time.monotonic() - start) * 1000, 2)

        if retrieved != test_value:
            return {
                "status": STATUS_ERROR,
                "backend": backend_name,
                "latency_ms": latency_ms,
                "detail": "Cache returned unexpected value",
            }

        return {
            "status": STATUS_OK,
            "backend": backend_name,
            "latency_ms": latency_ms,
        }
    except Exception as exc:
        logger.exception("Cache health check failed")
        return {
            "status": STATUS_ERROR,
            "backend": backend_name,
            "latency_ms": round((time.monotonic() - start) * 1000, 2),
            "detail": f"{type(exc).__name__}: {exc}",
        }


def _detect_cache_backend() -> str:
    """
    تشخیص نوع backend cache فعلی از روی کلاس آن.

    در Django 6.x، `cache` یک ConnectionProxy است، پس باید از
    `caches['default']` برای دسترسی به backend واقعی استفاده کنیم.

    Returns:
        نام backend به صورت قابل خواندن:
        'locmem', 'redis', 'memcached', 'filebased', 'dummy', یا 'unknown'
    """
    try:
        from django.core.cache import caches

        # دسترسی به backend واقعی (نه ConnectionProxy)
        real_backend = caches["default"]
        backend_module = real_backend.__class__.__module__.lower()
        backend_class = real_backend.__class__.__name__.lower()

        # تشخیص بر اساس module path
        if "locmem" in backend_module:
            return "locmem"
        if "redis" in backend_module or "redis" in backend_class:
            return "redis"
        if "memcached" in backend_module:
            return "memcached"
        if "filebased" in backend_module:
            return "filebased"
        if "dummy" in backend_module:
            return "dummy"
        if "database" in backend_module or "db" in backend_module:
            return "database"

        return "unknown"
    except Exception:
        logger.exception("Failed to detect cache backend")
        return "unknown"


# ─── Tabyin Sync Stats ──────────────────────────────────────


def check_tabyin_sync() -> dict[str, Any]:
    """
    گزارش وضعیت آخرین همگام‌سازی محتوای تبیین.

    این چک خطایی برنمی‌گرداند مگر در حالت عدم دسترسی به DB —
    فقط اطلاعاتی است و در همه حالت `status=ok` برمی‌گرداند.

    Returns:
        dict با اطلاعات آماری sync.
    """
    try:
        # Lazy import برای جلوگیری از circular import
        from django.utils import timezone

        from apps.tabyin.models import TabyinContent

        total = TabyinContent.all_objects.count()
        active = TabyinContent.objects.count()
        deleted_in_source = TabyinContent.all_objects.filter(
            is_deleted_in_source=True,
        ).count()

        last_synced = (
            TabyinContent.all_objects.exclude(last_synced_at__isnull=True)
            .order_by("-last_synced_at")
            .values_list("last_synced_at", flat=True)
            .first()
        )

        seconds_since_last_sync: int | None = None
        if last_synced:
            seconds_since_last_sync = int((timezone.now() - last_synced).total_seconds())

        return {
            "status": STATUS_OK,
            "total_contents": total,
            "active_contents": active,
            "deleted_in_source": deleted_in_source,
            "last_synced_at": (last_synced.isoformat() if last_synced else None),
            "seconds_since_last_sync": seconds_since_last_sync,
        }
    except Exception as exc:
        logger.exception("Tabyin sync health check failed")
        return {
            "status": STATUS_ERROR,
            "detail": f"{type(exc).__name__}: {exc}",
        }


# ─── Aggregate Result ───────────────────────────────────────


def aggregate_status(checks: dict[str, dict[str, Any]]) -> str:
    """
    جمع‌بندی وضعیت کلی بر اساس وضعیت هر چک.

    قانون:
    - اگر یکی از checkها error باشد → کل سیستم error
    - اگر یکی degraded باشد و بقیه ok → کل سیستم degraded
    - در غیر این صورت → ok
    """
    statuses = {check.get("status", STATUS_ERROR) for check in checks.values()}

    if STATUS_ERROR in statuses:
        return STATUS_ERROR
    if STATUS_DEGRADED in statuses:
        return STATUS_DEGRADED
    return STATUS_OK

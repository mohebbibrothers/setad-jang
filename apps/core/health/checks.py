"""
Health Check Functions — reusable operational diagnostics.

هر check یک dict استاندارد و JSON-safe برمی‌گرداند:
{
    "status": "ok" | "degraded" | "error",
    "latency_ms": float,
    "detail": str,      # فقط پیام safe و non-secret
    "backend": str,     # در صورت معنی‌دار بودن
}

طراحی این ماژول برای production observability است:
- liveness نباید dependency خارجی را چک کند.
- readiness باید dependencyهای critical را چک کند.
- detailed health علاوه بر dependencyها، diagnosticهای non-critical مثل Tabyin sync
  را هم گزارش می‌کند.
- هیچ URL کامل، credential، token یا exception raw نباید در خروجی health leak شود.
"""

from __future__ import annotations

import logging
import socket
import time
from typing import Any
from urllib.parse import urlparse

import redis
from django.conf import settings
from django.core.cache import cache
from django.db import connections

logger = logging.getLogger("apps.core.health")

# ─── Status Constants ───────────────────────────────────────

STATUS_OK = "ok"
STATUS_ERROR = "error"
STATUS_DEGRADED = "degraded"

DATABASE_DEGRADED_AFTER_MS = 250.0
CACHE_DEGRADED_AFTER_MS = 100.0
BROKER_DEGRADED_AFTER_MS = 250.0


# ─── Generic helpers ────────────────────────────────────────


def _latency_ms_since(start: float) -> float:
    """Return elapsed monotonic time in milliseconds."""
    return round((time.monotonic() - start) * 1000, 2)


def _status_for_latency(latency_ms: float, *, degraded_after_ms: float) -> str:
    """Map latency to ok/degraded according to component threshold."""
    return STATUS_DEGRADED if latency_ms > degraded_after_ms else STATUS_OK


def _safe_error_detail(exc: Exception) -> str:
    """Return a safe, non-secret error detail for health responses."""
    return type(exc).__name__


def _safe_url_label(url: str) -> str:
    """Return a credential-free label for service URLs."""
    parsed = urlparse(url)
    if not parsed.scheme:
        return "unknown"
    if parsed.hostname:
        port = f":{parsed.port}" if parsed.port else ""
        return f"{parsed.scheme}://{parsed.hostname}{port}"
    return parsed.scheme


# ─── Liveness ───────────────────────────────────────────────


def check_liveness() -> dict[str, Any]:
    """
    Lightweight process liveness check.

    این check هیچ dependency خارجی را لمس نمی‌کند و فقط برای پاسخ سریع به
    orchestrator/load balancer استفاده می‌شود.
    """
    return {"status": STATUS_OK}


# ─── Database Check ─────────────────────────────────────────


def check_database(database_alias: str = "default") -> dict[str, Any]:
    """
    چک سلامت اتصال دیتابیس با یک `SELECT 1` ساده.

    Returns:
        dict شامل status, latency_ms و در صورت degraded/error یک detail امن.
    """
    start = time.monotonic()
    try:
        connection = connections[database_alias]
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
            cursor.fetchone()
        latency_ms = _latency_ms_since(start)
        component_status = _status_for_latency(
            latency_ms,
            degraded_after_ms=DATABASE_DEGRADED_AFTER_MS,
        )
        result: dict[str, Any] = {
            "status": component_status,
            "latency_ms": latency_ms,
            "backend": connection.vendor,
        }
        if component_status == STATUS_DEGRADED:
            result["detail"] = "Database latency is above threshold."
            logger.warning("Database health degraded latency_ms=%s", latency_ms)
        return result
    except Exception as exc:
        latency_ms = _latency_ms_since(start)
        logger.exception(
            "Database health check failed alias=%s latency_ms=%s error_type=%s",
            database_alias,
            latency_ms,
            type(exc).__name__,
        )
        return {
            "status": STATUS_ERROR,
            "latency_ms": latency_ms,
            "backend": database_alias,
            "detail": _safe_error_detail(exc),
        }


# ─── Cache Check ────────────────────────────────────────────


def check_cache() -> dict[str, Any]:
    """
    چک سلامت cache با set/get/delete کوتاه.

    اگر cache مقدار اشتباه برگرداند یا exception بدهد، component error می‌شود.
    latency بالا degraded محسوب می‌شود اما readiness را الزاماً fail نمی‌کند.
    """
    test_key = "_health_check_probe"
    test_value = "ping"
    backend_name = _detect_cache_backend()
    start = time.monotonic()
    try:
        cache.set(test_key, test_value, timeout=10)
        retrieved = cache.get(test_key)
        cache.delete(test_key)
        latency_ms = _latency_ms_since(start)

        if retrieved != test_value:
            logger.error("Cache health check returned unexpected value backend=%s", backend_name)
            return {
                "status": STATUS_ERROR,
                "backend": backend_name,
                "latency_ms": latency_ms,
                "detail": "Cache returned unexpected value.",
            }

        component_status = _status_for_latency(
            latency_ms,
            degraded_after_ms=CACHE_DEGRADED_AFTER_MS,
        )
        result: dict[str, Any] = {
            "status": component_status,
            "backend": backend_name,
            "latency_ms": latency_ms,
        }
        if component_status == STATUS_DEGRADED:
            result["detail"] = "Cache latency is above threshold."
            logger.warning("Cache health degraded backend=%s latency_ms=%s", backend_name, latency_ms)
        return result
    except Exception as exc:
        latency_ms = _latency_ms_since(start)
        logger.exception(
            "Cache health check failed backend=%s latency_ms=%s error_type=%s",
            backend_name,
            latency_ms,
            type(exc).__name__,
        )
        return {
            "status": STATUS_ERROR,
            "backend": backend_name,
            "latency_ms": latency_ms,
            "detail": _safe_error_detail(exc),
        }


def _detect_cache_backend() -> str:
    """تشخیص نوع backend cache فعلی از روی کلاس backend واقعی."""
    try:
        from django.core.cache import caches

        real_backend = caches["default"]
        backend_module = real_backend.__class__.__module__.lower()
        backend_class = real_backend.__class__.__name__.lower()

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


# ─── Celery Broker Check ────────────────────────────────────


def check_celery_broker() -> dict[str, Any]:
    """
    چک readiness برای Celery broker بدون dispatch کردن task.

    برای Redis broker یک ping واقعی زده می‌شود. برای memory broker تست‌ها/dev
    ok برمی‌گردد. برای schemeهای TCP-based دیگر، socket connect کوتاه انجام
    می‌شود تا dependency availability بدون leak کردن credential بررسی شود.
    """
    broker_url = str(getattr(settings, "CELERY_BROKER_URL", ""))
    broker_label = _safe_url_label(broker_url)
    parsed = urlparse(broker_url)
    start = time.monotonic()

    try:
        if not broker_url:
            return {
                "status": STATUS_ERROR,
                "backend": "missing",
                "latency_ms": _latency_ms_since(start),
                "detail": "CELERY_BROKER_URL is not configured.",
            }

        if parsed.scheme == "memory":
            return {
                "status": STATUS_OK,
                "backend": "memory",
                "latency_ms": _latency_ms_since(start),
            }

        if parsed.scheme in {"redis", "rediss"}:
            client = redis.Redis.from_url(
                broker_url,
                socket_connect_timeout=2,
                socket_timeout=2,
            )
            client.ping()
        elif parsed.hostname:
            port = parsed.port or _default_port_for_scheme(parsed.scheme)
            if port is None:
                raise ValueError("Unsupported broker URL scheme")
            with socket.create_connection((parsed.hostname, port), timeout=2) as sock:
                sock.getpeername()
        else:
            raise ValueError("Invalid broker URL")

        latency_ms = _latency_ms_since(start)
        component_status = _status_for_latency(
            latency_ms,
            degraded_after_ms=BROKER_DEGRADED_AFTER_MS,
        )
        result: dict[str, Any] = {
            "status": component_status,
            "backend": broker_label,
            "latency_ms": latency_ms,
        }
        if component_status == STATUS_DEGRADED:
            result["detail"] = "Celery broker latency is above threshold."
            logger.warning("Celery broker health degraded broker=%s latency_ms=%s", broker_label, latency_ms)
        return result
    except Exception as exc:
        latency_ms = _latency_ms_since(start)
        logger.exception(
            "Celery broker health check failed broker=%s latency_ms=%s error_type=%s",
            broker_label,
            latency_ms,
            type(exc).__name__,
        )
        return {
            "status": STATUS_ERROR,
            "backend": broker_label,
            "latency_ms": latency_ms,
            "detail": _safe_error_detail(exc),
        }


def _default_port_for_scheme(scheme: str) -> int | None:
    """Return common TCP port for known broker URL schemes."""
    return {
        "amqp": 5672,
        "amqps": 5671,
    }.get(scheme)


# ─── Tabyin Sync Stats ──────────────────────────────────────


def check_tabyin_sync() -> dict[str, Any]:
    """
    گزارش وضعیت آخرین همگام‌سازی محتوای تبیین.

    این check diagnostic/non-critical است و فقط در صورت query failure خطا می‌دهد.
    """
    try:
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
        logger.exception("Tabyin sync health check failed error_type=%s", type(exc).__name__)
        return {
            "status": STATUS_ERROR,
            "detail": _safe_error_detail(exc),
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


def build_readiness_checks() -> dict[str, dict[str, Any]]:
    """Run all critical dependency checks required for serving traffic."""
    return {
        "database": check_database(),
        "cache": check_cache(),
        "celery_broker": check_celery_broker(),
    }


def build_detailed_checks() -> dict[str, dict[str, Any]]:
    """Run readiness checks plus non-critical diagnostic checks."""
    return {
        **build_readiness_checks(),
        "tabyin_sync": check_tabyin_sync(),
    }

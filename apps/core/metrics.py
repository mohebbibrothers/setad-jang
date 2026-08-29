"""Prometheus metrics primitives for Setad Jang observability.

یافتهٔ P1 فاز ۷ (صحت متریک در پروداکشن):
    deployment استاندارد این پروژه gunicorn با N worker است و registry
    ``prometheus_client`` به‌صورت پیش‌فرض **per-process** نگه داشته می‌شود؛
    یعنی یک اسکرپ که به یکی از workerها می‌خورد، فقط شمارنده‌های همان
    worker را می‌دید (~۱/N واقعِ کل) و بازیافت workerها (``max-requests``)
    شمارنده‌ها را بی‌صدا به صفر برمی‌گرداند.

الگوی رفع:
    حالت multiprocess خودِ prometheus_client — با env متغیر
    ``PROMETHEUS_MULTIPROC_DIR`` هر worker شمارش‌ها را در mmap-fileهای
    مشترک (روی tmpfs) می‌نویسد و مسیرِ exposition، همهٔ فایل‌ها را با
    ``MultiProcessCollector`` جمع می‌کند. توابع پایین تنها نقطهٔ اتصال
    این حالت‌اند تا business code هرگز شاخه‌ی «تک‌پروسه/چندپروسه» نبیند.
"""

from __future__ import annotations

import os
import time
from typing import Any

from prometheus_client import Counter, Gauge, Histogram

HTTP_REQUESTS_TOTAL = Counter(
    "setadjang_http_requests_total",
    "Total HTTP requests handled by Django.",
    ["method", "path", "status"],
)

HTTP_REQUEST_DURATION_SECONDS = Histogram(
    "setadjang_http_request_duration_seconds",
    "HTTP request latency in seconds.",
    ["method", "path"],
    buckets=(0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10),
)

HTTP_SLOW_REQUESTS_TOTAL = Counter(
    "setadjang_http_slow_requests_total",
    "HTTP requests exceeding configured performance contracts.",
    ["method", "path"],
)

HTTP_DB_QUERY_COUNT = Histogram(
    "setadjang_http_db_query_count",
    "Database query count per HTTP request.",
    ["method", "path"],
    buckets=(0, 1, 2, 5, 10, 20, 50, 100, 200, 500),
)

HTTP_DB_QUERY_TIME_SECONDS = Histogram(
    "setadjang_http_db_query_time_seconds",
    "Total database query time per HTTP request in seconds.",
    ["method", "path"],
    buckets=(0.001, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5),
)

HTTP_DB_SLOW_QUERIES_TOTAL = Counter(
    "setadjang_http_db_slow_queries_total",
    "Database queries exceeding slow-query threshold, grouped by HTTP request route.",
    ["method", "path"],
)

CELERY_TASKS_TOTAL = Counter(
    "setadjang_celery_tasks_total",
    "Total Celery tasks observed by lifecycle signals.",
    ["task", "state"],
)


CACHE_OPERATIONS_TOTAL = Counter(
    "setadjang_cache_operations_total",
    "Cache operations by namespace and outcome.",
    ["namespace", "operation", "outcome"],
)

CACHE_INVALIDATIONS_TOTAL = Counter(
    "setadjang_cache_invalidations_total",
    "Cache namespace invalidations by namespace.",
    ["namespace"],
)

FRONTEND_REVALIDATIONS_TOTAL = Counter(
    "setadjang_frontend_revalidations_total",
    "Frontend revalidation dispatch outcomes.",
    ["outcome"],
)


CACHE_INVALIDATION_OUTBOX_EVENTS = Gauge(
    "setadjang_cache_invalidation_outbox_events",
    "Cache invalidation outbox events by status.",
    ["status"],
)

CACHE_INVALIDATION_OUTBOX_OLDEST_PENDING_SECONDS = Gauge(
    "setadjang_cache_invalidation_outbox_oldest_pending_seconds",
    "Age of the oldest pending/failed cache invalidation event in seconds.",
)

FRONTEND_REVALIDATION_DURATION_SECONDS = Histogram(
    "setadjang_frontend_revalidation_duration_seconds",
    "Frontend revalidation HTTP request latency in seconds.",
    ["outcome"],
    buckets=(0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10),
)

CELERY_TASK_DURATION_SECONDS = Histogram(
    "setadjang_celery_task_duration_seconds",
    "Celery task runtime in seconds.",
    ["task"],
    buckets=(0.01, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10, 30, 60, 300, 900),
)


def multiprocess_mode_enabled() -> bool:
    """Return whether prometheus_client is running in multiprocess mode.

    env متغیر در هر فراخوانی خوانده می‌شود (نه import-time) تا تست و
    اسکریپت‌های استقرار بتوانند رفتار را بدون reload ماژول تغییر دهند؛
    این عمداً با نحوهٔ خوانش prometheus_client در زمان importِ `values`
    متفاوت است و همین «خوانش زنده» در سمتِ ماست، نه سمت کتابخانه.
    """
    return bool(os.environ.get("PROMETHEUS_MULTIPROC_DIR"))


def exposition_registry() -> Any:
    """Return the registry the scrape endpoint must render.

    - حالت چندپروسه‌ای: registry تازه با ``MultiProcessCollector`` — همهٔ
      workerها از روی فایل‌های mmap جمع می‌شوند. registryِ *پیش‌فرض* عمداً
      اضافه نمی‌شود، چون در این حالت خودش مقادیرِ همین پروسه را نگه می‌دارد
      و افزودنش شمارش را دوبرابر نشان می‌داد.
    - حالت تک‌پروسه‌ای (dev/test): همان ``REGISTRY`` پیش‌فرض برمی‌گردد.
    """
    if not multiprocess_mode_enabled():
        from prometheus_client import REGISTRY

        return REGISTRY

    from prometheus_client import CollectorRegistry
    from prometheus_client.multiprocess import MultiProcessCollector

    registry = CollectorRegistry()
    MultiProcessCollector(registry)
    return registry


def monotonic_time() -> float:
    """Return monotonic timestamp for latency measurement."""
    return time.monotonic()


def normalize_path(path: str) -> str:
    """Normalize request path to avoid unbounded metrics cardinality."""
    if not path:
        return "/"
    parts = []
    for part in path.strip("/").split("/"):
        if part.isdigit():
            parts.append("{id}")
        elif len(part) > 32 and any(ch.isdigit() for ch in part):
            parts.append("{token}")
        else:
            parts.append(part)
    return "/" + "/".join(parts)

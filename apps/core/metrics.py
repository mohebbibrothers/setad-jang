"""Prometheus metrics primitives for Setad Jang observability."""

from __future__ import annotations

import time

from prometheus_client import Counter, Histogram

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

CELERY_TASK_DURATION_SECONDS = Histogram(
    "setadjang_celery_task_duration_seconds",
    "Celery task runtime in seconds.",
    ["task"],
    buckets=(0.01, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10, 30, 60, 300, 900),
)


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

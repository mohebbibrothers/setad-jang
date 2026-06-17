"""Database query telemetry helpers for request-scoped performance diagnostics."""

from __future__ import annotations

import logging
from collections.abc import Callable
from contextlib import ExitStack
from dataclasses import dataclass
from typing import Any

from django.conf import settings
from django.db import connections
from django.http import HttpRequest, HttpResponse

from apps.core.metrics import monotonic_time

logger = logging.getLogger("apps.core.db_performance")


@dataclass(frozen=True)
class DBQueryTelemetrySnapshot:
    """Immutable summary of database work performed during one request."""

    query_count: int
    total_query_time_ms: float
    slow_query_count: int
    max_query_time_ms: float
    slow_threshold_ms: int

    def as_headers(self) -> dict[str, str]:
        """Return safe response headers with no SQL or parameter leakage."""
        return {
            "X-DB-Query-Count": str(self.query_count),
            "X-DB-Time-ms": f"{self.total_query_time_ms:.2f}",
        }


class DBQueryTelemetryCollector:
    """Collect query count and latency using Django connection execute wrappers."""

    def __init__(self, *, slow_threshold_ms: int) -> None:
        self.slow_threshold_ms = slow_threshold_ms
        self.query_count = 0
        self.total_query_time_ms = 0.0
        self.slow_query_count = 0
        self.max_query_time_ms = 0.0

    def __call__(
        self,
        execute: Callable[..., Any],
        sql: str,
        params: Any,
        many: bool,
        context: dict[str, Any],
    ) -> Any:
        """Wrap a DB execute call and record timing without logging SQL text."""
        started_at = monotonic_time()
        try:
            return execute(sql, params, many, context)
        finally:
            elapsed_ms = (monotonic_time() - started_at) * 1000
            self.query_count += 1
            self.total_query_time_ms += elapsed_ms
            self.max_query_time_ms = max(self.max_query_time_ms, elapsed_ms)
            if elapsed_ms > self.slow_threshold_ms:
                self.slow_query_count += 1

    def snapshot(self) -> DBQueryTelemetrySnapshot:
        """Return current telemetry as an immutable snapshot."""
        return DBQueryTelemetrySnapshot(
            query_count=self.query_count,
            total_query_time_ms=round(self.total_query_time_ms, 2),
            slow_query_count=self.slow_query_count,
            max_query_time_ms=round(self.max_query_time_ms, 2),
            slow_threshold_ms=self.slow_threshold_ms,
        )


def collect_request_db_telemetry(
    *,
    request: HttpRequest,
    get_response: Callable[[HttpRequest], HttpResponse],
) -> tuple[HttpResponse, DBQueryTelemetrySnapshot]:
    """Execute a request while collecting DB query telemetry for all configured connections."""
    threshold = int(getattr(settings, "DB_SLOW_QUERY_THRESHOLD_MS", 100))
    collector = DBQueryTelemetryCollector(slow_threshold_ms=threshold)
    with ExitStack() as stack:
        for connection in connections.all(initialized_only=True):
            stack.enter_context(connection.execute_wrapper(collector))
        response = get_response(request)
    return response, collector.snapshot()


def should_log_db_telemetry(*, snapshot: DBQueryTelemetrySnapshot) -> bool:
    """Return whether DB telemetry should be logged as degraded for a request."""
    max_queries = int(getattr(settings, "DB_QUERY_COUNT_WARNING_THRESHOLD", 50))
    max_total_ms = int(getattr(settings, "DB_TOTAL_QUERY_TIME_WARNING_MS", 500))
    return (
        snapshot.slow_query_count > 0
        or snapshot.query_count > max_queries
        or snapshot.total_query_time_ms > max_total_ms
    )


def log_db_telemetry_warning(*, path: str, method: str, snapshot: DBQueryTelemetrySnapshot) -> None:
    """Log safe DB request telemetry when budgets are exceeded."""
    logger.warning(
        "DB telemetry warning method=%s path=%s queries=%s total_ms=%.2f slow_queries=%s max_ms=%.2f threshold_ms=%s",
        method,
        path,
        snapshot.query_count,
        snapshot.total_query_time_ms,
        snapshot.slow_query_count,
        snapshot.max_query_time_ms,
        snapshot.slow_threshold_ms,
    )

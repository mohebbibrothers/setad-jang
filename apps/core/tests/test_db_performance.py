"""Core C3 database query telemetry tests."""

from __future__ import annotations

import pytest
from django.db import connection
from django.http import HttpResponse
from django.test import RequestFactory, override_settings

from apps.core.db_performance import collect_request_db_telemetry, should_log_db_telemetry
from apps.core.middleware import PrometheusMetricsMiddleware

pytestmark = pytest.mark.django_db


def test_collect_request_db_telemetry_counts_queries() -> None:
    """Request DB telemetry should count queries and record total DB time."""
    request = RequestFactory().get("/api/v1/db-test/")

    def get_response(_request):
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
            cursor.fetchone()
        return HttpResponse("ok")

    response, snapshot = collect_request_db_telemetry(request=request, get_response=get_response)

    assert response.status_code == 200
    assert snapshot.query_count == 1
    assert snapshot.total_query_time_ms >= 0
    assert snapshot.as_headers()["X-DB-Query-Count"] == "1"


@override_settings(
    PROMETHEUS_METRICS_ENABLED=True,
    DB_QUERY_TELEMETRY_ENABLED=True,
    DB_SLOW_QUERY_THRESHOLD_MS=0,
    DB_QUERY_COUNT_WARNING_THRESHOLD=0,
    DB_TOTAL_QUERY_TIME_WARNING_MS=0,
    DEFAULT_PERFORMANCE_BUDGET_MS=1000,
    PERFORMANCE_CONTRACTS={},
)
def test_metrics_middleware_adds_db_telemetry_headers() -> None:
    """Metrics middleware should add safe DB query telemetry headers."""
    request = RequestFactory().get("/api/v1/db-test/123/")

    def get_response(_request):
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
            cursor.fetchone()
        return HttpResponse("ok")

    response = PrometheusMetricsMiddleware(get_response)(request)

    assert response["X-DB-Query-Count"] == "1"
    assert float(response["X-DB-Time-ms"]) >= 0
    assert response["X-Performance-Budget-ms"] == "1000"


def test_should_log_db_telemetry_for_threshold_breaches(settings) -> None:
    """DB telemetry warning policy should trigger on query-count budget breach."""
    request = RequestFactory().get("/api/v1/db-test/")

    def get_response(_request):
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
            cursor.fetchone()
        return HttpResponse("ok")

    _response, snapshot = collect_request_db_telemetry(request=request, get_response=get_response)
    settings.DB_QUERY_COUNT_WARNING_THRESHOLD = 0

    assert should_log_db_telemetry(snapshot=snapshot) is True

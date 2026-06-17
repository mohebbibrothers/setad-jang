"""Core C1 performance contract and slow-request telemetry tests."""

from __future__ import annotations

from django.http import HttpResponse
from django.test import RequestFactory, override_settings

from apps.core.middleware import PrometheusMetricsMiddleware
from apps.core.performance import is_slow_request, resolve_performance_contract


def test_resolve_performance_contract_uses_exact_and_prefix_budget(settings) -> None:
    """Performance contracts should resolve exact method/path and longest prefix budgets."""
    settings.DEFAULT_PERFORMANCE_BUDGET_MS = 1000
    settings.PERFORMANCE_CONTRACTS = {
        "GET /api/v1/health/ready": 100,
        "/api/v1/support/admin/*": 2500,
        "/api/v1/*": 1500,
    }

    exact = resolve_performance_contract(method="GET", path="/api/v1/health/ready/")
    prefix = resolve_performance_contract(method="POST", path="/api/v1/support/admin/tickets/ABC/auto-assign/")
    default = resolve_performance_contract(method="GET", path="/other/")

    assert exact.budget_ms == 100
    assert exact.contract_key == "GET /api/v1/health/ready"
    assert prefix.budget_ms == 2500
    assert prefix.contract_key == "/api/v1/support/admin/*"
    assert default.budget_ms == 1000
    assert is_slow_request(duration_ms=2501, contract=prefix) is True


@override_settings(
    PROMETHEUS_METRICS_ENABLED=True,
    DEFAULT_PERFORMANCE_BUDGET_MS=50,
    PERFORMANCE_CONTRACTS={"/api/v1/test/*": 50},
)
def test_prometheus_middleware_adds_performance_headers_and_detects_slow(monkeypatch) -> None:
    """Metrics middleware should expose response-time headers from performance contract."""
    from apps.core import metrics

    timestamps = iter([10.0, 10.075])
    monkeypatch.setattr(metrics, "monotonic_time", lambda: next(timestamps))

    def get_response(request):
        return HttpResponse("ok", status=200)

    request = RequestFactory().get("/api/v1/test/123/")
    response = PrometheusMetricsMiddleware(get_response)(request)

    assert response["X-Response-Time-ms"] == "75.00"
    assert response["X-Performance-Budget-ms"] == "50"

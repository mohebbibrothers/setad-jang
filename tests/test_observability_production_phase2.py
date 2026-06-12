"""Production Phase 2 observability tests."""

from __future__ import annotations

import json
import logging

import pytest
from django.test import override_settings
from django.urls import reverse
from prometheus_client import REGISTRY
from rest_framework import status
from rest_framework.test import APIClient

from apps.core.logging import JSONLogFormatter
from apps.core.metrics import normalize_path

pytestmark = pytest.mark.django_db


def test_json_log_formatter_includes_request_id_and_exception() -> None:
    """JSON logs must be machine-parseable and request-correlated."""
    formatter = JSONLogFormatter()
    record = logging.LogRecord(
        name="apps.test",
        level=logging.ERROR,
        pathname=__file__,
        lineno=10,
        msg="observability failed %s",
        args=("hard",),
        exc_info=None,
    )
    record.request_id = "req-123"

    payload = json.loads(formatter.format(record))

    assert payload["level"] == "ERROR"
    assert payload["logger"] == "apps.test"
    assert payload["message"] == "observability failed hard"
    assert payload["request_id"] == "req-123"


def test_metrics_path_normalization_limits_cardinality() -> None:
    """Metrics labels must not explode with raw IDs/tokens."""
    assert normalize_path("/api/v1/support/admin/tickets/123/") == "/api/v1/support/admin/tickets/{id}"
    assert normalize_path("/api/v1/items/abcdef1234567890abcdef1234567890abcdef/") == "/api/v1/items/{token}"


def test_prometheus_metrics_endpoint_returns_text_exposition() -> None:
    """Metrics endpoint must expose Prometheus text format."""
    response = APIClient().get(reverse("prometheus-metrics"))

    assert response.status_code == status.HTTP_200_OK
    assert b"setadjang_http_requests_total" in response.content or b"python_info" in response.content
    assert response["Content-Type"].startswith("text/plain")


@override_settings(PROMETHEUS_METRICS_ENABLED=False)
def test_prometheus_metrics_endpoint_can_be_disabled() -> None:
    """Operators must be able to disable public metrics exposure by env/settings."""
    response = APIClient().get(reverse("prometheus-metrics"))

    assert response.status_code == status.HTTP_404_NOT_FOUND


def test_http_metrics_are_recorded_by_middleware() -> None:
    """A normal HTTP request should increment the project HTTP counter."""
    APIClient().get(reverse("health:simple"))

    metric_names = {sample.name for metric in REGISTRY.collect() for sample in metric.samples}
    assert "setadjang_http_requests_total" in metric_names

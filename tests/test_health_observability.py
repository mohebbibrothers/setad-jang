"""
Health and observability contract tests.

Phase 6 تضمین می‌کند health endpoints برای orchestration و monitoring حرفه‌ای
قابل اتکا باشند:
- liveness سریع و dependency-free است.
- readiness dependencyهای critical را با status code درست گزارش می‌کند.
- detailed health diagnosticهای تکمیلی دارد.
- خطاها secret-safe هستند و credential/URL خام leak نمی‌کنند.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient

from apps.core.health import checks as health_checks
from apps.core.health.views import _log_health_summary

pytestmark = pytest.mark.django_db


def test_liveness_endpoint_is_dependency_free_and_returns_ok() -> None:
    """Liveness نباید DB/cache/broker را لمس کند و همیشه process status بدهد."""
    client = APIClient()

    with patch("apps.core.health.views.build_readiness_checks") as mock_readiness:
        response = client.get(reverse("health:simple"))

    assert response.status_code == status.HTTP_200_OK
    assert response.data["status"] == health_checks.STATUS_OK
    assert "timestamp" in response.data
    mock_readiness.assert_not_called()


def test_readiness_endpoint_returns_503_when_critical_dependency_fails() -> None:
    """Readiness با error در dependency critical باید 503 بدهد."""
    client = APIClient()
    fake_checks = {
        "database": {"status": "ok", "latency_ms": 1.0, "backend": "sqlite"},
        "cache": {"status": "ok", "latency_ms": 1.0, "backend": "locmem"},
        "celery_broker": {
            "status": "error",
            "latency_ms": 1.0,
            "backend": "redis://redis:6379",
            "detail": "ConnectionError",
        },
    }

    with patch("apps.core.health.views.build_readiness_checks", return_value=fake_checks):
        response = client.get(reverse("health:ready"))

    assert response.status_code == status.HTTP_503_SERVICE_UNAVAILABLE
    assert response.data["status"] == health_checks.STATUS_ERROR
    assert response.data["checks"]["celery_broker"]["detail"] == "ConnectionError"


def test_readiness_endpoint_returns_200_for_degraded_dependency() -> None:
    """Degraded readiness باید 200 بدهد ولی body وضعیت degraded را نشان دهد."""
    client = APIClient()
    fake_checks = {
        "database": {
            "status": "degraded",
            "latency_ms": 999.0,
            "backend": "postgresql",
            "detail": "Database latency is above threshold.",
        },
        "cache": {"status": "ok", "latency_ms": 1.0, "backend": "redis"},
        "celery_broker": {"status": "ok", "latency_ms": 1.0, "backend": "redis://redis:6379"},
    }

    with patch("apps.core.health.views.build_readiness_checks", return_value=fake_checks):
        response = client.get(reverse("health:ready"))

    assert response.status_code == status.HTTP_200_OK
    assert response.data["status"] == health_checks.STATUS_DEGRADED


def test_detailed_endpoint_includes_system_and_diagnostic_checks() -> None:
    """Detailed health باید system info و diagnosticهای non-critical را شامل شود."""
    client = APIClient()
    fake_checks = {
        "database": {"status": "ok", "latency_ms": 1.0, "backend": "sqlite"},
        "cache": {"status": "ok", "latency_ms": 1.0, "backend": "locmem"},
        "celery_broker": {"status": "ok", "latency_ms": 0.0, "backend": "memory"},
        "tabyin_sync": {"status": "ok", "total_contents": 0, "active_contents": 0},
    }

    with patch("apps.core.health.views.build_detailed_checks", return_value=fake_checks):
        response = client.get(reverse("health:detailed"))

    assert response.status_code == status.HTTP_200_OK
    assert response.data["status"] == health_checks.STATUS_OK
    assert set(response.data["checks"]) == {"database", "cache", "celery_broker", "tabyin_sync"}
    assert response.data["system"]["project_name"] == "Setad Jang"
    assert "python_version" in response.data["system"]


def test_celery_broker_check_supports_memory_broker(settings) -> None:
    """memory:// broker در تست/dev باید بدون network call سالم باشد."""
    settings.CELERY_BROKER_URL = "memory://"

    result = health_checks.check_celery_broker()

    assert result["status"] == health_checks.STATUS_OK
    assert result["backend"] == "memory"


def test_celery_broker_check_does_not_leak_credentials(settings) -> None:
    """خطای broker نباید password موجود در URL را در response leak کند."""
    settings.CELERY_BROKER_URL = "redis://:super-secret-password@127.0.0.1:1/0"

    with patch(
        "apps.core.health.checks.redis.Redis.from_url",
        side_effect=RuntimeError("boom super-secret-password"),
    ):
        result = health_checks.check_celery_broker()

    result_text = str(result)
    assert result["status"] == health_checks.STATUS_ERROR
    assert "super-secret-password" not in result_text
    assert result["backend"] == "redis://127.0.0.1:1"
    assert result["detail"] == "RuntimeError"


def test_cache_check_reports_unexpected_value_as_error(monkeypatch: pytest.MonkeyPatch) -> None:
    """اگر cache مقدار اشتباه برگرداند، check باید error شود و لاگ‌پذیر باشد."""
    monkeypatch.setattr("apps.core.health.checks.cache.set", lambda *args, **kwargs: None)
    monkeypatch.setattr("apps.core.health.checks.cache.get", lambda *args, **kwargs: "wrong")
    monkeypatch.setattr("apps.core.health.checks.cache.delete", lambda *args, **kwargs: None)

    result = health_checks.check_cache()

    assert result["status"] == health_checks.STATUS_ERROR
    assert result["detail"] == "Cache returned unexpected value."


def test_health_summary_logs_failed_components() -> None:
    """Health summary logger باید component و latency خطادار را برای ops ثبت کند."""
    checks = {
        "database": {"status": "error", "latency_ms": 12.5, "detail": "OperationalError"},
        "cache": {"status": "ok", "latency_ms": 1.0},
    }

    with patch("apps.core.health.views.logger.error") as mock_error:
        _log_health_summary(endpoint="readiness", overall="error", checks=checks)

    mock_error.assert_called_once()
    assert "readiness" in mock_error.call_args.args
    assert "database" in str(mock_error.call_args.args)

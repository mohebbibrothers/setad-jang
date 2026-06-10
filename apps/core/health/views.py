"""
Views برای Health Check endpoints.

سه endpoint عملیاتی ارائه می‌شود:
- `/health/`: liveness بسیار سریع — فقط زنده بودن process را نشان می‌دهد.
- `/health/ready/`: readiness — dependencyهای critical را چک می‌کند.
- `/health/detailed/`: monitoring/debugging — readiness + diagnosticهای تکمیلی.

اصل مهم: health response نباید secret، DSN کامل، token، password یا traceback خام
را به client نشان دهد. جزئیات خطا safe و component-level هستند؛ لاگ‌ها برای ops
جزئیات بیشتری مثل component و latency را دارند.
"""

from __future__ import annotations

import logging
import platform
import time
from typing import Any

import django
from django.conf import settings
from django.utils import timezone
from drf_spectacular.utils import extend_schema
from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.core.health.checks import (
    STATUS_ERROR,
    aggregate_status,
    build_detailed_checks,
    build_readiness_checks,
    check_liveness,
)
from apps.core.health.serializers import (
    DetailedHealthSerializer,
    ReadinessHealthSerializer,
    SimpleHealthSerializer,
)

logger = logging.getLogger("apps.core.health")

# ─── Tag Constant ───────────────────────────────────────────

TAG_HEALTH = "سلامت سیستم"

# ─── Server Start Time (for uptime calculation) ─────────────

_SERVER_STARTED_AT = time.monotonic()


def _get_uptime_seconds() -> int:
    """محاسبه uptime سرور به ثانیه."""
    return int(time.monotonic() - _SERVER_STARTED_AT)


def _get_environment() -> str:
    """تشخیص محیط اجرا از روی DJANGO_SETTINGS_MODULE."""
    settings_module = settings.SETTINGS_MODULE or ""
    if "production" in settings_module:
        return "production"
    if "staging" in settings_module:
        return "staging"
    if "development" in settings_module:
        return "development"
    return "unknown"


def _build_system_info() -> dict[str, Any]:
    """ساخت dict اطلاعات سیستمی غیرحساس پروژه."""
    project_version = getattr(settings, "PROJECT_VERSION", "1.0.0")

    return {
        "project_name": "Setad Jang",
        "project_version": project_version,
        "django_version": django.get_version(),
        "python_version": platform.python_version(),
        "debug": settings.DEBUG,
        "environment": _get_environment(),
        "uptime_seconds": _get_uptime_seconds(),
    }


def _http_status_for_health(overall: str) -> int:
    """Map health status to HTTP status code."""
    return status.HTTP_503_SERVICE_UNAVAILABLE if overall == STATUS_ERROR else status.HTTP_200_OK


def _log_health_summary(*, endpoint: str, overall: str, checks: dict[str, dict[str, Any]]) -> None:
    """Log degraded/error components with enough context for operators."""
    if overall == "ok":
        logger.debug("Health endpoint ok endpoint=%s", endpoint)
        return

    components = {
        name: {
            "status": result.get("status"),
            "latency_ms": result.get("latency_ms"),
            "detail": result.get("detail"),
        }
        for name, result in checks.items()
        if result.get("status") != "ok"
    }

    if overall == STATUS_ERROR:
        logger.error("Health endpoint failed endpoint=%s components=%s", endpoint, components)
    else:
        logger.warning("Health endpoint degraded endpoint=%s components=%s", endpoint, components)


# ─── Liveness Endpoint ──────────────────────────────────────


class SimpleHealthView(APIView):
    """
    Liveness probe — فقط زنده بودن process.

    این endpoint dependency خارجی را چک نمی‌کند تا orchestrator به‌خاطر قطعی
    DB/Redis بی‌دلیل process سالم را restart نکند. readiness برای dependencyهاست.
    """

    permission_classes = [AllowAny]
    throttle_classes = []

    @extend_schema(
        operation_id="health_liveness",
        tags=[TAG_HEALTH],
        summary="Liveness check",
        description=(
            "بررسی سریع زنده بودن process بدون چک dependency خارجی.\n\n"
            "برای Kubernetes/Docker liveness probe و load balancerهای ساده مناسب است."
        ),
        responses={200: SimpleHealthSerializer},
    )
    def get(self, request: Request) -> Response:
        result = check_liveness()
        return Response(
            data={
                "status": result["status"],
                "timestamp": timezone.now().isoformat(),
            },
            status=status.HTTP_200_OK,
        )


# ─── Readiness Endpoint ─────────────────────────────────────


class ReadinessHealthView(APIView):
    """
    Readiness probe — dependencyهای critical برای سرو traffic.

    اگر DB/cache/broker error باشند، 503 برمی‌گرداند. degraded با 200 برمی‌گردد
    ولی در body و logs مشخص می‌شود تا monitoring هشدار بدهد.
    """

    permission_classes = [AllowAny]
    throttle_classes = []

    @extend_schema(
        operation_id="health_readiness",
        tags=[TAG_HEALTH],
        summary="Readiness check",
        description=(
            "بررسی dependencyهای critical برای سرو کردن traffic:\n"
            "Database، Cache و Celery broker.\n\n"
            "- `200 status=ok`: آماده سرویس‌دهی\n"
            "- `200 status=degraded`: آماده ولی کند/غیربهینه\n"
            "- `503 status=error`: آماده سرویس‌دهی نیست"
        ),
        responses={
            200: ReadinessHealthSerializer,
            503: ReadinessHealthSerializer,
        },
    )
    def get(self, request: Request) -> Response:
        checks = build_readiness_checks()
        overall = aggregate_status(checks)
        _log_health_summary(endpoint="readiness", overall=overall, checks=checks)

        return Response(
            data={
                "status": overall,
                "timestamp": timezone.now().isoformat(),
                "checks": checks,
            },
            status=_http_status_for_health(overall),
        )


# ─── Detailed Health Endpoint ───────────────────────────────


class DetailedHealthView(APIView):
    """
    Health check کامل — readiness + اطلاعات سیستم + diagnosticهای non-critical.

    مناسب dashboardهای monitoring و debugging. برای liveness/readiness مستقیم
    orchestration، از `/health/` و `/health/ready/` استفاده شود.
    """

    permission_classes = [AllowAny]
    throttle_classes = []

    @extend_schema(
        operation_id="health_detailed",
        tags=[TAG_HEALTH],
        summary="Detailed health check",
        description=(
            "بررسی جامع وضعیت کامپوننت‌های سیستم.\n\n"
            "شامل readiness checks و diagnosticهای تکمیلی مثل Tabyin sync.\n"
            "خروجی secret-safe است و credential/traceback خام نشان نمی‌دهد."
        ),
        responses={
            200: DetailedHealthSerializer,
            503: DetailedHealthSerializer,
        },
    )
    def get(self, request: Request) -> Response:
        checks = build_detailed_checks()
        overall = aggregate_status(checks)
        _log_health_summary(endpoint="detailed", overall=overall, checks=checks)

        return Response(
            data={
                "status": overall,
                "timestamp": timezone.now().isoformat(),
                "checks": checks,
                "system": _build_system_info(),
            },
            status=_http_status_for_health(overall),
        )

"""
Views برای Health Check endpoints.

دو endpoint ارائه می‌شود:
- `/health/`: ساده و سریع — برای liveness probe (load balancer)
- `/health/detailed/`: کامل با تمام checkها — برای monitoring
"""

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
    STATUS_OK,
    aggregate_status,
    check_cache,
    check_database,
    check_tabyin_sync,
)
from apps.core.health.serializers import (
    DetailedHealthSerializer,
    SimpleHealthSerializer,
)

logger = logging.getLogger("apps.core")


# ─── Tag Constant ───────────────────────────────────────────

TAG_HEALTH = "سلامت سیستم"


# ─── Server Start Time (for uptime calculation) ─────────────
# این مقدار یک بار در زمان import این ماژول ست می‌شود
# و تا restart شدن process ثابت می‌ماند.
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
    """ساخت dict اطلاعات سیستمی پروژه."""
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


# ─── Simple Health Endpoint ─────────────────────────────────


class SimpleHealthView(APIView):
    """
    Health check ساده — مناسب liveness probe.

    این endpoint سریع‌ترین حالت ممکن است و فقط نشان می‌دهد سرویس "زنده" است.
    برای استفاده توسط load balancer، Kubernetes liveness probe، یا uptime monitoring.

    پاسخ:
    - 200 OK: سرویس فعال است
    - 503 Service Unavailable: سرویس مشکل دارد
    """

    permission_classes = [AllowAny]
    # غیرفعال کردن throttle برای endpoint health
    throttle_classes = []

    @extend_schema(
        operation_id="health_simple",
        tags=[TAG_HEALTH],
        summary="چک سلامت ساده",
        description=(
            "بررسی سریع زنده بودن سرویس.\n\n"
            "این endpoint برای **liveness probe** ابزارهای DevOps طراحی شده "
            "(Kubernetes, Docker Swarm, AWS ELB, ...).\n\n"
            "**پاسخ:**\n"
            "- `200 OK`: سرویس فعال است\n"
            "- `503 Service Unavailable`: سرویس مشکل دارد\n\n"
            "این endpoint بدون throttle است."
        ),
        responses={
            200: SimpleHealthSerializer,
            503: SimpleHealthSerializer,
        },
    )
    def get(self, request: Request) -> Response:
        # فقط چک سریع DB انجام می‌دهیم — cache و بقیه در /detailed/
        db_check = check_database()

        overall = STATUS_OK if db_check["status"] == STATUS_OK else STATUS_ERROR
        http_status = (
            status.HTTP_200_OK if overall == STATUS_OK else status.HTTP_503_SERVICE_UNAVAILABLE
        )

        return Response(
            data={
                "status": overall,
                "timestamp": timezone.now().isoformat(),
            },
            status=http_status,
        )


# ─── Detailed Health Endpoint ───────────────────────────────


class DetailedHealthView(APIView):
    """
    Health check کامل — تمام چک‌ها + اطلاعات سیستم.

    مناسب برای dashboard‌های monitoring و debugging.
    """

    permission_classes = [AllowAny]
    throttle_classes = []

    @extend_schema(
        operation_id="health_detailed",
        tags=[TAG_HEALTH],
        summary="چک سلامت کامل سیستم",
        description=(
            "بررسی جامع وضعیت تمام کامپوننت‌های سیستم:\n\n"
            "**چک‌ها:**\n"
            "- 🗄 **Database**: اتصال + زمان پاسخ\n"
            "- 💾 **Cache**: اتصال + زمان پاسخ\n"
            "- 📊 **Tabyin Sync**: آمار محتواها + زمان آخرین همگام‌سازی\n\n"
            "**اطلاعات سیستم:**\n"
            "- نسخه پروژه، Django، Python\n"
            "- محیط اجرا (dev / staging / prod)\n"
            "- uptime سرور\n\n"
            "**کدهای پاسخ:**\n"
            "- `200 OK`: همه چیز سالم است (`status=ok`)\n"
            "- `200 OK` با `status=degraded`: عملکرد کند است\n"
            "- `503 Service Unavailable`: یک یا چند کامپوننت خطا دارد\n\n"
            "این endpoint بدون throttle است."
        ),
        responses={
            200: DetailedHealthSerializer,
            503: DetailedHealthSerializer,
        },
    )
    def get(self, request: Request) -> Response:
        # اجرای تمام چک‌ها
        checks = {
            "database": check_database(),
            "cache": check_cache(),
            "tabyin_sync": check_tabyin_sync(),
        }

        # جمع‌بندی وضعیت کلی
        overall = aggregate_status(checks)
        http_status = (
            status.HTTP_200_OK if overall != STATUS_ERROR else status.HTTP_503_SERVICE_UNAVAILABLE
        )

        return Response(
            data={
                "status": overall,
                "timestamp": timezone.now().isoformat(),
                "checks": checks,
                "system": _build_system_info(),
            },
            status=http_status,
        )

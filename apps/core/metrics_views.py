"""Prometheus metrics endpoint for production monitoring.

یافتهٔ P1 فاز ۷ (افشای اطلاعات + سطح حمله):
    این endpoint قبلاً `AllowAny` و بدون throttle بود؛ یعنی نقشهٔ کامل
    ترافیک سامانه (مسیرها، نرخ خطا، تاخیرها، شمارنده‌های Celery) برای هر
    بازدیدکننده‌ای خوانا بود و خودِ فراخوانی هم روی هر اسکرپ کل registry را
    serialize می‌کند — بستر مناسب برای DoS با درخواست‌های مکرر.

قرارداد دسترسی:
    - DEBUG: باز (توسعهٔ محلی بدون ceremonial).
    - production: تنها با هدر `Authorization: Bearer <PROMETHEUS_METRICS_TOKEN>`؛
      مقایسه با `constant_time_compare` و در نبودِ توکن تنظیم‌شده → 404
      (fail-closed و بدونِ افشای وجود endpoint).
    - حالتِ خاموش (`PROMETHEUS_METRICS_ENABLED=False`) هم 404 می‌دهد.

یکپارچگی با scrape-config پایدار است: پرومئتئوس `authorization: credentials`
همان Bearer scheme را می‌فرستد.
"""

from __future__ import annotations

from typing import Any

from django.conf import settings
from django.http import HttpRequest, HttpResponse
from django.utils.crypto import constant_time_compare
from drf_spectacular.utils import extend_schema
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest
from rest_framework.permissions import AllowAny
from rest_framework.views import APIView

from apps.core import metrics as core_metrics

_BEARER_PREFIX: str = "Bearer "


def scrape_authorized(request: HttpRequest) -> bool:
    """Return whether this request may read the metrics exposition.

    منطقِ fail-closed: در پروداکشن اگر اپراتور توکن تنظیم نکرده باشد،
    endpoint عملاً وجود ندارد (404) — نه این‌که باز بماند.
    """
    if settings.DEBUG:
        return True
    token = str(getattr(settings, "PROMETHEUS_METRICS_TOKEN", "") or "")
    if not token:
        return False
    header = request.headers.get("Authorization", "")
    if not header.startswith(_BEARER_PREFIX):
        return False
    return constant_time_compare(header[len(_BEARER_PREFIX) :].strip(), token)


class PrometheusMetricsView(APIView):
    """Expose Prometheus metrics when enabled and authorized.

    در حالت چندپروسه‌ای (پروداکشنِ این ریپو — gunicorn با N worker) خروجی از
    `exposition_registry()` خوانده می‌شود تا جمعِ کل workerها سرو شود؛ در
    حالت تک‌پروسه‌ای همان registry پیش‌فرض. جزئیاتِ چرا در
    `apps/core/metrics.py` مستند شده است.
    """

    permission_classes = [AllowAny]
    throttle_classes: list[Any] = []
    # عمداً خالی: احرازِ این endpoint یک هدر Bearerِ اختصاصیِ خودش است (پایین).
    # اگر JWTAuthentication جنگو روی همین هدر بدود، توکنِ اسکرپرِ نامعتبر قبل
    # از رسیدن به گیتِ ما 401 می‌گیرد و رفتار «بدون افشای وجود endpoint» (404)
    # خراب می‌شود؛ پروتکل اسکرپ پرومتئوس هم هیچ ارتباطی به JWT کاربری ندارد.
    authentication_classes: list[Any] = []

    @extend_schema(
        operation_id="metrics_prometheus",
        tags=["Observability"],
        summary="Prometheus scrape endpoint (token-gated in production)",
        description=(
            "خروجی text exposition برای Prometheus.\n\n"
            "دسترسی در production فقط با هدر "
            "`Authorization: Bearer $PROMETHEUS_METRICS_TOKEN`؛ بدون توکن "
            "`404` برمی‌گردد. در حالت `DEBUG` آزاد است."
        ),
        responses={200: None, 404: None},
    )
    def get(self, request: HttpRequest) -> HttpResponse:
        """Return Prometheus text exposition format (or 404 if off/forbidden)."""
        if not getattr(settings, "PROMETHEUS_METRICS_ENABLED", True):
            return HttpResponse(
                "metrics disabled", status=404, content_type="text/plain; charset=utf-8"
            )
        if not scrape_authorized(request):
            return HttpResponse(
                "metrics not found", status=404, content_type="text/plain; charset=utf-8"
            )
        return HttpResponse(
            generate_latest(core_metrics.exposition_registry()),
            content_type=CONTENT_TYPE_LATEST,
        )

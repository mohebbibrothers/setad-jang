"""Prometheus metrics endpoint for production monitoring."""

from __future__ import annotations

from django.conf import settings
from django.http import HttpResponse
from drf_spectacular.utils import extend_schema
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest
from rest_framework.permissions import AllowAny
from rest_framework.views import APIView


class PrometheusMetricsView(APIView):
    """Expose Prometheus metrics when enabled by settings."""

    permission_classes = [AllowAny]
    throttle_classes = []

    @extend_schema(
        operation_id="metrics_prometheus", tags=["Observability"], responses={200: None, 404: None}
    )
    def get(self, request):
        """Return Prometheus text exposition format."""
        if not getattr(settings, "PROMETHEUS_METRICS_ENABLED", True):
            return HttpResponse(
                "metrics disabled", status=404, content_type="text/plain; charset=utf-8"
            )
        return HttpResponse(generate_latest(), content_type=CONTENT_TYPE_LATEST)

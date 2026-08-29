"""
Main URL configuration for Setad Jang project.

این فایل entrypoint اصلی تمام URLهای پروژه است و مسئول:
- اتصال endpointهای اپ‌های مختلف
- wiring داکیومنتیشن OpenAPI / Swagger / ReDoc
- root redirect
- static/media serving در محیط development

اصول طراحی:
- تمام APIهای نسخه‌دار زیر `/api/v1/` قرار می‌گیرند.
- هر app با namespace اختصاصی include می‌شود تا reverse URL
  در کل پروژه ایمن و maintainable بماند.
- داکیومنتیشن از business endpointها جدا نگه داشته می‌شود.
- سرو static/media فقط در DEBUG فعال است.
"""

from __future__ import annotations

from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path
from django.views.generic import RedirectView

from apps.core.docs_gate import (
    GatedSpectacularAPIView,
    GatedSpectacularRedocView,
    GatedSpectacularSwaggerView,
)
from apps.core.metrics_views import PrometheusMetricsView
from apps.core.public_media import serve_public_media

# ============================================================
# Root / Documentation URLs
# ============================================================
# یافتۀ P1-4 فاز 7: این سه endpoint دیگر بدون‌گیت عمومی نیستند؛ سیاست
# دقیق (DEBUG / API_DOCS_ALLOW_ANONYMOUS / staff) در
# apps/core/docs_gate.py مستند شده است.

documentation_urlpatterns = [
    # ── Root redirect ───────────────────────────────────────
    path(
        "",
        RedirectView.as_view(url="/api/docs/", permanent=False),
        name="home",
    ),
    # ── OpenAPI schema ──────────────────────────────────────
    path(
        "api/schema/",
        GatedSpectacularAPIView.as_view(),
        name="schema",
    ),
    # ── Swagger UI ──────────────────────────────────────────
    path(
        "api/docs/",
        GatedSpectacularSwaggerView.as_view(url_name="schema"),
        name="swagger-ui",
    ),
    # ── ReDoc ───────────────────────────────────────────────
    path(
        "api/redoc/",
        GatedSpectacularRedocView.as_view(url_name="schema"),
        name="redoc",
    ),
]

# ============================================================
# Admin URLs
# ============================================================

admin_urlpatterns = [
    path("admin/", admin.site.urls),
]

# ============================================================
# Versioned API (v1)
# ============================================================

api_v1_urlpatterns = [
    # ── Health check ────────────────────────────────────────
    path(
        "api/v1/health/",
        include(("apps.core.health.urls", "health"), namespace="health"),
    ),
    # ── Prometheus metrics ──────────────────────────────────
    path("api/v1/metrics/", PrometheusMetricsView.as_view(), name="prometheus-metrics"),
    # ── Authentication ──────────────────────────────────────
    path(
        "api/v1/auth/",
        include(
            ("apps.authentication.urls", "authentication"),
            namespace="authentication",
        ),
    ),
    # ── Public Reports ──────────────────────────────────────
    path(
        "api/v1/public-reports/",
        include(
            ("apps.public_reports.urls", "public_reports"),
            namespace="public_reports",
        ),
    ),
    # ── Tabyin ──────────────────────────────────────────────
    path(
        "api/v1/tabyin/",
        include(("apps.tabyin.urls", "tabyin"), namespace="tabyin"),
    ),
    # ── Audit Logs ──────────────────────────────────────────
    path(
        "api/v1/audit-logs/",
        include(
            ("apps.audit_logs.urls", "audit_logs"),
            namespace="audit_logs",
        ),
    ),
    # ── R4J (Reward for Justice) ────────────────────────────
    path(
        "api/v1/r4j/",
        include(("apps.r4j.urls", "r4j"), namespace="r4j"),
    ),
    # ── Madadkar (Charitable Crowdfunding) ──────────────────
    path(
        "api/v1/madadkar/",
        include(("apps.madadkar.urls", "madadkar"), namespace="madadkar"),
    ),
    # ── LMS (Learning Management System) ────────────────────
    path(
        "api/v1/lms/",
        include(("apps.lms.urls", "lms"), namespace="lms"),
    ),
    # ── Kindness Wall (Divar-e Mehrabani) ──────────────────
    path(
        "api/v1/kindness-wall/",
        include(("apps.kindness_wall.urls", "kindness_wall"), namespace="kindness_wall"),
    ),
    # ── Support Desk (Ticketing) ────────────────────────────
    path(
        "api/v1/support/",
        include(("apps.support_desk.urls", "support_desk"), namespace="support_desk"),
    ),
    # ── Notifications ───────────────────────────────────────
    path(
        "api/v1/notifications/",
        include(("apps.notifications.urls", "notifications"), namespace="notifications"),
    ),
    # ── User Activity Timeline ──────────────────────────────
    path(
        "api/v1/activity/",
        include(("apps.activity.urls", "activity"), namespace="activity"),
    ),
    # ── Unified Admin Command Center ────────────────────────
    path(
        "api/v1/admin/command-center/",
        include(("apps.command_center.urls", "command_center"), namespace="command_center"),
    ),
]

# ============================================================
# Final urlpatterns
# ============================================================

urlpatterns = [
    *documentation_urlpatterns,
    *admin_urlpatterns,
    *api_v1_urlpatterns,
]


# ============================================================
# Public media files for isolated HTTP demo/local deployments
# ============================================================

if getattr(settings, "SERVE_PUBLIC_MEDIA", False):
    urlpatterns += [
        path("media/public/<path:path>", serve_public_media, name="public-media"),
    ]

# ============================================================
# Static / Media files (development only)
# ============================================================

if settings.DEBUG:
    urlpatterns += static(
        settings.MEDIA_URL,
        document_root=settings.MEDIA_ROOT,
    )
    urlpatterns += static(
        settings.STATIC_URL,
        document_root=settings.STATIC_ROOT,
    )

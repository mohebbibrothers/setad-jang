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
from drf_spectacular.views import (
    SpectacularAPIView,
    SpectacularRedocView,
    SpectacularSwaggerView,
)

# ============================================================
# Root / Documentation URLs
# ============================================================

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
        SpectacularAPIView.as_view(),
        name="schema",
    ),
    # ── Swagger UI ──────────────────────────────────────────
    path(
        "api/docs/",
        SpectacularSwaggerView.as_view(url_name="schema"),
        name="swagger-ui",
    ),
    # ── ReDoc ───────────────────────────────────────────────
    path(
        "api/redoc/",
        SpectacularRedocView.as_view(url_name="schema"),
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

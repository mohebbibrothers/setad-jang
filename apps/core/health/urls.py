"""URL routing برای Health Check endpoints."""

from django.urls import path

from apps.core.health.views import DetailedHealthView, SimpleHealthView

app_name = "health"

urlpatterns = [
    # ── Liveness probe (سریع، برای load balancer) ──
    path(
        "",
        SimpleHealthView.as_view(),
        name="simple",
    ),
    # ── Detailed check (کامل، برای monitoring) ─────
    path(
        "detailed/",
        DetailedHealthView.as_view(),
        name="detailed",
    ),
]

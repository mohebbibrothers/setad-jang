"""URL routing برای Health Check endpoints."""

from django.urls import path

from apps.core.health.views import (
    DetailedHealthView,
    ReadinessHealthView,
    SimpleHealthView,
)

app_name = "health"

urlpatterns = [
    path(
        "",
        SimpleHealthView.as_view(),
        name="simple",
    ),
    path(
        "ready/",
        ReadinessHealthView.as_view(),
        name="ready",
    ),
    path(
        "detailed/",
        DetailedHealthView.as_view(),
        name="detailed",
    ),
]

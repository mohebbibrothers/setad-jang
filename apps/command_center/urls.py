"""URL routing for admin command center."""

from django.urls import path

from apps.command_center.views import CommandCenterSummaryView

app_name = "command_center"

urlpatterns = [
    path("", CommandCenterSummaryView.as_view(), name="summary"),
]

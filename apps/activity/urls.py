"""URL routing for activity timeline."""

from django.urls import path

from apps.activity import views

app_name = "activity"

urlpatterns = [
    path("me/", views.UserActivityTimelineView.as_view(), name="user-timeline"),
    path("admin/", views.AdminActivityTimelineView.as_view(), name="admin-timeline"),
]

"""URL routing for notifications."""

from django.urls import path

from apps.notifications import views

app_name = "notifications"

urlpatterns = [
    path("me/", views.NotificationInboxView.as_view(), name="inbox"),
    path("me/<int:delivery_id>/read/", views.NotificationMarkReadView.as_view(), name="mark-read"),
    path("me/read-all/", views.NotificationMarkAllReadView.as_view(), name="mark-all-read"),
    path("me/preferences/", views.NotificationPreferenceListSetView.as_view(), name="preferences"),
    path("admin/events/", views.NotificationAdminEventListView.as_view(), name="admin-event-list"),
    path(
        "admin/deliveries/",
        views.NotificationAdminDeliveryListView.as_view(),
        name="admin-delivery-list",
    ),
    path(
        "admin/templates/",
        views.NotificationAdminTemplateListView.as_view(),
        name="admin-template-list",
    ),
]

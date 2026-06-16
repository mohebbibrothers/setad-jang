"""URL routing اپ audit_logs."""

from django.urls import path

from .views import AdminAuditLogDetailAPIView, AdminAuditLogExportAPIView, AdminAuditLogListAPIView

app_name = "audit_logs"

urlpatterns = [
    # ── Admin ───────────────────────────────────────
    path(
        "admin/logs/",
        AdminAuditLogListAPIView.as_view(),
        name="admin-log-list",
    ),
    path(
        "admin/logs/export/",
        AdminAuditLogExportAPIView.as_view(),
        name="admin-log-export",
    ),
    path(
        "admin/logs/<int:audit_log_id>/",
        AdminAuditLogDetailAPIView.as_view(),
        name="admin-log-detail",
    ),
]

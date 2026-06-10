"""URL routing اپ گزارشات مردمی."""

from django.urls import path

from .views import (
    AdminReportDetailAPIView,
    AdminReportListAPIView,
    AdminReportStatusUpdateAPIView,
    AdminSubjectDetailAPIView,
    AdminSubjectListCreateAPIView,
    ReportCreateAPIView,
    ReportSubjectListAPIView,
)

app_name = "public_reports"

urlpatterns = [
    # ── Public ──────────────────────────────────────
    path(
        "subjects/",
        ReportSubjectListAPIView.as_view(),
        name="subject-list",
    ),
    path(
        "reports/",
        ReportCreateAPIView.as_view(),
        name="report-create",
    ),
    # ── Admin: Subjects (CRUD کامل موضوعات) ─────────
    path(
        "admin/subjects/",
        AdminSubjectListCreateAPIView.as_view(),
        name="admin-subject-list-create",
    ),
    path(
        "admin/subjects/<int:subject_id>/",
        AdminSubjectDetailAPIView.as_view(),
        name="admin-subject-detail",
    ),
    # ── Admin: Reports ──────────────────────────────
    path(
        "admin/reports/",
        AdminReportListAPIView.as_view(),
        name="admin-report-list",
    ),
    path(
        "admin/reports/<int:report_id>/",
        AdminReportDetailAPIView.as_view(),
        name="admin-report-detail",
    ),
    path(
        "admin/reports/<int:report_id>/status/",
        AdminReportStatusUpdateAPIView.as_view(),
        name="admin-report-status",
    ),
]

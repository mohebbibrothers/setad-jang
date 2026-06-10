"""
URL routing اپ تبیین.

ساختار:
- Public: مسیرهای عمومی محتوا
- User: ارسال محتوا توسط کاربران احرازشده و مشاهده وضعیت بررسی
- Admin: مدیریت محتواها، بررسی submissions و sync async
"""

from django.urls import path

from apps.tabyin import views

app_name = "tabyin"

urlpatterns = [
    # ── Public ──────────────────────────────────────
    path(
        "contents/",
        views.PublicTabyinContentListView.as_view(),
        name="public-content-list",
    ),
    path(
        "contents/<str:external_id>/",
        views.PublicTabyinContentDetailView.as_view(),
        name="public-content-detail",
    ),
    # ── User submissions ────────────────────────────
    path(
        "me/submissions/",
        views.UserTabyinSubmissionListCreateView.as_view(),
        name="user-submission-list-create",
    ),
    path(
        "me/submissions/<int:content_id>/",
        views.UserTabyinSubmissionDetailView.as_view(),
        name="user-submission-detail",
    ),
    # ── Admin: Content management ───────────────────
    path(
        "admin/contents/",
        views.AdminTabyinContentListView.as_view(),
        name="admin-content-list",
    ),
    path(
        "admin/contents/<str:external_id>/",
        views.AdminTabyinContentDetailView.as_view(),
        name="admin-content-detail",
    ),
    path(
        "admin/contents/<str:external_id>/toggle/",
        views.AdminTabyinContentToggleView.as_view(),
        name="admin-content-toggle",
    ),
    # ── Admin: User submission review ───────────────
    path(
        "admin/submissions/",
        views.AdminTabyinSubmissionQueueView.as_view(),
        name="admin-submission-list",
    ),
    path(
        "admin/submissions/<int:content_id>/",
        views.AdminTabyinSubmissionDetailView.as_view(),
        name="admin-submission-detail",
    ),
    path(
        "admin/submissions/<int:content_id>/approve/",
        views.AdminTabyinSubmissionApproveView.as_view(),
        name="admin-submission-approve",
    ),
    path(
        "admin/submissions/<int:content_id>/reject/",
        views.AdminTabyinSubmissionRejectView.as_view(),
        name="admin-submission-reject",
    ),
    # ── Admin: Async sync (Celery) ──────────────────
    path(
        "admin/sync/",
        views.AdminSyncTriggerView.as_view(),
        name="admin-sync-trigger",
    ),
    path(
        "admin/sync/status/<str:task_id>/",
        views.AdminSyncTaskStatusView.as_view(),
        name="admin-sync-status",
    ),
]

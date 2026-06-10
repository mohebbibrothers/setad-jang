"""
URL routing اپ تبیین.

ساختار:
- Public: مسیرهای عمومی محتوا
- Admin: مدیریت محتواها (لیست، جزئیات، toggle)
- Admin async sync: dispatch کردن sync به‌صورت async و پیگیری وضعیت آن

نکته:
نام مسیرها به‌صورت kebab-case تعریف شده‌اند تا با استاندارد پروژه
هماهنگ باشند و در `reverse()` نیز قابل اتکا بمانند.
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

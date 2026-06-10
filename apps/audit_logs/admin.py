"""
Django admin configuration for immutable audit log inspection.
"""

from django.contrib import admin

from .models import AuditLog


@admin.register(AuditLog)
class AuditLogAdmin(admin.ModelAdmin):
    """
    Admin panel برای مشاهده لاگ‌های فعالیت.

    این مدل فقط read-only است و امکان ایجاد، ویرایش یا حذف ندارد.
    """

    list_display = (
        "action",
        "user",
        "resource_type",
        "resource_id",
        "ip_address",
        "request_id",
        "created_at",
    )
    list_filter = ("action", "resource_type", "created_at")
    search_fields = ("action", "resource_type", "resource_id", "ip_address", "request_id")
    readonly_fields = (
        "user",
        "action",
        "ip_address",
        "request_id",
        "resource_type",
        "resource_id",
        "changes",
        "extra_data",
        "created_at",
        "updated_at",
    )
    ordering = ("-created_at",)

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

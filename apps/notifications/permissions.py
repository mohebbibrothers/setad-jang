"""Permissions for notifications."""

from rest_framework.permissions import BasePermission


class IsNotificationAdminUser(BasePermission):
    """Allow staff/superuser/admin users to inspect notification operations."""

    message = "برای مدیریت اعلان‌ها باید دسترسی ادمین داشته باشید."

    def has_permission(self, request, view) -> bool:
        """Check admin permission."""
        user = request.user
        return bool(
            user
            and user.is_authenticated
            and (user.is_staff or user.is_superuser or getattr(user, "role", "") == "admin")
        )

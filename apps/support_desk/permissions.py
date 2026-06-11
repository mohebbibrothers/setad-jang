"""Permissions for Support Desk."""

from rest_framework.permissions import BasePermission


class IsSupportAdminUser(BasePermission):
    """Allow staff, superuser or admin-role users to manage support operations."""

    message = "برای مدیریت میز پشتیبانی باید دسترسی ادمین داشته باشید."

    def has_permission(self, request, view) -> bool:
        """Check support admin permission boundary."""
        user = request.user
        return bool(user and user.is_authenticated and (user.is_staff or user.is_superuser or getattr(user, "role", "") == "admin"))

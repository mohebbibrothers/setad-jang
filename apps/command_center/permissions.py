"""Permissions for admin command center."""

from rest_framework.permissions import BasePermission


class IsCommandCenterAdminUser(BasePermission):
    """Allow staff/superuser/admin-role users to access command center."""

    message = "برای مشاهده مرکز فرماندهی باید دسترسی ادمین داشته باشید."

    def has_permission(self, request, view) -> bool:
        """Check admin permission."""
        user = request.user
        return bool(user and user.is_authenticated and (user.is_staff or user.is_superuser or getattr(user, "role", "") == "admin"))

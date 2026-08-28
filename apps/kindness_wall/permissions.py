"""Permissions for Kindness Wall."""

from rest_framework.permissions import BasePermission


class IsKindnessAdminUser(BasePermission):
    """Allow staff/superuser/admin-role users."""

    message = "برای مدیریت دیوار مهربانی باید دسترسی ادمین داشته باشید."

    def has_permission(self, request, view) -> bool:
        """Check admin permission."""
        user = request.user
        return bool(
            user
            and user.is_authenticated
            and (user.is_staff or user.is_superuser or getattr(user, "role", "") == "admin")
        )

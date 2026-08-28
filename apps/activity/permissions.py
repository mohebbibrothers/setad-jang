"""Permissions for activity timeline."""

from rest_framework.permissions import BasePermission


class IsActivityAdminUser(BasePermission):
    """Allow admin users to inspect all activity."""

    message = "برای مشاهده خط زمانی همه کاربران باید دسترسی ادمین داشته باشید."

    def has_permission(self, request, view) -> bool:
        """Check admin permission."""
        user = request.user
        return bool(
            user
            and user.is_authenticated
            and (user.is_staff or user.is_superuser or getattr(user, "role", "") == "admin")
        )

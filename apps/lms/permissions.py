"""
DRF permission classes for LMS endpoints.

Endpoint-specific permission composition remains in views; reusable object-level
rules are centralized here.
"""

from rest_framework.permissions import BasePermission

from apps.authentication.choices import UserRole


class IsLMSAdminUser(BasePermission):
    """Allow only staff/superuser/admin-role users to manage LMS resources."""

    message = "برای مدیریت سامانه آموزش باید دسترسی ادمین داشته باشید."

    def has_permission(self, request, view) -> bool:
        user = request.user
        return bool(
            user
            and user.is_authenticated
            and (user.is_staff or user.is_superuser or getattr(user, "role", None) == UserRole.ADMIN)
        )


class IsEnrollmentOwner(BasePermission):
    """Object permission for enrollment ownership."""

    message = "شما به این ثبت‌نام دسترسی ندارید."

    def has_object_permission(self, request, view, obj) -> bool:
        return bool(request.user and request.user.is_authenticated and obj.user_id == request.user.pk)

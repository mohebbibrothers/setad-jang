"""Permissionهای مشترک API دیوار مهربانی."""

from rest_framework.permissions import BasePermission


class IsKindnessAdminUser(BasePermission):
    """اجازهٔ دسترسی پنل ادمین: staff/superuser/نقش admin."""

    message = "برای مدیریت دیوار مهربانی باید دسترسی ادمین داشته باشید."

    def has_permission(self, request, view) -> bool:
        """بررسی سه‌شاخهٔ دسترسی ادمین (سازگار با مدل نقش پروژه)."""
        user = request.user
        return bool(
            user
            and user.is_authenticated
            and (user.is_staff or user.is_superuser or getattr(user, "role", "") == "admin")
        )

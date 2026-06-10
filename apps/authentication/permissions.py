from rest_framework.permissions import BasePermission

from .choices import UserRole


class IsAdminUser(BasePermission):
    """فقط کاربران با نقش admin."""

    message = "شما دسترسی ادمین ندارید."

    def has_permission(self, request, view):
        return bool(
            request.user and request.user.is_authenticated and request.user.role == UserRole.ADMIN
        )


class IsEmailVerified(BasePermission):
    """کاربران فقط در صورت تأیید ایمیل اجازه دارن."""

    message = "ابتدا ایمیل خود را تأیید کنید."

    def has_permission(self, request, view):
        return bool(
            request.user and request.user.is_authenticated and request.user.is_email_verified
        )


class IsSelfOrAdmin(BasePermission):
    """کاربر فقط به اطلاعات خودش یا ادمین به همه دسترسی داره."""

    def has_object_permission(self, request, view, obj):
        if request.user.role == UserRole.ADMIN:
            return True
        if hasattr(obj, "user"):
            return obj.user == request.user
        return obj == request.user

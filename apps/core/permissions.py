from rest_framework.permissions import BasePermission


class IsAdmin(BasePermission):
    message = "شما دسترسی ادمین ندارید."

    def has_permission(self, request, view):
        return bool(request.user and request.user.is_authenticated and request.user.is_staff)


class IsSuperAdmin(BasePermission):
    message = "شما دسترسی سوپرادمین ندارید."

    def has_permission(self, request, view):
        return bool(request.user and request.user.is_authenticated and request.user.is_superuser)


class IsOwner(BasePermission):
    message = "شما مالک این آبجکت نیستید."

    def has_object_permission(self, request, view, obj):
        if hasattr(obj, "user"):
            return obj.user == request.user
        if hasattr(obj, "created_by"):
            return obj.created_by == request.user
        return False

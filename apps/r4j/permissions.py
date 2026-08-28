"""
Permissions اپ R4J.

این فایل permissionهای granular دامنه R4J را نگه می‌دارد.

اصول طراحی:
- error messages واضح و راهنما هستند تا UX کاربر مشخص باشد.
- IsFullyVerifiedUser پیام دقیق برمی‌گرداند که کدام شرط برقرار نیست.
- object-level permissions برای جلوگیری از IDOR
  (Insecure Direct Object Reference).
"""

from __future__ import annotations

from typing import Any

from rest_framework.permissions import BasePermission
from rest_framework.request import Request

from apps.authentication.choices import UserRole


class IsR4JAdminUser(BasePermission):
    """دسترسی فقط برای کاربران با نقش admin."""

    message = "این عملیات فقط برای ادمین مجاز است."

    def has_permission(self, request: Request, view: Any) -> bool:
        user = request.user
        return bool(
            user and user.is_authenticated and getattr(user, "role", None) == UserRole.ADMIN,
        )


class IsFullyVerifiedUser(BasePermission):
    """
    دسترسی فقط برای کاربرانی که:
    - لاگین کرده‌اند
    - ایمیل + شماره موبایل تأیید شده
    - پروفایل (فیلدهای الزامی R4J) کامل پر شده

    این permission برای high-trust operations مثل تعیین جایزه استفاده می‌شود.
    error message بسته به اولین شرط نقض‌شده dynamic ساخته می‌شود.
    """

    def has_permission(self, request: Request, view: Any) -> bool:
        user = request.user

        if not (user and user.is_authenticated):
            self.message = "برای این عملیات باید ابتدا وارد حساب کاربری شوید."
            return False

        if not getattr(user, "is_email_verified", False):
            self.message = "برای این عملیات باید ابتدا ایمیل خود را تأیید کنید."
            return False

        if not getattr(user, "is_phone_verified", False):
            self.message = "برای این عملیات باید ابتدا شماره موبایل خود را تأیید کنید."
            return False

        profile = getattr(user, "profile", None)
        if profile is None:
            self.message = "ابتدا پروفایل خود را تکمیل کنید."
            return False

        missing = profile.get_missing_r4j_fields()
        if missing:
            self.message = (
                "برای این عملیات باید ابتدا پروفایل خود را کامل کنید. "
                f"فیلدهای ناقص: {', '.join(missing)}"
            )
            return False

        return True


class IsBountyOwner(BasePermission):
    """کاربر فقط می‌تواند روی bounty خودش عملیات انجام دهد."""

    message = "این جایزه متعلق به شما نیست."

    def has_object_permission(self, request: Request, view: Any, obj: Any) -> bool:
        return bool(obj.user_id == request.user.pk)


class IsReportOwner(BasePermission):
    """کاربر فقط می‌تواند روی report خودش عملیات انجام دهد."""

    message = "این گزارش متعلق به شما نیست."

    def has_object_permission(self, request: Request, view: Any, obj: Any) -> bool:
        return bool(obj.submitted_by_id == request.user.pk)

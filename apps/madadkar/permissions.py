"""
Permissions اپ مددکار.

ساختار:
- IsMadadkarAdminUser: محدودیت برای ادمین (alias تمیز روی IsAdminUser).
- IsAuthenticatedBasic: محدودیت برای کاربر لاگین معمولی (نه احراز کامل).
- IsParticipationOwner: کاربر فقط مشارکت‌های خودش را می‌بیند (IDOR protection).
- IsPaymentOwner: کاربر فقط پرداخت‌های خودش را می‌بیند.

نکته معماری مهم:
- اپ مددکار **نیازی به احراز هویت کامل (IsFullyVerifiedUser) ندارد**.
  لاگین معمولی برای مشارکت کافی است (این تصمیم در ADR گرفته شد).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from rest_framework.permissions import BasePermission, IsAdminUser, IsAuthenticated

if TYPE_CHECKING:
    from rest_framework.request import Request
    from rest_framework.views import APIView


class IsMadadkarAdminUser(IsAdminUser):
    """
    دسترسی ادمین برای endpointهای مدیریت مددکار.

    Alias تمیز روی IsAdminUser برای خوانایی بهتر در view‌ها.
    """

    message = "این عملیات فقط برای مدیران سامانه مجاز است."


class IsAuthenticatedBasic(IsAuthenticated):
    """
    دسترسی کاربر لاگین‌شده — برای مشارکت در حرکت‌ها.

    تفاوت با IsFullyVerifiedUser در r4j:
    - فقط لاگین کافی است.
    - نیازی به تأیید ایمیل + موبایل + تکمیل پروفایل نیست.
    - تصمیم معماری: مشارکت خیریه باید برای حداکثر کاربران در دسترس باشد.
    """

    message = "برای انجام این عملیات باید وارد حساب کاربری شوید."


class IsParticipationOwner(BasePermission):
    """
    بررسی مالکیت کاربر بر یک Participation.

    استفاده در endpointهای جزئیات و عملیات روی participation شخصی.
    جلوگیری از IDOR — کاربر A نباید بتواند participation کاربر B را ببیند.
    """

    message = "شما به این مشارکت دسترسی ندارید."

    def has_object_permission(
        self,
        request: Request,
        view: APIView,
        obj,
    ) -> bool:
        """فقط صاحب participation اجازه دسترسی دارد."""
        return bool(
            request.user and request.user.is_authenticated and obj.user_id == request.user.pk,
        )


class IsPaymentOwner(BasePermission):
    """
    بررسی مالکیت کاربر بر یک Payment.

    استفاده در endpointهای جزئیات پرداخت شخصی.
    """

    message = "شما به این پرداخت دسترسی ندارید."

    def has_object_permission(
        self,
        request: Request,
        view: APIView,
        obj,
    ) -> bool:
        """فقط صاحب payment اجازه دسترسی دارد."""
        return bool(
            request.user and request.user.is_authenticated and obj.user_id == request.user.pk,
        )

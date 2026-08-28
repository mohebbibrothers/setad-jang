"""
Unified Response Classes — Envelope استاندارد پروژه ستاد جنگ.

تمام endpointهای پروژه از این کلاس‌ها برای ساخت response استفاده می‌کنند
تا فرمت پاسخ‌ها در کل API یکپارچه و قابل پیش‌بینی باشد.

فرمت استاندارد:

    Success:
    {
        "success": true,
        "status_code": 200,
        "message": "عملیات با موفقیت انجام شد.",
        "data": { ... }
    }

    Error:
    {
        "success": false,
        "status_code": 400,
        "message": "خطایی رخ داده است.",
        "errors": { ... }
    }

کلاس‌ها:
- SuccessResponse  : پاسخ موفق عمومی (200)
- CreatedResponse  : پاسخ موفق ساخت resource (201)
- DeletedResponse  : پاسخ موفق حذف resource (200, data=None)
- ErrorResponse    : پاسخ خطا (400 یا هر status دلخواه)

اصول طراحی:
- هر response class از rest_framework.response.Response ارث‌بری می‌کند.
- envelope به‌صورت خودکار ساخته می‌شود — view فقط data و message می‌دهد.
- status_code هم در body و هم در HTTP response header موجود است.
- type hints کامل برای IDE support و documentation.
- هیچ business logic در این فایل وجود ندارد.

Usage:
    from apps.core.responses import SuccessResponse, CreatedResponse, ErrorResponse

    # در view:
    return SuccessResponse(data=serializer.data, message="لیست دریافت شد.")
    return CreatedResponse(data=serializer.data, message="ساخته شد.")
    return DeletedResponse(message="حذف شد.")
    return ErrorResponse(message="ورودی نامعتبر.", errors=serializer.errors)
    return ErrorResponse(message="یافت نشد.", status_code=404)
"""

from __future__ import annotations

from typing import Any

from rest_framework import status
from rest_framework.response import Response


class SuccessResponse(Response):
    """
    پاسخ موفق عمومی — HTTP 200.

    برای عملیات‌هایی که resource جدید نمی‌سازند:
    - لیست‌ها
    - جزئیات
    - ویرایش
    - عملیات‌های موفق بدون ساخت resource

    Args:
        data: داده‌های اصلی پاسخ (dict, list, None).
        message: پیام فارسی قابل نمایش به کاربر.
        status_code: کد وضعیت HTTP (پیش‌فرض 200).
        **kwargs: سایر پارامترهای Response (مثل headers).
    """

    def __init__(
        self,
        data: Any = None,
        message: str = "عملیات با موفقیت انجام شد.",
        status_code: int = status.HTTP_200_OK,
        **kwargs: Any,
    ) -> None:
        super().__init__(
            data={
                "success": True,
                "status_code": status_code,
                "message": message,
                "data": data,
            },
            status=status_code,
            **kwargs,
        )


class CreatedResponse(Response):
    """
    پاسخ موفق ساخت resource — HTTP 201.

    برای عملیات‌هایی که resource جدید ساخته شده:
    - POST endpoints که record جدید می‌سازند
    - ثبت گزارش، ساخت criminal، ثبت bounty و ...

    Args:
        data: داده‌های resource ساخته‌شده.
        message: پیام فارسی قابل نمایش به کاربر.
        **kwargs: سایر پارامترهای Response.
    """

    def __init__(
        self,
        data: Any = None,
        message: str = "با موفقیت ایجاد شد.",
        **kwargs: Any,
    ) -> None:
        super().__init__(
            data={
                "success": True,
                "status_code": status.HTTP_201_CREATED,
                "message": message,
                "data": data,
            },
            status=status.HTTP_201_CREATED,
            **kwargs,
        )


class DeletedResponse(Response):
    """
    پاسخ موفق حذف resource — HTTP 200.

    برای عملیات‌های soft-delete یا hard-delete:
    - data همیشه None است چون resource حذف شده.
    - message باید به کاربر بگوید چه چیزی حذف شد.

    نکته: از HTTP 204 استفاده نمی‌کنیم چون:
    - envelope ما همیشه body دارد
    - 204 مطابق RFC بدون body است
    - 200 + data=None رفتار consistent‌تری می‌دهد

    این یک انحراف آگاهانه از قرارداد رایج REST است، پس صریحاً برای
    مصرف‌کنندهٔ frontend مستند شده است. اگر این رفتار را تغییر دادید،
    بخش «حذف (DELETE)» در docs/FRONTEND_INTEGRATION_GUIDE.md را هم
    به‌روز کنید.

    Args:
        message: پیام فارسی قابل نمایش به کاربر.
        **kwargs: سایر پارامترهای Response.
    """

    def __init__(
        self,
        message: str = "با موفقیت حذف شد.",
        **kwargs: Any,
    ) -> None:
        super().__init__(
            data={
                "success": True,
                "status_code": status.HTTP_200_OK,
                "message": message,
                "data": None,
            },
            status=status.HTTP_200_OK,
            **kwargs,
        )


class ErrorResponse(Response):
    """
    پاسخ خطا — HTTP 400 یا هر status code دلخواه.

    برای تمام سناریوهای خطا:
    - validation errors (400)
    - permission denied (403)
    - not found (404)
    - business logic errors (400)
    - conflict (409)
    - rate limit (429)

    فرمت errors:
    - می‌تواند dict باشد (مثل serializer.errors)
    - می‌تواند list باشد (مثل لیست خطاها)
    - می‌تواند None باشد (فقط message کافی است)

    Args:
        errors: جزئیات خطا (dict, list, None).
        message: پیام فارسی قابل نمایش به کاربر.
        status_code: کد وضعیت HTTP (پیش‌فرض 400).
        **kwargs: سایر پارامترهای Response.

    Usage:
        # validation error
        return ErrorResponse(
            message="ورودی نامعتبر است.",
            errors=serializer.errors,
        )

        # not found
        return ErrorResponse(
            message="مجرمی با این شناسه یافت نشد.",
            status_code=status.HTTP_404_NOT_FOUND,
        )

        # business logic error
        return ErrorResponse(
            message="این پروفایل قبلاً منتشر شده است.",
        )
    """

    def __init__(
        self,
        errors: Any = None,
        message: str = "خطایی رخ داده است.",
        status_code: int = status.HTTP_400_BAD_REQUEST,
        **kwargs: Any,
    ) -> None:
        super().__init__(
            data={
                "success": False,
                "status_code": status_code,
                "message": message,
                "errors": errors,
            },
            status=status_code,
            **kwargs,
        )

"""
Custom Exception Handler — تبدیل تمام استثناها به فرمت یکسان پاسخ پروژه.

این فایل entrypoint مرکزی error handling در کل API است.
تمام استثناها — چه DRF و چه Python — از اینجا عبور می‌کنند و
به فرمت envelope استاندارد پروژه تبدیل می‌شوند.

فرمت خروجی:
    {
        "success": false,
        "status_code": <int>,
        "message": "<پیام فارسی>",
        "errors": <جزئیات خطا | null>
    }

نکات کلیدی:
- استفاده از exception_handler پیش‌فرض DRF برای استثناهای شناخته‌شده.
- استخراج message سفارشی از PermissionDenied (برای IsFullyVerifiedUser و ...).
- در صورت استثنای ناشناخته (500): لاگ‌گذاری امن و حرفه‌ای.
- در حالت DEBUG: traceback کامل برای توسعه‌دهنده.
- در حالت production: فقط اطلاعات لازم بدون افشای جزئیات داخلی.

Usage:
    # در settings:
    REST_FRAMEWORK = {
        "EXCEPTION_HANDLER": "apps.core.exceptions.custom_exception_handler",
    }
"""

from __future__ import annotations

import logging
import traceback
from typing import Any

from django.conf import settings
from rest_framework import status
from rest_framework.exceptions import (
    PermissionDenied,
    Throttled,
    ValidationError,
)
from rest_framework.response import Response
from rest_framework.views import exception_handler

logger = logging.getLogger(__name__)


# ============================================================
# پیام‌های فارسی استاندارد — per status code
# ============================================================

_DEFAULT_MESSAGES: dict[int, str] = {
    status.HTTP_400_BAD_REQUEST: "درخواست نامعتبر است.",
    status.HTTP_401_UNAUTHORIZED: "احراز هویت انجام نشده است.",
    status.HTTP_403_FORBIDDEN: "شما دسترسی لازم را ندارید.",
    status.HTTP_404_NOT_FOUND: "موردی یافت نشد.",
    status.HTTP_405_METHOD_NOT_ALLOWED: "متد مجاز نیست.",
    status.HTTP_406_NOT_ACCEPTABLE: "فرمت درخواستی پشتیبانی نمی‌شود.",
    status.HTTP_409_CONFLICT: "تداخل در درخواست رخ داده است.",
    status.HTTP_413_REQUEST_ENTITY_TOO_LARGE: "حجم درخواست بیش از حد مجاز است.",
    status.HTTP_415_UNSUPPORTED_MEDIA_TYPE: "نوع محتوا پشتیبانی نمی‌شود.",
    status.HTTP_429_TOO_MANY_REQUESTS: (
        "تعداد درخواست‌های شما بیش از حد مجاز است. لطفاً کمی صبر کنید."
    ),
    status.HTTP_500_INTERNAL_SERVER_ERROR: "خطای داخلی سرور رخ داده است.",
    status.HTTP_503_SERVICE_UNAVAILABLE: "سرویس در حال حاضر در دسترس نیست.",
}


# ============================================================
# Main handler
# ============================================================


def custom_exception_handler(
    exc: Exception,
    context: dict[str, Any],
) -> Response:
    """
    Exception handler سفارشی پروژه.

    تمام استثناهای DRF و غیر-DRF را به فرمت envelope تبدیل می‌کند.

    Flow:
    1. ابتدا handler پیش‌فرض DRF فراخوانی می‌شود.
    2. اگر DRF آن را شناخت → envelope wrapper اعمال می‌شود.
    3. اگر DRF آن را نشناخت → 500 با لاگ امن ساخته می‌شود.

    Args:
        exc: استثنای رخ‌داده.
        context: اطلاعات context شامل view و request.

    Returns:
        Response با فرمت envelope استاندارد.
    """
    response = exception_handler(exc, context)

    if response is not None:
        return _build_handled_response(response, exc)

    return _build_unhandled_response(exc, context)


# ============================================================
# Handled exceptions (DRF-recognized)
# ============================================================


def _build_handled_response(response: Response, exc: Exception) -> Response:
    """
    ساخت پاسخ یکدست برای استثناهای شناخته‌شده DRF.

    ویژگی‌های حرفه‌ای:
    - اگر exception یک PermissionDenied با message سفارشی باشد
      (مثل IsFullyVerifiedUser)، همان message نمایش داده می‌شود.
    - اگر exception یک Throttled باشد، مدت زمان انتظار هم در message
      قرار می‌گیرد.
    - اگر exception یک ValidationError باشد، errors مستقیم از DRF
      استخراج می‌شود.

    Args:
        response: پاسخ DRF handler.
        exc: استثنای اصلی.

    Returns:
        Response با envelope استاندارد.
    """
    status_code = response.status_code
    message = _extract_message(exc, status_code)
    errors = _extract_errors(response, exc)

    response.data = {
        "success": False,
        "status_code": status_code,
        "message": message,
        "errors": errors,
    }
    return response


def _extract_message(exc: Exception, status_code: int) -> str:
    """
    استخراج بهترین message ممکن از exception.

    اولویت:
    1. اگر PermissionDenied با message سفارشی → همان message
    2. اگر Throttled → message با مدت زمان انتظار
    3. اگر exception.detail یک string باشد → همان
    4. fallback → پیام پیش‌فرض بر اساس status code

    Args:
        exc: استثنای اصلی.
        status_code: کد وضعیت HTTP.

    Returns:
        پیام فارسی مناسب.
    """
    if isinstance(exc, PermissionDenied) and hasattr(exc, "detail"):
        detail = exc.detail
        if isinstance(detail, str) and detail != PermissionDenied.default_detail:
            return detail

    if isinstance(exc, Throttled):
        wait = exc.wait
        if wait is not None:
            return f"تعداد درخواست‌ها بیش از حد مجاز است. لطفاً {int(wait)} ثانیه صبر کنید."
        return _DEFAULT_MESSAGES.get(status_code, "خطایی رخ داده است.")

    if hasattr(exc, "detail"):
        detail = exc.detail
        if isinstance(detail, str):
            return detail

    return _DEFAULT_MESSAGES.get(status_code, "خطایی رخ داده است.")


def _extract_errors(response: Response, exc: Exception) -> Any:
    """
    استخراج errors از response یا exception.

    منطق:
    - اگر ValidationError باشد، errors از response.data استخراج می‌شود
      (چون DRF آن را به dict/list تبدیل کرده).
    - برای بقیه، response.data مستقیم استفاده می‌شود.
    - اگر response.data فقط یک detail string باشد، آن را به dict می‌پیچیم.

    Args:
        response: پاسخ DRF handler.
        exc: استثنای اصلی.

    Returns:
        errors data مناسب.
    """
    data = response.data

    if isinstance(exc, ValidationError):
        return data

    if isinstance(data, dict) and "detail" in data and len(data) == 1:
        return data

    if isinstance(data, str):
        return {"detail": data}

    return data


# ============================================================
# Unhandled exceptions (500 errors)
# ============================================================


def _build_unhandled_response(
    exc: Exception,
    context: dict[str, Any],
) -> Response:
    """
    ساخت پاسخ برای استثناهای ناشناخته (500 errors).

    لاگ‌گذاری حرفه‌ای:
    - در DEBUG: traceback کامل.
    - در production: فقط exception type و exc_info=True
      (traceback در لاگ هست ولی در response نیست).

    Args:
        exc: استثنای ناشناخته.
        context: اطلاعات context.

    Returns:
        Response 500 با envelope استاندارد.
    """
    view = context.get("view")
    request = context.get("request")
    view_name = view.__class__.__name__ if view else "Unknown"
    method = getattr(request, "method", "?")
    path = getattr(request, "path", "?")

    if settings.DEBUG:
        logger.error(
            "Unhandled exception in %s [%s %s]: %s\n%s",
            view_name,
            method,
            path,
            exc,
            traceback.format_exc(),
        )
    else:
        logger.error(
            "Unhandled exception in %s [%s %s]: %s",
            view_name,
            method,
            path,
            type(exc).__name__,
            exc_info=True,
        )

    return Response(
        data={
            "success": False,
            "status_code": status.HTTP_500_INTERNAL_SERVER_ERROR,
            "message": _DEFAULT_MESSAGES[status.HTTP_500_INTERNAL_SERVER_ERROR],
            "errors": {"detail": "Internal server error."},
        },
        status=status.HTTP_500_INTERNAL_SERVER_ERROR,
    )

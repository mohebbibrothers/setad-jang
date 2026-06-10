"""
Audit Log Helpers.

توابع کمکی برای extract کردن metadata از request.

اصول طراحی:
- هر helper باید defensive باشد و در صورت نبود attribute خطا ندهد.
- extract_audit_metadata() خروجی‌ای می‌دهد که مستقیماً قابل unpack
  به log_action / log_action_async است.
- request_id اول از attribute ست‌شده توسط RequestIDMiddleware خوانده
  می‌شود و fallback به header مستقیم دارد.
"""

from __future__ import annotations

from rest_framework.request import Request


def get_client_ip(request: Request) -> str | None:
    """Extract client IP address from request headers."""
    x_forwarded_for = request.META.get("HTTP_X_FORWARDED_FOR")
    if x_forwarded_for:
        return x_forwarded_for.split(",")[0].strip()

    return request.META.get("REMOTE_ADDR")


def get_request_id(request: Request) -> str | None:
    """
    Extract request ID from request object.

    اول از request.request_id که توسط RequestIDMiddleware ست شده
    استفاده می‌کند. Fallback به header مستقیم برای compatibility.
    """
    request_id = getattr(request, "request_id", None)
    if request_id:
        return request_id

    return request.META.get("HTTP_X_REQUEST_ID") or request.META.get("X_REQUEST_ID")


def extract_audit_metadata(request: Request) -> dict[str, str | None]:
    """
    Extract تمام metadata لازم برای audit log از یک request.

    خروجی مستقیماً قابل unpack به ``log_action()`` و ``log_action_async()``
    است و از تکرار در view boundary جلوگیری می‌کند.
    """
    return {
        "ip_address": get_client_ip(request),
        "request_id": get_request_id(request),
    }

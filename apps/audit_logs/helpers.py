"""
Audit Log Helpers.

توابع کمکی برای extract کردن metadata از request.

اصول طراحی:
- هر helper باید defensive باشد و در صورت نبود attribute خطا ندهد.
- extract_audit_metadata() خروجی‌ای می‌دهد که مستقیماً قابل unpack
  به log_action / log_action_async است.
- request_id اول از attribute ست‌شده توسط RequestIDMiddleware خوانده
  می‌شود و fallback به header مستقیم دارد.
- metadata عملیاتی مثل IP، user-agent، path و method برای forensic tracing
  ثبت می‌شود، اما body/headerهای حساس هرگز وارد audit نمی‌شوند.
"""

from __future__ import annotations

from rest_framework.request import Request

from apps.core.client_ip import get_client_ip as resolve_client_ip

_MAX_USER_AGENT_LENGTH = 512
_MAX_PATH_LENGTH = 512


def get_client_ip(request: Request) -> str | None:
    """Extract client IP address, trusting X-Forwarded-For only per NUM_PROXIES.

    یافتهٔ P1 ممیزی: نسخهٔ قبلی ``X-Forwarded-For`` را بدون راستی‌آزمایی
    می‌پذیرفت (header ورودی، قابل جعل) و audit trail را با IP ساختگی
    آلوده می‌کرد. اکنون به ``apps.core.client_ip`` delegate می‌شود:
    NUM_PROXIES=0 (پیش‌فرض) → REMOTE_ADDR؛ زنجیرهٔ کوتاه/معیوب → fail-closed.
    """
    return resolve_client_ip(request)


def get_request_id(request: Request) -> str | None:
    """
    Extract request ID from request object.

    اول از request.request_id که توسط RequestIDMiddleware ست شده
    استفاده می‌کند. Fallback به header مستقیم برای compatibility.
    """
    request_id = getattr(request, "request_id", None)
    if request_id:
        return str(request_id)

    return request.META.get("HTTP_X_REQUEST_ID") or request.META.get("X_REQUEST_ID")


def get_user_agent(request: Request) -> str:
    """Extract and truncate User-Agent for safe persistence."""
    return str(request.META.get("HTTP_USER_AGENT", ""))[:_MAX_USER_AGENT_LENGTH]


def get_request_path(request: Request) -> str:
    """Extract and truncate request path for audit traceability."""
    return str(getattr(request, "path", ""))[:_MAX_PATH_LENGTH]


def get_request_method(request: Request) -> str:
    """Extract normalized HTTP method from request."""
    return str(getattr(request, "method", "")).upper()[:10]


def extract_audit_metadata(request: Request) -> dict[str, str | None]:
    """
    Extract تمام metadata لازم برای audit log از یک request.

    خروجی مستقیماً قابل unpack به ``log_action()`` و ``log_action_async()``
    است و از تکرار در view boundary جلوگیری می‌کند.
    """
    return {
        "ip_address": get_client_ip(request),
        "request_id": get_request_id(request),
        "user_agent": get_user_agent(request),
        "path": get_request_path(request),
        "method": get_request_method(request),
    }

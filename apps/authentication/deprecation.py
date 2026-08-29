"""
Deprecation helpers for legacy authentication endpoints.

هدف:
- افزودن headerهای deprecation به endpointهای legacy
- متمرکز کردن logهای مربوط به مصرف endpointهای قدیمی
- آماده‌سازی پروژه برای sunset controlled بدون breaking change ناگهانی
"""

from __future__ import annotations

import logging
from typing import Final

from decouple import config
from rest_framework.request import Request
from rest_framework.response import Response

from apps.core.client_ip import get_client_ip as resolve_client_ip

logger = logging.getLogger("apps.authentication")

DEPRECATION_HEADER: Final[str] = "Deprecation"
SUNSET_HEADER: Final[str] = "Sunset"
SUCCESSOR_LINK_HEADER: Final[str] = "Link"

LEGACY_AUTH_SUNSET: Final[str] = config(
    "AUTH_LEGACY_SUNSET",
    default="",
)


def build_deprecation_headers(*, successor: str | None = None) -> dict[str, str]:
    """
    Build standard deprecation headers for legacy auth endpoints.

    Notes:
    - Deprecation=true به‌صورت صریح اعلام می‌کند endpoint deprecated است.
    - اگر successor داده شود، با Link header معرفی می‌شود.
    - اگر sunset در env تنظیم شده باشد، در header اضافه می‌شود.
    """
    headers: dict[str, str] = {
        DEPRECATION_HEADER: "true",
    }

    if LEGACY_AUTH_SUNSET:
        headers[SUNSET_HEADER] = LEGACY_AUTH_SUNSET

    if successor:
        headers[SUCCESSOR_LINK_HEADER] = f'<{successor}>; rel="successor-version"'

    return headers


def add_deprecation_headers(
    response: Response,
    *,
    successor: str | None = None,
) -> Response:
    """
    Attach deprecation headers to a DRF Response instance.
    """
    for key, value in build_deprecation_headers(successor=successor).items():
        response[key] = value

    return response


def log_legacy_auth_usage(
    *,
    endpoint_name: str,
    request: Request,
    successor: str | None = None,
) -> None:
    """
    Log usage of a legacy auth endpoint for observability and migration tracking.
    """
    user = getattr(request, "user", None)
    user_id = getattr(user, "pk", None) if getattr(user, "is_authenticated", False) else None
    ip_address = resolve_client_ip(request)

    logger.warning(
        "Legacy auth endpoint used endpoint=%s user_id=%s ip=%s successor=%s",
        endpoint_name,
        user_id,
        ip_address,
        successor,
    )

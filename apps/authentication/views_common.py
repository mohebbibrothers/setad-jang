"""مشترکات views — constants/helpers که گروه‌های دامنه‌ای import می‌کنند.

با ابزار split_views در فاز ۱۱ از views.py جدا شد؛ منطق دست‌نخورده است(برشِ verbatim). facade در views.py همه را دوباره export می‌کند تا مسیرهایimport بیرونی (urls/tests) تغییر نکنند.
"""

from __future__ import annotations

from drf_spectacular.utils import (
    OpenApiParameter,
    OpenApiTypes,
    inline_serializer,
)
from rest_framework import serializers, status
from rest_framework.request import Request
from rest_framework.response import Response

from apps.core.responses import (
    ErrorResponse,
)
from apps.core.schemas import (
    build_error_response_serializer,
    build_paginated_success_response_serializer,
    build_success_response_serializer,
)

from .anti_abuse import is_global_otp_guard_tripped, is_honeypot_triggered
from .choices import UserRole
from .deprecation import add_deprecation_headers, log_legacy_auth_usage
from .otp import OTPCooldownActive, OTPDeliveryError
from .serializers import (
    AuthRiskSignalSerializer,
    AuthSessionSerializer,
    ProfileSerializer,
    UserAdminSerializer,
    UserMeSerializer,
)
from .services import (
    OTPServiceError,
)

# ============================================================
# Tag Constants
# ============================================================

TAG_AUTH_PUBLIC = "احراز هویت — عمومی"
TAG_AUTH_USER = "احراز هویت — کاربر"
TAG_AUTH_ADMIN = "احراز هویت — مدیریت"
# ============================================================
# Legacy deprecation successors
# ============================================================

LEGACY_REGISTER_SUCCESSOR = "/api/v1/auth/signup/request/"
LEGACY_VERIFY_EMAIL_SUCCESSOR = "/api/v1/auth/signup/verify/"
LEGACY_RESEND_VERIFICATION_SUCCESSOR = "/api/v1/auth/signup/request/"
LEGACY_LOGIN_SUCCESSOR = "/api/v1/auth/login/password/"
LEGACY_PASSWORD_FORGOT_SUCCESSOR = "/api/v1/auth/password/forgot/request/"
LEGACY_PASSWORD_RESET_SUCCESSOR = "/api/v1/auth/password/forgot/confirm/"
# ============================================================
# Swagger Response Schemas
# ============================================================

GENERIC_ERROR_RESPONSE = build_error_response_serializer(
    name="AuthenticationGenericErrorResponse",
)
EMPTY_SUCCESS_RESPONSE = build_success_response_serializer(
    name="AuthenticationEmptySuccessResponse",
)
REGISTER_RESPONSE_DATA = inline_serializer(
    name="RegisterResponseData",
    fields={
        "email": serializers.EmailField(),
    },
)
REGISTER_SUCCESS_RESPONSE = build_success_response_serializer(
    name="RegisterSuccessResponse",
    data_serializer=REGISTER_RESPONSE_DATA,
)
LOGIN_TOKENS_RESPONSE = inline_serializer(
    name="LoginTokensResponse",
    fields={
        "refresh": serializers.CharField(),
        "access": serializers.CharField(),
    },
)
LOGIN_RESPONSE_DATA = inline_serializer(
    name="LoginResponseData",
    fields={
        "user": UserMeSerializer(),
        "tokens": LOGIN_TOKENS_RESPONSE,
    },
)
LOGIN_SUCCESS_RESPONSE = build_success_response_serializer(
    name="LoginSuccessResponse",
    data_serializer=LOGIN_RESPONSE_DATA,
)
TOKEN_REFRESH_DATA = inline_serializer(
    name="TokenRefreshData",
    fields={
        "access": serializers.CharField(),
        "refresh": serializers.CharField(required=False),
    },
)
TOKEN_REFRESH_SUCCESS_RESPONSE = build_success_response_serializer(
    name="TokenRefreshSuccessResponse",
    data_serializer=TOKEN_REFRESH_DATA,
)
USER_ME_SUCCESS_RESPONSE = build_success_response_serializer(
    name="UserMeSuccessResponse",
    data_serializer=UserMeSerializer,
)
AUTH_SESSION_LIST_RESPONSE = build_paginated_success_response_serializer(
    name="AuthSessionListResponse",
    item_serializer=AuthSessionSerializer,
)
AUTH_SESSION_DETAIL_RESPONSE = build_success_response_serializer(
    name="AuthSessionDetailResponse",
    data_serializer=AuthSessionSerializer,
)
AUTH_RISK_SIGNAL_LIST_RESPONSE = build_paginated_success_response_serializer(
    name="AuthRiskSignalListResponse",
    item_serializer=AuthRiskSignalSerializer,
)
AUTH_RISK_SIGNAL_DETAIL_RESPONSE = build_success_response_serializer(
    name="AuthRiskSignalDetailResponse",
    data_serializer=AuthRiskSignalSerializer,
)
PROFILE_SUCCESS_RESPONSE = build_success_response_serializer(
    name="ProfileSuccessResponse",
    data_serializer=ProfileSerializer,
)
USER_ADMIN_SUCCESS_RESPONSE = build_success_response_serializer(
    name="UserAdminSuccessResponse",
    data_serializer=UserAdminSerializer,
)
USER_ADMIN_PAGINATED_SUCCESS_RESPONSE = build_paginated_success_response_serializer(
    name="UserAdminPaginatedSuccessResponse",
    item_serializer=UserAdminSerializer,
)
ADMIN_USER_LIST_PARAMETERS = [
    OpenApiParameter(
        name="page",
        type=OpenApiTypes.INT,
        location=OpenApiParameter.QUERY,
        description="شماره صفحه",
    ),
    OpenApiParameter(
        name="page_size",
        type=OpenApiTypes.INT,
        location=OpenApiParameter.QUERY,
        description="تعداد آیتم در هر صفحه (حداکثر ۱۰۰)",
    ),
    OpenApiParameter(
        name="email",
        type=OpenApiTypes.STR,
        location=OpenApiParameter.QUERY,
        description="فیلتر ایمیل با جستجوی icontains",
    ),
    OpenApiParameter(
        name="role",
        type=OpenApiTypes.STR,
        location=OpenApiParameter.QUERY,
        enum=[choice[0] for choice in UserRole.choices],
        description="فیلتر نقش کاربر",
    ),
    OpenApiParameter(
        name="is_active",
        type=OpenApiTypes.BOOL,
        location=OpenApiParameter.QUERY,
        description="فیلتر بر اساس فعال بودن کاربر",
    ),
    OpenApiParameter(
        name="is_email_verified",
        type=OpenApiTypes.BOOL,
        location=OpenApiParameter.QUERY,
        description="فیلتر بر اساس تأیید ایمیل",
    ),
]
# ============================================================
# Internal helpers
# ============================================================

_LEGACY_DESCRIPTION_FOOTER = (
    "\n\n---\n"
    "> ⚠️ **این endpoint منسوخ شده است** و در نسخه‌های آینده حذف خواهد شد.\n"
    "> لطفاً به نسخه جدید مهاجرت کنید."
)


def _build_honeypot_error_response() -> ErrorResponse:
    """Internal helper for views."""
    return ErrorResponse(
        message="درخواست نامعتبر است.",
        status_code=status.HTTP_400_BAD_REQUEST,
    )


def _build_global_otp_guard_error_response() -> ErrorResponse:
    """Internal helper for views."""
    return ErrorResponse(
        message="در حال حاضر امکان ارسال کد وجود ندارد. لطفاً کمی بعد تلاش کنید.",
        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
    )


def _check_honeypot(request: Request) -> ErrorResponse | None:
    """Internal helper for views."""
    if is_honeypot_triggered(request.data):
        return _build_honeypot_error_response()
    return None


def _check_global_otp_guard() -> ErrorResponse | None:
    """Internal helper for views."""
    if is_global_otp_guard_tripped():
        return _build_global_otp_guard_error_response()
    return None


def _otp_service_error_to_response(exc: OTPServiceError) -> ErrorResponse:
    """Internal helper for views."""
    status_code = status.HTTP_400_BAD_REQUEST

    if isinstance(exc.original, OTPCooldownActive):
        status_code = status.HTTP_429_TOO_MANY_REQUESTS
    elif isinstance(exc.original, OTPDeliveryError):
        status_code = status.HTTP_503_SERVICE_UNAVAILABLE

    return ErrorResponse(
        message=str(exc),
        status_code=status_code,
    )


def _mark_legacy_response(
    *,
    response: Response,
    request: Request,
    endpoint_name: str,
    successor: str | None,
) -> Response:
    """
    Add deprecation headers and log usage for legacy auth-v1 endpoints.
    """
    log_legacy_auth_usage(
        endpoint_name=endpoint_name,
        request=request,
        successor=successor,
    )
    return add_deprecation_headers(response, successor=successor)

"""
API views for authentication, identity management, and user administration.
"""

from __future__ import annotations

from typing import Any

from drf_spectacular.utils import (
    OpenApiParameter,
    OpenApiTypes,
    extend_schema,
    inline_serializer,
)
from rest_framework import serializers, status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.serializers import TokenRefreshSerializer
from rest_framework_simplejwt.views import TokenRefreshView

from apps.audit_logs import actions as audit_actions
from apps.audit_logs.helpers import extract_audit_metadata
from apps.audit_logs.services import log_action, log_action_async
from apps.core.pagination import StandardPagination
from apps.core.responses import (
    CreatedResponse,
    DeletedResponse,
    ErrorResponse,
    SuccessResponse,
)
from apps.core.schemas import (
    build_error_response_serializer,
    build_paginated_success_response_serializer,
    build_success_response_serializer,
)

from .anti_abuse import is_global_otp_guard_tripped, is_honeypot_triggered
from .choices import OTPPurpose, UserRole
from .deprecation import add_deprecation_headers, log_legacy_auth_usage
from .filters import UserAdminFilter
from .otp import OTPCooldownActive, OTPDeliveryError
from .permissions import IsAdminUser
from .selectors import (
    get_active_user_by_email,
    get_all_users_for_admin,
    get_user_auth_session_by_id,
    get_user_auth_sessions,
    get_user_by_email,
    get_user_by_id,
)
from .serializers import (
    AdminChangeRoleSerializer,
    AdminUserUpdateSerializer,
    AuthSessionSerializer,
    ChangePasswordSerializer,
    ForgotPasswordSerializer,
    IdentifierAddRequestSerializer,
    IdentifierAddVerifySerializer,
    IdentifierForgotPasswordConfirmSerializer,
    IdentifierForgotPasswordRequestSerializer,
    IdentifierMakePrimarySerializer,
    LoginPasswordSerializer,
    LoginSerializer,
    LogoutSerializer,
    OTPLoginRequestSerializer,
    OTPLoginVerifySerializer,
    ProfileSerializer,
    RefreshTokenInputSerializer,
    RegisterSerializer,
    ResendVerificationSerializer,
    ResetPasswordSerializer,
    SignupRequestSerializer,
    SignupVerifySerializer,
    UpdateMeSerializer,
    UpdateProfileSerializer,
    UserAdminSerializer,
    UserMeSerializer,
    VerifyEmailSerializer,
)
from .services import (
    AccountInactive,
    AccountNotVerified,
    IdentifierAlreadyExists,
    IdentifierAlreadyVerified,
    IdentifierChannelAlreadyOccupied,
    IdentifierNotAttached,
    IdentifierNotFound,
    IdentifierNotVerified,
    InvalidCredentials,
    OTPServiceError,
    admin_change_user_role,
    admin_update_user,
    change_password,
    create_and_send_otp,
    forgot_password_confirm,
    forgot_password_request,
    identifier_add_request,
    identifier_add_verify,
    login_otp_request,
    login_otp_verify,
    login_user,
    login_with_password,
    logout_user,
    make_primary_identifier,
    register_user,
    request_password_reset,
    reset_password_with_otp,
    revoke_all_user_sessions,
    revoke_auth_session,
    signup_request,
    signup_verify,
    update_profile,
    update_user_basic_info,
    verify_user_email,
)
from .throttles import (
    LoginThrottle,
    OTPGlobalIPThrottle,
    OTPRequestThrottle,
    OTPVerifyThrottle,
    PasswordResetThrottle,
    RegisterThrottle,
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


# ============================================================
# Phase H.1 — Multi-Identifier Public Auth (current API)
# ============================================================


class SignupRequestAPIView(APIView):
    """SignupRequestAPIView implementation for the authentication application."""
    permission_classes = [AllowAny]
    throttle_classes = [OTPRequestThrottle, OTPGlobalIPThrottle]

    @extend_schema(
        operation_id="auth_signup_request",
        tags=[TAG_AUTH_PUBLIC],
        summary="درخواست کد ثبت‌نام با شناسه",
        description=(
            "ارسال کد ثبت‌نام به ایمیل یا شماره موبایل.\n\n"
            "در این مرحله هنوز هیچ حساب کاربری‌ای ساخته نمی‌شود."
        ),
        request=SignupRequestSerializer,
        responses={
            200: EMPTY_SUCCESS_RESPONSE,
            400: GENERIC_ERROR_RESPONSE,
            429: GENERIC_ERROR_RESPONSE,
            503: GENERIC_ERROR_RESPONSE,
        },
    )
    def post(self, request: Request) -> SuccessResponse | ErrorResponse:
        honeypot_response = _check_honeypot(request)
        if honeypot_response is not None:
            return honeypot_response

        global_guard_response = _check_global_otp_guard()
        if global_guard_response is not None:
            return global_guard_response

        serializer = SignupRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        try:
            signup_request(
                identifier_kind=serializer.validated_data["identifier_kind"],
                identifier_value=serializer.validated_data["identifier"],
            )
        except OTPServiceError as exc:
            return _otp_service_error_to_response(exc)

        return SuccessResponse(message="کد ثبت‌نام با موفقیت ارسال شد.")


class SignupVerifyAPIView(APIView):
    """SignupVerifyAPIView implementation for the authentication application."""
    permission_classes = [AllowAny]
    throttle_classes = [OTPVerifyThrottle]

    @extend_schema(
        operation_id="auth_signup_verify",
        tags=[TAG_AUTH_PUBLIC],
        summary="تأیید ثبت‌نام و ساخت حساب",
        description="تأیید کد، ساخت حساب و دریافت JWT.",
        request=SignupVerifySerializer,
        responses={
            200: LOGIN_SUCCESS_RESPONSE,
            400: GENERIC_ERROR_RESPONSE,
            429: GENERIC_ERROR_RESPONSE,
        },
    )
    def post(self, request: Request) -> SuccessResponse | ErrorResponse:
        honeypot_response = _check_honeypot(request)
        if honeypot_response is not None:
            return honeypot_response

        serializer = SignupVerifySerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        try:
            result = signup_verify(
                identifier_kind=serializer.validated_data["identifier_kind"],
                identifier_value=serializer.validated_data["identifier"],
                code=serializer.validated_data["code"],
                password=serializer.validated_data["password"],
                first_name=serializer.validated_data.get("first_name", ""),
                last_name=serializer.validated_data.get("last_name", ""),
                request=request,
            )
        except IdentifierAlreadyExists:
            return ErrorResponse(message="این شناسه قبلاً ثبت شده است.")
        except OTPServiceError as exc:
            return _otp_service_error_to_response(exc)

        user = result["user"]
        metadata = extract_audit_metadata(request)
        log_action_async(
            user_id=user.pk,
            action=audit_actions.SIGNUP_COMPLETED,
            resource_type="user",
            resource_id=str(user.pk),
            extra_data={
                "identifier_kind": serializer.validated_data["identifier_kind"],
            },
            **metadata,
        )

        return SuccessResponse(
            data={
                "user": UserMeSerializer(result["user"]).data,
                "tokens": result["tokens"],
            },
            message="ثبت‌نام با موفقیت تکمیل شد.",
        )


class LoginPasswordAPIView(APIView):
    """LoginPasswordAPIView implementation for the authentication application."""
    permission_classes = [AllowAny]
    throttle_classes = [LoginThrottle]

    @extend_schema(
        operation_id="auth_login_password",
        tags=[TAG_AUTH_PUBLIC],
        summary="ورود با رمز عبور و شناسه",
        description="ورود با ایمیل یا شماره موبایل و رمز عبور.",
        request=LoginPasswordSerializer,
        responses={
            200: LOGIN_SUCCESS_RESPONSE,
            400: GENERIC_ERROR_RESPONSE,
            401: GENERIC_ERROR_RESPONSE,
            403: GENERIC_ERROR_RESPONSE,
        },
    )
    def post(self, request: Request) -> SuccessResponse | ErrorResponse:
        honeypot_response = _check_honeypot(request)
        if honeypot_response is not None:
            return honeypot_response

        serializer = LoginPasswordSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        identifier_kind = serializer.validated_data["identifier_kind"]
        identifier_value = serializer.validated_data["identifier"]
        metadata = extract_audit_metadata(request)

        try:
            result = login_with_password(
                identifier_kind=identifier_kind,
                identifier_value=identifier_value,
                password=serializer.validated_data["password"],
                request=request,
            )
        except (IdentifierNotFound, InvalidCredentials):
            log_action_async(
                user_id=None,
                action=audit_actions.LOGIN_FAILED,
                resource_type="user",
                resource_id=None,
                extra_data={
                    "identifier_kind": identifier_kind,
                    "reason": "invalid_credentials",
                },
                **metadata,
            )
            return ErrorResponse(
                message="شناسه یا رمز عبور اشتباه است.",
                status_code=status.HTTP_401_UNAUTHORIZED,
            )
        except AccountInactive:
            log_action_async(
                user_id=None,
                action=audit_actions.LOGIN_FAILED,
                resource_type="user",
                resource_id=None,
                extra_data={
                    "identifier_kind": identifier_kind,
                    "reason": "account_inactive",
                },
                **metadata,
            )
            return ErrorResponse(
                message="حساب کاربری غیرفعال است.",
                status_code=status.HTTP_403_FORBIDDEN,
            )
        except AccountNotVerified:
            log_action_async(
                user_id=None,
                action=audit_actions.LOGIN_FAILED,
                resource_type="user",
                resource_id=None,
                extra_data={
                    "identifier_kind": identifier_kind,
                    "reason": "account_not_verified",
                },
                **metadata,
            )
            return ErrorResponse(
                message="شناسه اصلی شما هنوز تأیید نشده است.",
                status_code=status.HTTP_403_FORBIDDEN,
            )

        user = result["user"]
        log_action_async(
            user_id=user.pk,
            action=audit_actions.LOGIN_SUCCESS,
            resource_type="user",
            resource_id=str(user.pk),
            extra_data={
                "identifier_kind": identifier_kind,
                "method": "password",
                "session_id": result["session"].pk,
            },
            **metadata,
        )

        return SuccessResponse(
            data={
                "user": UserMeSerializer(user).data,
                "tokens": result["tokens"],
            },
            message="ورود با موفقیت انجام شد.",
        )


class LoginOTPRequestAPIView(APIView):
    """LoginOTPRequestAPIView implementation for the authentication application."""
    permission_classes = [AllowAny]
    throttle_classes = [OTPRequestThrottle, OTPGlobalIPThrottle]

    @extend_schema(
        operation_id="auth_login_otp_request",
        tags=[TAG_AUTH_PUBLIC],
        summary="درخواست کد ورود با شناسه",
        description=(
            "ارسال کد ورود به ایمیل یا شماره موبایل.\n\n"
            "این endpoint enumeration-safe است."
        ),
        request=OTPLoginRequestSerializer,
        responses={
            200: EMPTY_SUCCESS_RESPONSE,
            400: GENERIC_ERROR_RESPONSE,
            429: GENERIC_ERROR_RESPONSE,
            503: GENERIC_ERROR_RESPONSE,
        },
    )
    def post(self, request: Request) -> SuccessResponse | ErrorResponse:
        honeypot_response = _check_honeypot(request)
        if honeypot_response is not None:
            return honeypot_response

        global_guard_response = _check_global_otp_guard()
        if global_guard_response is not None:
            return global_guard_response

        serializer = OTPLoginRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        try:
            login_otp_request(
                identifier_kind=serializer.validated_data["identifier_kind"],
                identifier_value=serializer.validated_data["identifier"],
            )
        except OTPServiceError as exc:
            return _otp_service_error_to_response(exc)

        return SuccessResponse(
            message="اگر حسابی با این شناسه وجود داشته باشد، کد ورود ارسال شد.",
        )


class LoginOTPVerifyAPIView(APIView):
    """LoginOTPVerifyAPIView implementation for the authentication application."""
    permission_classes = [AllowAny]
    throttle_classes = [OTPVerifyThrottle]

    @extend_schema(
        operation_id="auth_login_otp_verify",
        tags=[TAG_AUTH_PUBLIC],
        summary="تأیید کد ورود",
        description="تأیید کد ورود و دریافت JWT.",
        request=OTPLoginVerifySerializer,
        responses={
            200: LOGIN_SUCCESS_RESPONSE,
            400: GENERIC_ERROR_RESPONSE,
            403: GENERIC_ERROR_RESPONSE,
        },
    )
    def post(self, request: Request) -> SuccessResponse | ErrorResponse:
        honeypot_response = _check_honeypot(request)
        if honeypot_response is not None:
            return honeypot_response

        serializer = OTPLoginVerifySerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        identifier_kind = serializer.validated_data["identifier_kind"]
        identifier_value = serializer.validated_data["identifier"]
        metadata = extract_audit_metadata(request)

        try:
            result = login_otp_verify(
                identifier_kind=identifier_kind,
                identifier_value=identifier_value,
                code=serializer.validated_data["code"],
                request=request,
            )
        except OTPServiceError as exc:
            log_action_async(
                user_id=None,
                action=audit_actions.LOGIN_FAILED,
                resource_type="user",
                resource_id=None,
                extra_data={
                    "identifier_kind": identifier_kind,
                    "method": "otp",
                    "reason": "otp_error",
                },
                **metadata,
            )
            return _otp_service_error_to_response(exc)
        except IdentifierNotFound:
            log_action_async(
                user_id=None,
                action=audit_actions.LOGIN_FAILED,
                resource_type="user",
                resource_id=None,
                extra_data={
                    "identifier_kind": identifier_kind,
                    "method": "otp",
                    "reason": "identifier_not_found",
                },
                **metadata,
            )
            return ErrorResponse(message="کد یا شناسه نامعتبر است.")
        except AccountInactive:
            log_action_async(
                user_id=None,
                action=audit_actions.LOGIN_FAILED,
                resource_type="user",
                resource_id=None,
                extra_data={
                    "identifier_kind": identifier_kind,
                    "method": "otp",
                    "reason": "account_inactive",
                },
                **metadata,
            )
            return ErrorResponse(
                message="حساب کاربری غیرفعال است.",
                status_code=status.HTTP_403_FORBIDDEN,
            )
        except AccountNotVerified:
            log_action_async(
                user_id=None,
                action=audit_actions.LOGIN_FAILED,
                resource_type="user",
                resource_id=None,
                extra_data={
                    "identifier_kind": identifier_kind,
                    "method": "otp",
                    "reason": "account_not_verified",
                },
                **metadata,
            )
            return ErrorResponse(
                message="شناسه اصلی شما هنوز تأیید نشده است.",
                status_code=status.HTTP_403_FORBIDDEN,
            )

        user = result["user"]
        log_action_async(
            user_id=user.pk,
            action=audit_actions.LOGIN_SUCCESS,
            resource_type="user",
            resource_id=str(user.pk),
            extra_data={
                "identifier_kind": identifier_kind,
                "method": "otp",
            },
            **metadata,
        )

        return SuccessResponse(
            data={
                "user": UserMeSerializer(result["user"]).data,
                "tokens": result["tokens"],
            },
            message="ورود با موفقیت انجام شد.",
        )


class IdentifierForgotPasswordRequestAPIView(APIView):
    """IdentifierForgotPasswordRequestAPIView implementation for the authentication application."""
    permission_classes = [AllowAny]
    throttle_classes = [PasswordResetThrottle, OTPGlobalIPThrottle]

    @extend_schema(
        operation_id="auth_password_forgot_request_identifier",
        tags=[TAG_AUTH_PUBLIC],
        summary="درخواست بازیابی رمز با شناسه",
        description=(
            "ارسال کد بازیابی رمز عبور به ایمیل یا شماره موبایل.\n\n"
            "این endpoint enumeration-safe است."
        ),
        request=IdentifierForgotPasswordRequestSerializer,
        responses={
            200: EMPTY_SUCCESS_RESPONSE,
            400: GENERIC_ERROR_RESPONSE,
            429: GENERIC_ERROR_RESPONSE,
            503: GENERIC_ERROR_RESPONSE,
        },
    )
    def post(self, request: Request) -> SuccessResponse | ErrorResponse:
        honeypot_response = _check_honeypot(request)
        if honeypot_response is not None:
            return honeypot_response

        global_guard_response = _check_global_otp_guard()
        if global_guard_response is not None:
            return global_guard_response

        serializer = IdentifierForgotPasswordRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        try:
            forgot_password_request(
                identifier_kind=serializer.validated_data["identifier_kind"],
                identifier_value=serializer.validated_data["identifier"],
            )
        except OTPServiceError as exc:
            return _otp_service_error_to_response(exc)

        return SuccessResponse(
            message="اگر حسابی با این شناسه وجود داشته باشد، کد بازیابی ارسال شد.",
        )


class IdentifierForgotPasswordConfirmAPIView(APIView):
    """IdentifierForgotPasswordConfirmAPIView implementation for the authentication application."""
    permission_classes = [AllowAny]
    throttle_classes = [OTPVerifyThrottle]

    @extend_schema(
        operation_id="auth_password_forgot_confirm_identifier",
        tags=[TAG_AUTH_PUBLIC],
        summary="تأیید بازیابی رمز با شناسه",
        description="تنظیم رمز عبور جدید با شناسه، کد یکبارمصرف و رمز جدید.",
        request=IdentifierForgotPasswordConfirmSerializer,
        responses={
            200: EMPTY_SUCCESS_RESPONSE,
            400: GENERIC_ERROR_RESPONSE,
        },
    )
    def post(self, request: Request) -> SuccessResponse | ErrorResponse:
        honeypot_response = _check_honeypot(request)
        if honeypot_response is not None:
            return honeypot_response

        serializer = IdentifierForgotPasswordConfirmSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        try:
            forgot_password_confirm(
                identifier_kind=serializer.validated_data["identifier_kind"],
                identifier_value=serializer.validated_data["identifier"],
                code=serializer.validated_data["code"],
                new_password=serializer.validated_data["new_password"],
            )
        except OTPServiceError as exc:
            return _otp_service_error_to_response(exc)
        except IdentifierNotFound:
            return ErrorResponse(message="کد یا شناسه نامعتبر است.")

        metadata = extract_audit_metadata(request)
        log_action_async(
            user_id=None,
            action=audit_actions.PASSWORD_RESET_COMPLETED,
            resource_type="user",
            resource_id=None,
            extra_data={
                "identifier_kind": serializer.validated_data["identifier_kind"],
                "method": "otp_identifier",
            },
            **metadata,
        )

        return SuccessResponse(message="رمز عبور با موفقیت تغییر کرد.")


# ============================================================
# Phase H.2 — Authenticated Identifier Management
# ============================================================


class IdentifierAddRequestAPIView(APIView):
    """IdentifierAddRequestAPIView implementation for the authentication application."""
    permission_classes = [IsAuthenticated]
    throttle_classes = [OTPRequestThrottle, OTPGlobalIPThrottle]

    @extend_schema(
        operation_id="auth_identifier_add_request",
        tags=[TAG_AUTH_USER],
        summary="درخواست اتصال شناسه ثانویه",
        description=(
            "ارسال کد تأیید برای اتصال ایمیل یا شماره موبایل جدید به حساب.\n\n"
            "موارد پشتیبانی‌نشده: جایگزینی یک شناسه‌ی موجود در همان channel."
        ),
        request=IdentifierAddRequestSerializer,
        responses={
            200: EMPTY_SUCCESS_RESPONSE,
            400: GENERIC_ERROR_RESPONSE,
            401: GENERIC_ERROR_RESPONSE,
            429: GENERIC_ERROR_RESPONSE,
            503: GENERIC_ERROR_RESPONSE,
        },
    )
    def post(self, request: Request) -> SuccessResponse | ErrorResponse:
        honeypot_response = _check_honeypot(request)
        if honeypot_response is not None:
            return honeypot_response

        global_guard_response = _check_global_otp_guard()
        if global_guard_response is not None:
            return global_guard_response

        serializer = IdentifierAddRequestSerializer(
            data=request.data,
            context={"request": request},
        )
        serializer.is_valid(raise_exception=True)

        try:
            identifier_add_request(
                user=request.user,
                identifier_kind=serializer.validated_data["identifier_kind"],
                identifier_value=serializer.validated_data["identifier"],
            )
        except (
            IdentifierAlreadyVerified,
            IdentifierChannelAlreadyOccupied,
            IdentifierAlreadyExists,
        ) as exc:
            return ErrorResponse(message=str(exc))
        except OTPServiceError as exc:
            return _otp_service_error_to_response(exc)

        return SuccessResponse(message="کد تأیید ارسال شد.")


class IdentifierAddVerifyAPIView(APIView):
    """IdentifierAddVerifyAPIView implementation for the authentication application."""
    permission_classes = [IsAuthenticated]
    throttle_classes = [OTPVerifyThrottle]

    @extend_schema(
        operation_id="auth_identifier_add_verify",
        tags=[TAG_AUTH_USER],
        summary="تأیید اتصال شناسه ثانویه",
        description="تأیید کد و اتصال نهایی ایمیل یا شماره موبایل به حساب.",
        request=IdentifierAddVerifySerializer,
        responses={
            200: USER_ME_SUCCESS_RESPONSE,
            400: GENERIC_ERROR_RESPONSE,
            401: GENERIC_ERROR_RESPONSE,
        },
    )
    def post(self, request: Request) -> SuccessResponse | ErrorResponse:
        honeypot_response = _check_honeypot(request)
        if honeypot_response is not None:
            return honeypot_response

        serializer = IdentifierAddVerifySerializer(
            data=request.data,
            context={"request": request},
        )
        serializer.is_valid(raise_exception=True)

        try:
            user = identifier_add_verify(
                user=request.user,
                identifier_kind=serializer.validated_data["identifier_kind"],
                identifier_value=serializer.validated_data["identifier"],
                code=serializer.validated_data["code"],
            )
        except (
            IdentifierAlreadyVerified,
            IdentifierChannelAlreadyOccupied,
            IdentifierAlreadyExists,
        ) as exc:
            return ErrorResponse(message=str(exc))
        except OTPServiceError as exc:
            return _otp_service_error_to_response(exc)

        metadata = extract_audit_metadata(request)
        log_action_async(
            user_id=user.pk,
            action=audit_actions.IDENTIFIER_VERIFIED,
            resource_type="user",
            resource_id=str(user.pk),
            extra_data={
                "identifier_kind": serializer.validated_data["identifier_kind"],
            },
            **metadata,
        )

        return SuccessResponse(
            data=UserMeSerializer(user).data,
            message="شناسه با موفقیت به حساب شما متصل و تأیید شد.",
        )


class IdentifierMakePrimaryAPIView(APIView):
    """IdentifierMakePrimaryAPIView implementation for the authentication application."""
    permission_classes = [IsAuthenticated]

    @extend_schema(
        operation_id="auth_identifier_make_primary",
        tags=[TAG_AUTH_USER],
        summary="تغییر شناسه اصلی",
        description="تغییر شناسه اصلی حساب به یکی از شناسه‌های تأیید شده.",
        request=IdentifierMakePrimarySerializer,
        responses={
            200: USER_ME_SUCCESS_RESPONSE,
            400: GENERIC_ERROR_RESPONSE,
            401: GENERIC_ERROR_RESPONSE,
        },
    )
    def post(self, request: Request) -> SuccessResponse | ErrorResponse:
        serializer = IdentifierMakePrimarySerializer(
            data=request.data,
            context={"request": request},
        )
        serializer.is_valid(raise_exception=True)

        try:
            user = make_primary_identifier(
                user=request.user,
                identifier_kind=serializer.validated_data["identifier_kind"],
            )
        except IdentifierNotAttached as exc:
            return ErrorResponse(message=str(exc))
        except IdentifierNotVerified as exc:
            return ErrorResponse(message=str(exc))

        metadata = extract_audit_metadata(request)
        log_action_async(
            user_id=user.pk,
            action=audit_actions.PRIMARY_IDENTIFIER_CHANGED,
            resource_type="user",
            resource_id=str(user.pk),
            extra_data={
                "new_primary_kind": serializer.validated_data["identifier_kind"],
            },
            **metadata,
        )

        return SuccessResponse(
            data=UserMeSerializer(user).data,
            message="شناسه اصلی با موفقیت تغییر کرد.",
        )


# ============================================================
# Legacy Public: Register / Login / Verify
# ============================================================


class RegisterAPIView(APIView):
    """RegisterAPIView implementation for the authentication application."""
    permission_classes = [AllowAny]
    throttle_classes = [RegisterThrottle]

    @extend_schema(
        operation_id="auth_register",
        tags=[TAG_AUTH_PUBLIC],
        summary="[منسوخ] ثبت‌نام کاربر جدید",
        deprecated=True,
        description=(
            "ساخت حساب کاربری جدید با ایمیل و رمز عبور.\n\n"
            "پس از ثبت‌نام موفق، یک کد تأیید ۵ رقمی به ایمیل ارسال می‌شود."
            + _LEGACY_DESCRIPTION_FOOTER
        ),
        request=RegisterSerializer,
        responses={
            201: REGISTER_SUCCESS_RESPONSE,
            400: GENERIC_ERROR_RESPONSE,
        },
    )
    def post(self, request: Request) -> Response:
        serializer = RegisterSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        user = register_user(**serializer.validated_data)

        response = CreatedResponse(
            data={"email": user.email},
            message="ثبت‌نام انجام شد. کد تأیید به ایمیل شما ارسال شد.",
        )
        return _mark_legacy_response(
            response=response,
            request=request,
            endpoint_name="auth_register",
            successor=LEGACY_REGISTER_SUCCESSOR,
        )


class VerifyEmailAPIView(APIView):
    """VerifyEmailAPIView implementation for the authentication application."""
    permission_classes = [AllowAny]
    throttle_classes = [OTPRequestThrottle]

    @extend_schema(
        operation_id="auth_verify_email",
        tags=[TAG_AUTH_PUBLIC],
        summary="[منسوخ] تأیید ایمیل با کد",
        deprecated=True,
        description=(
            "تأیید ایمیل کاربر با ارسال کد ۵ رقمی دریافتی."
            + _LEGACY_DESCRIPTION_FOOTER
        ),
        request=VerifyEmailSerializer,
        responses={
            200: EMPTY_SUCCESS_RESPONSE,
            400: GENERIC_ERROR_RESPONSE,
            404: GENERIC_ERROR_RESPONSE,
        },
    )
    def post(self, request: Request) -> Response:
        serializer = VerifyEmailSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        user = get_user_by_email(serializer.validated_data["email"])
        if not user:
            response = ErrorResponse(
                message="کاربری با این ایمیل یافت نشد.",
                status_code=status.HTTP_404_NOT_FOUND,
            )
            return _mark_legacy_response(
                response=response,
                request=request,
                endpoint_name="auth_verify_email",
                successor=LEGACY_VERIFY_EMAIL_SUCCESSOR,
            )

        success = verify_user_email(user=user, code=serializer.validated_data["code"])
        if not success:
            response = ErrorResponse(message="کد نامعتبر یا منقضی شده است.")
            return _mark_legacy_response(
                response=response,
                request=request,
                endpoint_name="auth_verify_email",
                successor=LEGACY_VERIFY_EMAIL_SUCCESSOR,
            )

        response = SuccessResponse(message="ایمیل با موفقیت تأیید شد.")
        return _mark_legacy_response(
            response=response,
            request=request,
            endpoint_name="auth_verify_email",
            successor=LEGACY_VERIFY_EMAIL_SUCCESSOR,
        )


class ResendVerificationAPIView(APIView):
    """ResendVerificationAPIView implementation for the authentication application."""
    permission_classes = [AllowAny]
    throttle_classes = [OTPRequestThrottle]

    @extend_schema(
        operation_id="auth_resend_verification",
        tags=[TAG_AUTH_PUBLIC],
        summary="[منسوخ] ارسال مجدد کد تأیید ایمیل",
        deprecated=True,
        description=(
            "اگر کد قبلی منقضی شد، با این endpoint می‌توان کد جدیدی درخواست کرد."
            + _LEGACY_DESCRIPTION_FOOTER
        ),
        request=ResendVerificationSerializer,
        responses={
            200: EMPTY_SUCCESS_RESPONSE,
            400: GENERIC_ERROR_RESPONSE,
            404: GENERIC_ERROR_RESPONSE,
        },
    )
    def post(self, request: Request) -> Response:
        serializer = ResendVerificationSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        user = get_user_by_email(serializer.validated_data["email"])
        if not user:
            response = ErrorResponse(
                message="کاربری با این ایمیل یافت نشد.",
                status_code=status.HTTP_404_NOT_FOUND,
            )
            return _mark_legacy_response(
                response=response,
                request=request,
                endpoint_name="auth_resend_verification",
                successor=LEGACY_RESEND_VERIFICATION_SUCCESSOR,
            )

        if user.is_email_verified:
            response = ErrorResponse(message="ایمیل شما قبلاً تأیید شده است.")
            return _mark_legacy_response(
                response=response,
                request=request,
                endpoint_name="auth_resend_verification",
                successor=LEGACY_RESEND_VERIFICATION_SUCCESSOR,
            )

        create_and_send_otp(user=user, purpose=OTPPurpose.EMAIL_VERIFICATION)
        response = SuccessResponse(message="کد تأیید مجدداً ارسال شد.")
        return _mark_legacy_response(
            response=response,
            request=request,
            endpoint_name="auth_resend_verification",
            successor=LEGACY_RESEND_VERIFICATION_SUCCESSOR,
        )


class LoginAPIView(APIView):
    """LoginAPIView implementation for the authentication application."""
    permission_classes = [AllowAny]
    throttle_classes = [LoginThrottle]

    @extend_schema(
        operation_id="auth_login",
        tags=[TAG_AUTH_PUBLIC],
        summary="[منسوخ] ورود کاربر با ایمیل",
        deprecated=True,
        description=(
            "ورود با ایمیل و رمز عبور و دریافت توکن‌های JWT."
            + _LEGACY_DESCRIPTION_FOOTER
        ),
        request=LoginSerializer,
        responses={
            200: LOGIN_SUCCESS_RESPONSE,
            401: GENERIC_ERROR_RESPONSE,
            403: GENERIC_ERROR_RESPONSE,
        },
    )
    def post(self, request: Request) -> Response:
        serializer = LoginSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        metadata = extract_audit_metadata(request)

        result = login_user(
            request=request,
            email=serializer.validated_data["email"],
            password=serializer.validated_data["password"],
        )

        if not result:
            log_action_async(
                user_id=None,
                action=audit_actions.LOGIN_FAILED,
                resource_type="user",
                resource_id=None,
                extra_data={
                    "method": "legacy_email_password",
                    "reason": "invalid_credentials",
                },
                **metadata,
            )
            response = ErrorResponse(
                message="ایمیل یا رمز عبور اشتباه است.",
                status_code=status.HTTP_401_UNAUTHORIZED,
            )
            return _mark_legacy_response(
                response=response,
                request=request,
                endpoint_name="auth_login",
                successor=LEGACY_LOGIN_SUCCESSOR,
            )

        user = result["user"]
        if not user.is_email_verified:
            log_action_async(
                user_id=user.pk,
                action=audit_actions.LOGIN_FAILED,
                resource_type="user",
                resource_id=str(user.pk),
                extra_data={
                    "method": "legacy_email_password",
                    "reason": "email_not_verified",
                },
                **metadata,
            )
            response = ErrorResponse(
                message="ابتدا ایمیل خود را تأیید کنید.",
                status_code=status.HTTP_403_FORBIDDEN,
            )
            return _mark_legacy_response(
                response=response,
                request=request,
                endpoint_name="auth_login",
                successor=LEGACY_LOGIN_SUCCESSOR,
            )

        log_action_async(
            user_id=user.pk,
            action=audit_actions.LOGIN_SUCCESS,
            resource_type="user",
            resource_id=str(user.pk),
            extra_data={
                "method": "legacy_email_password",
            },
            **metadata,
        )

        response = SuccessResponse(
            data={
                "user": UserMeSerializer(user).data,
                "tokens": result["tokens"],
            },
            message="ورود با موفقیت انجام شد.",
        )
        return _mark_legacy_response(
            response=response,
            request=request,
            endpoint_name="auth_login",
            successor=LEGACY_LOGIN_SUCCESSOR,
        )


class CustomTokenRefreshView(TokenRefreshView):
    """CustomTokenRefreshView implementation for the authentication application."""
    permission_classes = [AllowAny]
    serializer_class = TokenRefreshSerializer

    @extend_schema(
        operation_id="auth_token_refresh",
        tags=[TAG_AUTH_PUBLIC],
        summary="بروزرسانی توکن JWT",
        description="دریافت access token جدید با استفاده از refresh token.",
        request=RefreshTokenInputSerializer,
        responses={
            200: TOKEN_REFRESH_SUCCESS_RESPONSE,
            401: GENERIC_ERROR_RESPONSE,
        },
    )
    def post(self, request: Request, *args: Any, **kwargs: Any) -> SuccessResponse:
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        token_data: dict[str, str] = dict(serializer.validated_data)

        return SuccessResponse(
            data=token_data,
            message="توکن با موفقیت بروزرسانی شد.",
        )


# ============================================================
# Password
# ============================================================


class ForgotPasswordAPIView(APIView):
    """ForgotPasswordAPIView implementation for the authentication application."""
    permission_classes = [AllowAny]
    throttle_classes = [PasswordResetThrottle]

    @extend_schema(
        operation_id="auth_password_forgot",
        tags=[TAG_AUTH_PUBLIC],
        summary="[منسوخ] درخواست بازیابی رمز عبور با ایمیل",
        deprecated=True,
        description=(
            "ارسال کد بازیابی به ایمیل کاربر.\n\n"
            "حتی اگر ایمیل وجود نداشته باشد، پاسخ موفقیت برگردانده می‌شود."
            + _LEGACY_DESCRIPTION_FOOTER
        ),
        request=ForgotPasswordSerializer,
        responses={
            200: EMPTY_SUCCESS_RESPONSE,
            400: GENERIC_ERROR_RESPONSE,
        },
    )
    def post(self, request: Request) -> Response:
        serializer = ForgotPasswordSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        user = get_active_user_by_email(serializer.validated_data["email"])
        if user:
            request_password_reset(user=user)

        response = SuccessResponse(
            message="در صورت وجود ایمیل، کد بازیابی ارسال شد.",
        )
        return _mark_legacy_response(
            response=response,
            request=request,
            endpoint_name="auth_password_forgot",
            successor=LEGACY_PASSWORD_FORGOT_SUCCESSOR,
        )


class ResetPasswordAPIView(APIView):
    """ResetPasswordAPIView implementation for the authentication application."""
    permission_classes = [AllowAny]
    throttle_classes = [PasswordResetThrottle]

    @extend_schema(
        operation_id="auth_password_reset",
        tags=[TAG_AUTH_PUBLIC],
        summary="[منسوخ] تنظیم رمز جدید با کد بازیابی",
        deprecated=True,
        description=(
            "تنظیم رمز عبور جدید با استفاده از کد ۵ رقمی دریافتی."
            + _LEGACY_DESCRIPTION_FOOTER
        ),
        request=ResetPasswordSerializer,
        responses={
            200: EMPTY_SUCCESS_RESPONSE,
            400: GENERIC_ERROR_RESPONSE,
        },
    )
    def post(self, request: Request) -> Response:
        serializer = ResetPasswordSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        metadata = extract_audit_metadata(request)

        user = get_active_user_by_email(serializer.validated_data["email"])
        if not user:
            response = ErrorResponse(message="کد یا ایمیل نامعتبر است.")
            return _mark_legacy_response(
                response=response,
                request=request,
                endpoint_name="auth_password_reset",
                successor=LEGACY_PASSWORD_RESET_SUCCESSOR,
            )

        success = reset_password_with_otp(
            user=user,
            code=serializer.validated_data["code"],
            new_password=serializer.validated_data["new_password"],
        )
        if not success:
            response = ErrorResponse(message="کد نامعتبر یا منقضی شده است.")
            return _mark_legacy_response(
                response=response,
                request=request,
                endpoint_name="auth_password_reset",
                successor=LEGACY_PASSWORD_RESET_SUCCESSOR,
            )

        log_action_async(
            user_id=user.pk,
            action=audit_actions.PASSWORD_RESET_COMPLETED,
            resource_type="user",
            resource_id=str(user.pk),
            extra_data={"method": "legacy_email_otp"},
            **metadata,
        )

        response = SuccessResponse(message="رمز عبور با موفقیت تغییر کرد.")
        return _mark_legacy_response(
            response=response,
            request=request,
            endpoint_name="auth_password_reset",
            successor=LEGACY_PASSWORD_RESET_SUCCESSOR,
        )


class ChangePasswordAPIView(APIView):
    """ChangePasswordAPIView implementation for the authentication application."""
    permission_classes = [IsAuthenticated]

    @extend_schema(
        operation_id="auth_password_change",
        tags=[TAG_AUTH_USER],
        summary="تغییر رمز عبور",
        description="تغییر رمز عبور توسط کاربر لاگین کرده با تأیید رمز فعلی.",
        request=ChangePasswordSerializer,
        responses={
            200: EMPTY_SUCCESS_RESPONSE,
            400: GENERIC_ERROR_RESPONSE,
            401: GENERIC_ERROR_RESPONSE,
        },
    )
    def post(self, request: Request) -> SuccessResponse | ErrorResponse:
        serializer = ChangePasswordSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        success = change_password(
            user=request.user,
            old_password=serializer.validated_data["old_password"],
            new_password=serializer.validated_data["new_password"],
        )
        if not success:
            return ErrorResponse(message="رمز فعلی اشتباه است.")

        metadata = extract_audit_metadata(request)
        log_action_async(
            user_id=request.user.pk,
            action=audit_actions.PASSWORD_CHANGED,
            resource_type="user",
            resource_id=str(request.user.pk),
            **metadata,
        )

        return SuccessResponse(message="رمز عبور با موفقیت تغییر کرد.")


# ============================================================
# Logout
# ============================================================


class LogoutAPIView(APIView):
    """LogoutAPIView implementation for the authentication application."""
    permission_classes = [IsAuthenticated]

    @extend_schema(
        operation_id="auth_logout",
        tags=[TAG_AUTH_USER],
        summary="خروج کاربر",
        description=(
            "خروج کاربر و invalidation refresh token.\n\n"
            "پس از logout، refresh token در blacklist قرار می‌گیرد."
        ),
        request=LogoutSerializer,
        responses={
            200: EMPTY_SUCCESS_RESPONSE,
            400: GENERIC_ERROR_RESPONSE,
            401: GENERIC_ERROR_RESPONSE,
        },
    )
    def post(self, request: Request) -> SuccessResponse | ErrorResponse:
        serializer = LogoutSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        user_id = request.user.pk
        success = logout_user(refresh_token=serializer.validated_data["refresh"])
        if not success:
            return ErrorResponse(message="توکن نامعتبر است.")

        metadata = extract_audit_metadata(request)
        log_action_async(
            user_id=user_id,
            action=audit_actions.LOGOUT,
            resource_type="user",
            resource_id=str(user_id),
            **metadata,
        )

        return SuccessResponse(message="با موفقیت خارج شدید.")


class AuthSessionListAPIView(APIView):
    """List current user's tracked auth sessions/devices."""

    permission_classes = [IsAuthenticated]
    pagination_class = StandardPagination

    @extend_schema(operation_id="auth_sessions_list", tags=[TAG_AUTH_USER], summary="لیست نشست‌ها و دستگاه‌های من", responses={200: AUTH_SESSION_LIST_RESPONSE, 401: GENERIC_ERROR_RESPONSE})
    def get(self, request: Request) -> Response:
        queryset = get_user_auth_sessions(user_id=request.user.pk)
        paginator = self.pagination_class()
        page = paginator.paginate_queryset(queryset, request, view=self)
        if page is not None:
            serializer = AuthSessionSerializer(page, many=True)
            return paginator.get_paginated_response(serializer.data, message="لیست نشست‌ها با موفقیت دریافت شد.")
        return SuccessResponse(data=AuthSessionSerializer(queryset, many=True).data, message="لیست نشست‌ها با موفقیت دریافت شد.")


class AuthSessionRevokeAPIView(APIView):
    """Revoke one current-user auth session with IDOR protection."""

    permission_classes = [IsAuthenticated]

    @extend_schema(operation_id="auth_sessions_revoke", tags=[TAG_AUTH_USER], summary="لغو یکی از نشست‌های من", request=None, responses={200: AUTH_SESSION_DETAIL_RESPONSE, 401: GENERIC_ERROR_RESPONSE, 404: GENERIC_ERROR_RESPONSE})
    def post(self, request: Request, session_id: int) -> Response:
        session = get_user_auth_session_by_id(user_id=request.user.pk, session_id=session_id)
        if session is None:
            return ErrorResponse(message="نشستی با این شناسه یافت نشد.", status_code=status.HTTP_404_NOT_FOUND)
        session = revoke_auth_session(session=session, revoked_by=request.user)
        metadata = extract_audit_metadata(request)
        log_action_async(user_id=request.user.pk, action=audit_actions.AUTH_SESSION_REVOKED, resource_type="auth_session", resource_id=str(session.pk), extra_data={"self_revoke": True}, **metadata)
        return SuccessResponse(data=AuthSessionSerializer(session).data, message="نشست با موفقیت لغو شد.")


class AdminUserSessionsListAPIView(APIView):
    """Admin list endpoint for a user's tracked sessions."""

    permission_classes = [IsAdminUser]
    pagination_class = StandardPagination

    @extend_schema(operation_id="auth_admin_user_sessions_list", tags=[TAG_AUTH_ADMIN], summary="لیست نشست‌های کاربر — ادمین", responses={200: AUTH_SESSION_LIST_RESPONSE, 403: GENERIC_ERROR_RESPONSE, 404: GENERIC_ERROR_RESPONSE})
    def get(self, request: Request, user_id: int) -> Response:
        user = get_user_by_id(user_id)
        if user is None:
            return ErrorResponse(message="کاربر یافت نشد.", status_code=status.HTTP_404_NOT_FOUND)
        queryset = get_user_auth_sessions(user_id=user.pk)
        paginator = self.pagination_class()
        page = paginator.paginate_queryset(queryset, request, view=self)
        if page is not None:
            serializer = AuthSessionSerializer(page, many=True)
            return paginator.get_paginated_response(serializer.data, message="لیست نشست‌های کاربر دریافت شد.")
        return SuccessResponse(data=AuthSessionSerializer(queryset, many=True).data, message="لیست نشست‌های کاربر دریافت شد.")


class AdminUserSessionsRevokeAPIView(APIView):
    """Admin endpoint to revoke all active sessions for one user."""

    permission_classes = [IsAdminUser]

    @extend_schema(operation_id="auth_admin_user_sessions_revoke_all", tags=[TAG_AUTH_ADMIN], summary="لغو همه نشست‌های کاربر — ادمین", request=None, responses={200: EMPTY_SUCCESS_RESPONSE, 403: GENERIC_ERROR_RESPONSE, 404: GENERIC_ERROR_RESPONSE})
    def post(self, request: Request, user_id: int) -> Response:
        user = get_user_by_id(user_id)
        if user is None:
            return ErrorResponse(message="کاربر یافت نشد.", status_code=status.HTTP_404_NOT_FOUND)
        revoked_count = revoke_all_user_sessions(user=user, revoked_by=request.user)
        metadata = extract_audit_metadata(request)
        log_action_async(user_id=request.user.pk, action=audit_actions.AUTH_USER_SESSIONS_REVOKED, resource_type="user", resource_id=str(user.pk), extra_data={"revoked_count": revoked_count}, **metadata)
        return SuccessResponse(data={"revoked_count": revoked_count}, message="نشست‌های کاربر با موفقیت لغو شد.")


# ============================================================
# Me (current user)
# ============================================================


class MeAPIView(APIView):
    """MeAPIView implementation for the authentication application."""
    permission_classes = [IsAuthenticated]

    @extend_schema(
        operation_id="auth_me_retrieve",
        tags=[TAG_AUTH_USER],
        summary="اطلاعات کاربر فعلی",
        description="دریافت اطلاعات پایه کاربر لاگین کرده.",
        responses={
            200: USER_ME_SUCCESS_RESPONSE,
            401: GENERIC_ERROR_RESPONSE,
        },
    )
    def get(self, request: Request) -> SuccessResponse:
        return SuccessResponse(
            data=UserMeSerializer(request.user).data,
            message="اطلاعات کاربر با موفقیت دریافت شد.",
        )

    @extend_schema(
        operation_id="auth_me_update",
        tags=[TAG_AUTH_USER],
        summary="ویرایش اطلاعات پایه کاربر",
        description="ویرایش اطلاعات پایه کاربر لاگین کرده مثل نام و نام خانوادگی.",
        request=UpdateMeSerializer,
        responses={
            200: USER_ME_SUCCESS_RESPONSE,
            400: GENERIC_ERROR_RESPONSE,
            401: GENERIC_ERROR_RESPONSE,
        },
    )
    def patch(self, request: Request) -> SuccessResponse:
        serializer = UpdateMeSerializer(data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)

        user = update_user_basic_info(user=request.user, **serializer.validated_data)
        return SuccessResponse(
            data=UserMeSerializer(user).data,
            message="اطلاعات با موفقیت بروزرسانی شد.",
        )


class ProfileAPIView(APIView):
    """ProfileAPIView implementation for the authentication application."""
    permission_classes = [IsAuthenticated]

    @extend_schema(
        operation_id="auth_profile_retrieve",
        tags=[TAG_AUTH_USER],
        summary="مشاهده پروفایل کاربر",
        description="دریافت اطلاعات تکمیلی پروفایل کاربر لاگین کرده.",
        responses={
            200: PROFILE_SUCCESS_RESPONSE,
            401: GENERIC_ERROR_RESPONSE,
        },
    )
    def get(self, request: Request) -> SuccessResponse:
        return SuccessResponse(
            data=ProfileSerializer(request.user.profile).data,
            message="پروفایل با موفقیت دریافت شد.",
        )

    @extend_schema(
        operation_id="auth_profile_update",
        tags=[TAG_AUTH_USER],
        summary="ویرایش پروفایل کاربر",
        description=(
            "ویرایش اطلاعات تکمیلی پروفایل کاربر لاگین کرده.\n\n"
            "تمام فیلدها optional هستند."
        ),
        request=UpdateProfileSerializer,
        responses={
            200: PROFILE_SUCCESS_RESPONSE,
            400: GENERIC_ERROR_RESPONSE,
            401: GENERIC_ERROR_RESPONSE,
        },
    )
    def patch(self, request: Request) -> SuccessResponse:
        serializer = UpdateProfileSerializer(data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)

        profile = update_profile(
            profile=request.user.profile,
            **serializer.validated_data,
        )
        return SuccessResponse(
            data=ProfileSerializer(profile).data,
            message="پروفایل با موفقیت بروزرسانی شد.",
        )


# ============================================================
# Admin
# ============================================================


class AdminUserListAPIView(APIView):
    """AdminUserListAPIView implementation for the authentication application."""
    permission_classes = [IsAdminUser]
    pagination_class = StandardPagination

    @extend_schema(
        operation_id="auth_admin_users_list",
        tags=[TAG_AUTH_ADMIN],
        summary="لیست کاربران",
        description=(
            "لیست تمام کاربران سیستم با pagination و قابلیت فیلتر.\n\n"
            "نیازمند احراز هویت با نقش admin."
        ),
        parameters=ADMIN_USER_LIST_PARAMETERS,
        responses={
            200: USER_ADMIN_PAGINATED_SUCCESS_RESPONSE,
            400: GENERIC_ERROR_RESPONSE,
            403: GENERIC_ERROR_RESPONSE,
        },
    )
    def get(self, request: Request) -> Response:
        queryset = get_all_users_for_admin()
        filterset = UserAdminFilter(request.query_params, queryset=queryset)

        if not filterset.is_valid():
            return ErrorResponse(
                errors=filterset.errors,
                message="فیلترهای ارسالی نامعتبر هستند.",
            )

        queryset = filterset.qs
        paginator = self.pagination_class()
        page = paginator.paginate_queryset(queryset, request, view=self)

        if page is not None:
            serializer = UserAdminSerializer(page, many=True)
            return paginator.get_paginated_response(
                serializer.data,
                message="لیست کاربران با موفقیت دریافت شد.",
            )

        return SuccessResponse(
            data=UserAdminSerializer(queryset, many=True).data,
            message="لیست کاربران با موفقیت دریافت شد.",
        )


class AdminUserDetailAPIView(APIView):
    """AdminUserDetailAPIView implementation for the authentication application."""
    permission_classes = [IsAdminUser]

    @extend_schema(
        operation_id="auth_admin_user_retrieve",
        tags=[TAG_AUTH_ADMIN],
        summary="جزئیات کاربر",
        description="دریافت اطلاعات کامل یک کاربر شامل پروفایل و وضعیت.",
        responses={
            200: USER_ADMIN_SUCCESS_RESPONSE,
            403: GENERIC_ERROR_RESPONSE,
            404: GENERIC_ERROR_RESPONSE,
        },
    )
    def get(self, request: Request, user_id: int) -> SuccessResponse | ErrorResponse:
        user = get_user_by_id(user_id)
        if not user:
            return ErrorResponse(
                message="کاربر یافت نشد.",
                status_code=status.HTTP_404_NOT_FOUND,
            )

        return SuccessResponse(
            data=UserAdminSerializer(user).data,
            message="جزئیات کاربر با موفقیت دریافت شد.",
        )

    @extend_schema(
        operation_id="auth_admin_user_update",
        tags=[TAG_AUTH_ADMIN],
        summary="ویرایش کاربر",
        description="ویرایش اطلاعات یک کاربر توسط ادمین.",
        request=AdminUserUpdateSerializer,
        responses={
            200: USER_ADMIN_SUCCESS_RESPONSE,
            400: GENERIC_ERROR_RESPONSE,
            403: GENERIC_ERROR_RESPONSE,
            404: GENERIC_ERROR_RESPONSE,
        },
    )
    def patch(self, request: Request, user_id: int) -> SuccessResponse | ErrorResponse:
        user = get_user_by_id(user_id)
        if not user:
            return ErrorResponse(
                message="کاربر یافت نشد.",
                status_code=status.HTTP_404_NOT_FOUND,
            )

        serializer = AdminUserUpdateSerializer(data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)

        old_is_active = user.is_active
        user = admin_update_user(user=user, **serializer.validated_data)

        metadata = extract_audit_metadata(request)

        # اگر کاربر deactivate شده، event مخصوص ثبت می‌کنیم
        if "is_active" in serializer.validated_data and not user.is_active and old_is_active:
            log_action_async(
                user_id=request.user.pk,
                action=audit_actions.ADMIN_USER_DEACTIVATED,
                resource_type="user",
                resource_id=str(user.pk),
                changes={
                    "is_active": {"before": True, "after": False},
                },
                **metadata,
            )
        else:
            log_action_async(
                user_id=request.user.pk,
                action=audit_actions.ADMIN_USER_UPDATED,
                resource_type="user",
                resource_id=str(user.pk),
                changes={
                    field: serializer.validated_data[field]
                    for field in serializer.validated_data
                },
                **metadata,
            )

        return SuccessResponse(
            data=UserAdminSerializer(user).data,
            message="کاربر با موفقیت بروزرسانی شد.",
        )

    @extend_schema(
        operation_id="auth_admin_user_delete",
        tags=[TAG_AUTH_ADMIN],
        summary="غیرفعال کردن کاربر",
        description="غیرفعال کردن (soft delete) یک کاربر توسط ادمین.",
        responses={
            200: EMPTY_SUCCESS_RESPONSE,
            403: GENERIC_ERROR_RESPONSE,
            404: GENERIC_ERROR_RESPONSE,
        },
    )
    def delete(self, request: Request, user_id: int) -> DeletedResponse | ErrorResponse:
        user = get_user_by_id(user_id)
        if not user:
            return ErrorResponse(
                message="کاربر یافت نشد.",
                status_code=status.HTTP_404_NOT_FOUND,
            )

        user.soft_delete()

        # Admin deactivation — sync چون compliance-critical است
        metadata = extract_audit_metadata(request)
        log_action(
            user_id=request.user.pk,
            action=audit_actions.ADMIN_USER_DEACTIVATED,
            resource_type="user",
            resource_id=str(user_id),
            changes={"is_active": {"before": True, "after": False}},
            **metadata,
        )

        return DeletedResponse(message="کاربر با موفقیت غیرفعال شد.")


class AdminChangeUserRoleAPIView(APIView):
    """AdminChangeUserRoleAPIView implementation for the authentication application."""
    permission_classes = [IsAdminUser]

    @extend_schema(
        operation_id="auth_admin_user_change_role",
        tags=[TAG_AUTH_ADMIN],
        summary="تغییر نقش کاربر",
        description=(
            "تغییر نقش یک کاربر توسط ادمین.\n\n"
            "**نقش‌های موجود:**\n"
            "- `user`: کاربر عادی\n"
            "- `admin`: مدیر سیستم"
        ),
        request=AdminChangeRoleSerializer,
        responses={
            200: USER_ADMIN_SUCCESS_RESPONSE,
            400: GENERIC_ERROR_RESPONSE,
            403: GENERIC_ERROR_RESPONSE,
            404: GENERIC_ERROR_RESPONSE,
        },
    )
    def post(self, request: Request, user_id: int) -> SuccessResponse | ErrorResponse:
        user = get_user_by_id(user_id)
        if not user:
            return ErrorResponse(
                message="کاربر یافت نشد.",
                status_code=status.HTTP_404_NOT_FOUND,
            )

        serializer = AdminChangeRoleSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        old_role = user.role
        user = admin_change_user_role(
            user=user,
            role=serializer.validated_data["role"],
        )

        # Role change — sync چون privilege escalation است
        metadata = extract_audit_metadata(request)
        log_action(
            user_id=request.user.pk,
            action=audit_actions.ADMIN_USER_ROLE_CHANGED,
            resource_type="user",
            resource_id=str(user.pk),
            changes={
                "role": {"before": old_role, "after": user.role},
            },
            **metadata,
        )

        return SuccessResponse(
            data=UserAdminSerializer(user).data,
            message="نقش کاربر با موفقیت تغییر کرد.",
        )

"""گروه دامنه‌ای `views_legacy` از views — فاز ۱۱ (تفکیک P3-16).

کلاس‌ها عیناً منتقل شده‌اند؛ مشترکات از views_common؛ نامِ عمومیِ این گروه‌ها را فقط از facade (apps.*.views) یا همین ماژول import کنید.
"""

from __future__ import annotations

from typing import Any

from drf_spectacular.utils import (
    extend_schema,
)
from rest_framework import status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.views import TokenRefreshView

from apps.audit_logs import actions as audit_actions
from apps.audit_logs.helpers import extract_audit_metadata
from apps.audit_logs.services import log_action_async
from apps.core.responses import (
    CreatedResponse,
    ErrorResponse,
    SuccessResponse,
)

from .choices import OTPPurpose
from .selectors import (
    get_user_by_email,
)
from .serializers import (
    LoginSerializer,
    LogoutSerializer,
    RefreshTokenInputSerializer,
    RegisterSerializer,
    ResendVerificationSerializer,
    SessionAwareTokenRefreshSerializer,
    UserMeSerializer,
    VerifyEmailSerializer,
)
from .services import (
    create_and_send_otp,
    login_user,
    logout_user,
    register_user,
    verify_user_email,
)
from .throttles import (
    LoginThrottle,
    OTPGlobalIPThrottle,
    OTPRequestThrottle,
    OTPTargetThrottle,
    RegisterThrottle,
    TokenRefreshThrottle,
)
from .views_common import (  # noqa: F401 — re-exportِ رایگان برای بدنه‌های منتقل‌شده
    _LEGACY_DESCRIPTION_FOOTER,
    ADMIN_USER_LIST_PARAMETERS,
    AUTH_RISK_SIGNAL_DETAIL_RESPONSE,
    AUTH_RISK_SIGNAL_LIST_RESPONSE,
    AUTH_SESSION_DETAIL_RESPONSE,
    AUTH_SESSION_LIST_RESPONSE,
    EMPTY_SUCCESS_RESPONSE,
    GENERIC_ERROR_RESPONSE,
    LEGACY_LOGIN_SUCCESSOR,
    LEGACY_PASSWORD_FORGOT_SUCCESSOR,
    LEGACY_PASSWORD_RESET_SUCCESSOR,
    LEGACY_REGISTER_SUCCESSOR,
    LEGACY_RESEND_VERIFICATION_SUCCESSOR,
    LEGACY_VERIFY_EMAIL_SUCCESSOR,
    LOGIN_RESPONSE_DATA,
    LOGIN_SUCCESS_RESPONSE,
    LOGIN_TOKENS_RESPONSE,
    PROFILE_SUCCESS_RESPONSE,
    REGISTER_RESPONSE_DATA,
    REGISTER_SUCCESS_RESPONSE,
    TAG_AUTH_ADMIN,
    TAG_AUTH_PUBLIC,
    TAG_AUTH_USER,
    TOKEN_REFRESH_DATA,
    TOKEN_REFRESH_SUCCESS_RESPONSE,
    USER_ADMIN_PAGINATED_SUCCESS_RESPONSE,
    USER_ADMIN_SUCCESS_RESPONSE,
    USER_ME_SUCCESS_RESPONSE,
    _build_global_otp_guard_error_response,
    _build_honeypot_error_response,
    _check_global_otp_guard,
    _check_honeypot,
    _mark_legacy_response,
    _otp_service_error_to_response,
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
            "پس از ثبت‌نام موفق، یک کد تأیید یکبارمصرف به ایمیل ارسال می‌شود."
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
    throttle_classes = [OTPRequestThrottle, OTPGlobalIPThrottle]

    @extend_schema(
        operation_id="auth_verify_email",
        tags=[TAG_AUTH_PUBLIC],
        summary="[منسوخ] تأیید ایمیل با کد",
        deprecated=True,
        description=(
            "تأیید ایمیل کاربر با ارسال کد یکبارمصرف دریافتی." + _LEGACY_DESCRIPTION_FOOTER
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
    throttle_classes = [OTPRequestThrottle, OTPGlobalIPThrottle, OTPTargetThrottle]

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
        description=("ورود با ایمیل و رمز عبور و دریافت توکن‌های JWT." + _LEGACY_DESCRIPTION_FOOTER),
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
    # یافتهٔ ممیزی ۵.۱: هر رفرش یک ردیف blacklist می‌سازد → throttle per-IP.
    throttle_classes = [TokenRefreshThrottle]
    serializer_class = SessionAwareTokenRefreshSerializer

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

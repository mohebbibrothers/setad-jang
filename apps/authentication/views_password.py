"""گروه دامنه‌ای `views_password` از views — فاز ۱۱ (تفکیک P3-16).

کلاس‌ها عیناً منتقل شده‌اند؛ مشترکات از views_common؛ نامِ عمومیِ این گروه‌ها را فقط از facade (apps.*.views) یا همین ماژول import کنید.
"""

from __future__ import annotations

from drf_spectacular.utils import (
    extend_schema,
)
from rest_framework import status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.audit_logs import actions as audit_actions
from apps.audit_logs.helpers import extract_audit_metadata
from apps.audit_logs.services import log_action_async
from apps.core.responses import (
    ErrorResponse,
    SuccessResponse,
)

from .constants import SESSION_ID_CLAIM
from .selectors import (
    get_active_user_by_email,
)
from .serializers import (
    ChangePasswordSerializer,
    ForgotPasswordSerializer,
    IdentifierForgotPasswordConfirmSerializer,
    IdentifierForgotPasswordRequestSerializer,
    LoginPasswordSerializer,
    ResetPasswordSerializer,
    UserMeSerializer,
)
from .services import (
    AccountInactive,
    AccountNotVerified,
    IdentifierNotFound,
    InvalidCredentials,
    OTPServiceError,
    change_password,
    forgot_password_confirm,
    forgot_password_request,
    login_with_password,
    request_password_reset,
    reset_password_with_otp,
)
from .throttles import (
    LoginThrottle,
    OTPGlobalIPThrottle,
    OTPTargetThrottle,
    OTPVerifyThrottle,
    PasswordResetThrottle,
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


class IdentifierForgotPasswordRequestAPIView(APIView):
    """IdentifierForgotPasswordRequestAPIView implementation for the authentication application."""

    permission_classes = [AllowAny]
    throttle_classes = [PasswordResetThrottle, OTPGlobalIPThrottle, OTPTargetThrottle]

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
        description=(
            "تنظیم رمز عبور جدید با شناسه، کد یکبارمصرف و رمز جدید.\n\n"
            "**پس از ریست، تمام نشست‌های فعال این کاربر لغو می‌شوند** — "
            "اگر حسابی به‌سرقت رفته باشد، ریست رمز مهاجم را هم بیرون می‌کند."
        ),
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
# Password
# ============================================================


class ForgotPasswordAPIView(APIView):
    """ForgotPasswordAPIView implementation for the authentication application."""

    permission_classes = [AllowAny]
    throttle_classes = [PasswordResetThrottle, OTPGlobalIPThrottle, OTPTargetThrottle]

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
    throttle_classes = [PasswordResetThrottle, OTPGlobalIPThrottle]

    @extend_schema(
        operation_id="auth_password_reset",
        tags=[TAG_AUTH_PUBLIC],
        summary="[منسوخ] تنظیم رمز جدید با کد بازیابی",
        deprecated=True,
        description=(
            "تنظیم رمز عبور جدید با استفاده از کد یکبارمصرف دریافتی." + _LEGACY_DESCRIPTION_FOOTER
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
        description=(
            "تغییر رمز عبور توسط کاربر لاگین کرده با تأیید رمز فعلی.\n\n"
            "**همزمان، تمام نشست‌های دیگر (دستگاه‌های دیگر) لغو می‌شوند** — "
            "الگوی استاندارد امنیتی. نشست همین دستگاه دست‌نخورده می‌ماند."
        ),
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

        # نشست جاری از claim «sid» روی همان توکنِ احراز هویت‌کنندهٔ درخواست
        # خوانده می‌شود تا هنگام لغو جمعی، از کاربرِ روی همین دستگاه بیرون
        # انداخته نشود (request.auth توسط SessionAwareJWTAuthentication پر شده).
        keep_session_sid: int | None = None
        auth_token = getattr(request, "auth", None)
        if auth_token is not None:
            raw_sid = auth_token.get(SESSION_ID_CLAIM)
            if isinstance(raw_sid, int):
                keep_session_sid = raw_sid

        success = change_password(
            user=request.user,
            old_password=serializer.validated_data["old_password"],
            new_password=serializer.validated_data["new_password"],
            keep_session_sid=keep_session_sid,
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

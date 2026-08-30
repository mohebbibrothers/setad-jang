"""گروه دامنه‌ای `views_signup` از views — فاز ۱۱ (تفکیک P3-16).

کلاس‌ها عیناً منتقل شده‌اند؛ مشترکات از views_common؛ نامِ عمومیِ این گروه‌ها را فقط از facade (apps.*.views) یا همین ماژول import کنید.
"""

from __future__ import annotations

from drf_spectacular.utils import (
    extend_schema,
)
from rest_framework.permissions import AllowAny
from rest_framework.request import Request
from rest_framework.views import APIView

from apps.audit_logs import actions as audit_actions
from apps.audit_logs.helpers import extract_audit_metadata
from apps.audit_logs.services import log_action_async
from apps.core.responses import (
    ErrorResponse,
    SuccessResponse,
)

from .serializers import (
    SignupRequestSerializer,
    SignupVerifySerializer,
    UserMeSerializer,
)
from .services import (
    IdentifierAlreadyExists,
    OTPServiceError,
    signup_request,
    signup_verify,
)
from .throttles import (
    OTPGlobalIPThrottle,
    OTPRequestThrottle,
    OTPTargetThrottle,
    OTPVerifyThrottle,
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
# Phase H.1 — Multi-Identifier Public Auth (current API)
# ============================================================


class SignupRequestAPIView(APIView):
    """SignupRequestAPIView implementation for the authentication application."""

    permission_classes = [AllowAny]
    throttle_classes = [OTPRequestThrottle, OTPGlobalIPThrottle, OTPTargetThrottle]

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

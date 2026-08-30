"""گروه دامنه‌ای `views_identifiers` از views — فاز ۱۱ (تفکیک P3-16).

کلاس‌ها عیناً منتقل شده‌اند؛ مشترکات از views_common؛ نامِ عمومیِ این گروه‌ها را فقط از facade (apps.*.views) یا همین ماژول import کنید.
"""

from __future__ import annotations

from drf_spectacular.utils import (
    extend_schema,
)
from rest_framework.permissions import IsAuthenticated
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
    IdentifierAddRequestSerializer,
    IdentifierAddVerifySerializer,
    IdentifierMakePrimarySerializer,
    UserMeSerializer,
)
from .services import (
    IdentifierAlreadyExists,
    IdentifierAlreadyVerified,
    IdentifierChannelAlreadyOccupied,
    IdentifierNotAttached,
    IdentifierNotVerified,
    OTPServiceError,
    identifier_add_request,
    identifier_add_verify,
    make_primary_identifier,
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
# Phase H.2 — Authenticated Identifier Management
# ============================================================


class IdentifierAddRequestAPIView(APIView):
    """IdentifierAddRequestAPIView implementation for the authentication application."""

    permission_classes = [IsAuthenticated]
    throttle_classes = [OTPRequestThrottle, OTPGlobalIPThrottle, OTPTargetThrottle]

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

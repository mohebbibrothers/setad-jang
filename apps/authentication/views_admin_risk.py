"""گروه دامنه‌ای `views_admin_risk` از views — فاز ۱۱ (تفکیک P3-16).

کلاس‌ها عیناً منتقل شده‌اند؛ مشترکات از views_common؛ نامِ عمومیِ این گروه‌ها را فقط از facade (apps.*.views) یا همین ماژول import کنید.
"""

from __future__ import annotations

from drf_spectacular.utils import (
    extend_schema,
)
from rest_framework import status
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.audit_logs import actions as audit_actions
from apps.audit_logs.helpers import extract_audit_metadata
from apps.audit_logs.services import log_action_async
from apps.core.pagination import StandardPagination
from apps.core.responses import (
    ErrorResponse,
    SuccessResponse,
)

from .permissions import IsAdminUser
from .selectors import (
    get_admin_auth_risk_signal_by_id,
    get_admin_auth_risk_signals,
)
from .serializers import (
    AuthRiskSignalReviewSerializer,
    AuthRiskSignalSerializer,
)
from .services import (
    review_auth_risk_signal,
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


class AdminAuthRiskSignalListAPIView(APIView):
    """Admin list endpoint for authentication risk signals."""

    permission_classes = [IsAdminUser]
    pagination_class = StandardPagination

    @extend_schema(
        operation_id="auth_admin_risk_signals_list",
        tags=[TAG_AUTH_ADMIN],
        summary="لیست سیگنال‌های ریسک احراز هویت",
        responses={200: AUTH_RISK_SIGNAL_LIST_RESPONSE, 403: GENERIC_ERROR_RESPONSE},
    )
    def get(self, request: Request) -> Response:
        queryset = get_admin_auth_risk_signals()
        status_filter = request.query_params.get("status")
        if status_filter:
            queryset = queryset.filter(status=status_filter)
        severity_filter = request.query_params.get("severity")
        if severity_filter:
            queryset = queryset.filter(severity=severity_filter)
        paginator = self.pagination_class()
        page = paginator.paginate_queryset(queryset, request, view=self)
        if page is not None:
            serializer = AuthRiskSignalSerializer(page, many=True)
            return paginator.get_paginated_response(
                serializer.data, message="لیست سیگنال‌های ریسک دریافت شد."
            )
        return SuccessResponse(
            data=AuthRiskSignalSerializer(queryset, many=True).data,
            message="لیست سیگنال‌های ریسک دریافت شد.",
        )


class AdminAuthRiskSignalReviewAPIView(APIView):
    """Admin endpoint to review/dismiss/escalate an authentication risk signal."""

    permission_classes = [IsAdminUser]

    @extend_schema(
        operation_id="auth_admin_risk_signal_review",
        tags=[TAG_AUTH_ADMIN],
        summary="بررسی سیگنال ریسک احراز هویت",
        request=AuthRiskSignalReviewSerializer,
        responses={
            200: AUTH_RISK_SIGNAL_DETAIL_RESPONSE,
            400: GENERIC_ERROR_RESPONSE,
            403: GENERIC_ERROR_RESPONSE,
            404: GENERIC_ERROR_RESPONSE,
        },
    )
    def post(self, request: Request, signal_id: int) -> Response:
        signal = get_admin_auth_risk_signal_by_id(signal_id=signal_id)
        if signal is None:
            return ErrorResponse(
                message="سیگنال ریسکی با این شناسه یافت نشد.", status_code=status.HTTP_404_NOT_FOUND
            )
        serializer = AuthRiskSignalReviewSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            signal = review_auth_risk_signal(
                signal=signal,
                reviewed_by=request.user,
                status=serializer.validated_data["status"],
                review_note=serializer.validated_data.get("review_note", ""),
            )
        except Exception as exc:
            return ErrorResponse(message=str(exc))
        metadata = extract_audit_metadata(request)
        log_action_async(
            user_id=request.user.pk,
            action=audit_actions.AUTH_RISK_SIGNAL_REVIEWED,
            resource_type="auth_risk_signal",
            resource_id=str(signal.pk),
            extra_data={"status": signal.status, "signal_type": signal.signal_type},
            **metadata,
        )
        return SuccessResponse(
            data=AuthRiskSignalSerializer(signal).data, message="سیگنال ریسک بررسی شد."
        )

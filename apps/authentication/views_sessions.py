"""گروه دامنه‌ای `views_sessions` از views — فاز ۱۱ (تفکیک P3-16).

کلاس‌ها عیناً منتقل شده‌اند؛ مشترکات از views_common؛ نامِ عمومیِ این گروه‌ها را فقط از facade (apps.*.views) یا همین ماژول import کنید.
"""

from __future__ import annotations

from drf_spectacular.utils import (
    extend_schema,
)
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
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
    get_user_auth_session_by_id,
    get_user_auth_sessions,
    get_user_by_id,
)
from .serializers import (
    AuthSessionSerializer,
)
from .services import (
    revoke_all_user_sessions,
    revoke_auth_session,
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


class AuthSessionListAPIView(APIView):
    """List current user's tracked auth sessions/devices."""

    permission_classes = [IsAuthenticated]
    pagination_class = StandardPagination

    @extend_schema(
        operation_id="auth_sessions_list",
        tags=[TAG_AUTH_USER],
        summary="لیست نشست‌ها و دستگاه‌های من",
        responses={200: AUTH_SESSION_LIST_RESPONSE, 401: GENERIC_ERROR_RESPONSE},
    )
    def get(self, request: Request) -> Response:
        queryset = get_user_auth_sessions(user_id=request.user.pk)
        paginator = self.pagination_class()
        page = paginator.paginate_queryset(queryset, request, view=self)
        if page is not None:
            serializer = AuthSessionSerializer(page, many=True, context={"request": request})
            return paginator.get_paginated_response(
                serializer.data, message="لیست نشست‌ها با موفقیت دریافت شد."
            )
        return SuccessResponse(
            data=AuthSessionSerializer(queryset, many=True, context={"request": request}).data,
            message="لیست نشست‌ها با موفقیت دریافت شد.",
        )


class AuthSessionRevokeAPIView(APIView):
    """Revoke one current-user auth session with IDOR protection."""

    permission_classes = [IsAuthenticated]

    @extend_schema(
        operation_id="auth_sessions_revoke",
        tags=[TAG_AUTH_USER],
        summary="لغو یکی از نشست‌های من",
        request=None,
        responses={
            200: AUTH_SESSION_DETAIL_RESPONSE,
            401: GENERIC_ERROR_RESPONSE,
            404: GENERIC_ERROR_RESPONSE,
        },
    )
    def post(self, request: Request, session_id: int) -> Response:
        session = get_user_auth_session_by_id(user_id=request.user.pk, session_id=session_id)
        if session is None:
            return ErrorResponse(
                message="نشستی با این شناسه یافت نشد.", status_code=status.HTTP_404_NOT_FOUND
            )
        session = revoke_auth_session(session=session, revoked_by=request.user)
        metadata = extract_audit_metadata(request)
        log_action_async(
            user_id=request.user.pk,
            action=audit_actions.AUTH_SESSION_REVOKED,
            resource_type="auth_session",
            resource_id=str(session.pk),
            extra_data={"self_revoke": True},
            **metadata,
        )
        return SuccessResponse(
            data=AuthSessionSerializer(session, context={"request": request}).data,
            message="نشست با موفقیت لغو شد.",
        )


class AdminUserSessionsListAPIView(APIView):
    """Admin list endpoint for a user's tracked sessions."""

    permission_classes = [IsAdminUser]
    pagination_class = StandardPagination

    @extend_schema(
        operation_id="auth_admin_user_sessions_list",
        tags=[TAG_AUTH_ADMIN],
        summary="لیست نشست‌های کاربر — ادمین",
        responses={
            200: AUTH_SESSION_LIST_RESPONSE,
            403: GENERIC_ERROR_RESPONSE,
            404: GENERIC_ERROR_RESPONSE,
        },
    )
    def get(self, request: Request, user_id: int) -> Response:
        user = get_user_by_id(user_id)
        if user is None:
            return ErrorResponse(message="کاربر یافت نشد.", status_code=status.HTTP_404_NOT_FOUND)
        queryset = get_user_auth_sessions(user_id=user.pk)
        paginator = self.pagination_class()
        page = paginator.paginate_queryset(queryset, request, view=self)
        if page is not None:
            serializer = AuthSessionSerializer(page, many=True, context={"request": request})
            return paginator.get_paginated_response(
                serializer.data, message="لیست نشست‌های کاربر دریافت شد."
            )
        return SuccessResponse(
            data=AuthSessionSerializer(queryset, many=True, context={"request": request}).data,
            message="لیست نشست‌های کاربر دریافت شد.",
        )


class AdminUserSessionsRevokeAPIView(APIView):
    """Admin endpoint to revoke all active sessions for one user."""

    permission_classes = [IsAdminUser]

    @extend_schema(
        operation_id="auth_admin_user_sessions_revoke_all",
        tags=[TAG_AUTH_ADMIN],
        summary="لغو همه نشست‌های کاربر — ادمین",
        request=None,
        responses={
            200: EMPTY_SUCCESS_RESPONSE,
            403: GENERIC_ERROR_RESPONSE,
            404: GENERIC_ERROR_RESPONSE,
        },
    )
    def post(self, request: Request, user_id: int) -> Response:
        user = get_user_by_id(user_id)
        if user is None:
            return ErrorResponse(message="کاربر یافت نشد.", status_code=status.HTTP_404_NOT_FOUND)
        revoked_count = revoke_all_user_sessions(user=user, revoked_by=request.user)
        metadata = extract_audit_metadata(request)
        log_action_async(
            user_id=request.user.pk,
            action=audit_actions.AUTH_USER_SESSIONS_REVOKED,
            resource_type="user",
            resource_id=str(user.pk),
            extra_data={"revoked_count": revoked_count},
            **metadata,
        )
        return SuccessResponse(
            data={"revoked_count": revoked_count}, message="نشست‌های کاربر با موفقیت لغو شد."
        )

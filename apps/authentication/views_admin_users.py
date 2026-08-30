"""گروه دامنه‌ای `views_admin_users` از views — فاز ۱۱ (تفکیک P3-16).

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
from apps.audit_logs.services import log_action, log_action_async
from apps.core.pagination import StandardPagination
from apps.core.responses import (
    DeletedResponse,
    ErrorResponse,
    SuccessResponse,
)

from .filters import UserAdminFilter
from .permissions import IsAdminUser
from .selectors import (
    get_all_users_for_admin,
    get_user_by_id,
)
from .serializers import (
    AdminUserUpdateSerializer,
    UserAdminSerializer,
)
from .services import (
    admin_update_user,
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
                    field: serializer.validated_data[field] for field in serializer.validated_data
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

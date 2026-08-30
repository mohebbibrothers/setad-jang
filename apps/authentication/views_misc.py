"""گروه دامنه‌ای `views_misc` از views — فاز ۱۱ (تفکیک P3-16).

کلاس‌ها عیناً منتقل شده‌اند؛ مشترکات از views_common؛ نامِ عمومیِ این گروه‌ها را فقط از facade (apps.*.views) یا همین ماژول import کنید.
"""

from __future__ import annotations

from drf_spectacular.utils import (
    extend_schema,
)
from rest_framework import status
from rest_framework.request import Request
from rest_framework.views import APIView

from apps.audit_logs import actions as audit_actions
from apps.audit_logs.helpers import extract_audit_metadata
from apps.audit_logs.services import log_action
from apps.core.responses import (
    ErrorResponse,
    SuccessResponse,
)

from .permissions import IsAdminUser
from .selectors import (
    get_user_by_id,
)
from .serializers import (
    AdminChangeRoleSerializer,
    UserAdminSerializer,
)
from .services import (
    admin_change_user_role,
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

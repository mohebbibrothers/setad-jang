"""گروه دامنه‌ای `views_profile` از views — فاز ۱۱ (تفکیک P3-16).

کلاس‌ها عیناً منتقل شده‌اند؛ مشترکات از views_common؛ نامِ عمومیِ این گروه‌ها را فقط از facade (apps.*.views) یا همین ماژول import کنید.
"""

from __future__ import annotations

from drf_spectacular.utils import (
    extend_schema,
)
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.views import APIView

from apps.core.responses import (
    SuccessResponse,
)

from .serializers import (
    ProfileSerializer,
    UpdateMeSerializer,
    UpdateProfileSerializer,
    UserMeSerializer,
)
from .services import (
    update_profile,
    update_user_basic_info,
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
            "ویرایش اطلاعات تکمیلی پروفایل کاربر لاگین کرده.\n\nتمام فیلدها optional هستند."
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

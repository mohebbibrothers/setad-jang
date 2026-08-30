"""گروه دامنه‌ای `views_bounties` از views — فاز ۱۱ (تفکیک P3-16).

کلاس‌ها عیناً منتقل شده‌اند؛ مشترکات از views_common؛ نامِ عمومیِ این گروه‌ها را فقط از facade (apps.*.views) یا همین ماژول import کنید.
"""

from __future__ import annotations

from drf_spectacular.utils import (
    extend_schema,
    extend_schema_view,
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
    CreatedResponse,
    ErrorResponse,
    SuccessResponse,
)

from . import selectors, services
from .filters import (
    R4JBountyAdminFilter,
)
from .permissions import IsFullyVerifiedUser, IsR4JAdminUser
from .serializers import (
    R4JAdminBountyDetailSerializer,
    R4JAdminBountyListSerializer,
    R4JBountyCancelActionSerializer,
    R4JBountySetSerializer,
    R4JUserBountySerializer,
)
from .services import (
    BountyNotCancelable,
    BountyNotInCancelRequested,
    BountyUpdateNotAllowed,
    InvalidBountyAmount,
)
from .throttles import (
    R4JBountySetThrottle,
)
from .views_common import (  # noqa: F401 — re-exportِ رایگان برای بدنه‌های منتقل‌شده
    ADMIN_ALIAS_LIST_RESPONSE,
    ADMIN_ALIAS_RESPONSE,
    ADMIN_ATTACHMENT_LIST_RESPONSE,
    ADMIN_ATTACHMENT_RESPONSE,
    ADMIN_BOUNTY_DETAIL_RESPONSE,
    ADMIN_BOUNTY_FILTER_PARAMS,
    ADMIN_BOUNTY_LIST_RESPONSE,
    ADMIN_CUSTODY_EVENT_LIST_RESPONSE,
    ADMIN_CUSTODY_EVENT_RESPONSE,
    ADMIN_DETAIL_RESPONSE,
    ADMIN_LIST_FILTER_PARAMS,
    ADMIN_LIST_RESPONSE,
    ADMIN_PHONE_LIST_RESPONSE,
    ADMIN_PHONE_RESPONSE,
    ADMIN_PHOTO_LIST_RESPONSE,
    ADMIN_PHOTO_RESPONSE,
    ADMIN_REPORT_DETAIL_RESPONSE,
    ADMIN_REPORT_FILTER_PARAMS,
    ADMIN_REPORT_LIST_RESPONSE,
    ADMIN_SOCIAL_LIST_RESPONSE,
    ADMIN_SOCIAL_RESPONSE,
    ADMIN_VISIBILITY_LIST_RESPONSE,
    ADMIN_VISIBILITY_RESPONSE,
    EMPTY_SUCCESS_RESPONSE,
    GENERIC_ERROR_RESPONSE,
    LIST_PAGINATION_PARAMS,
    PUBLIC_DETAIL_RESPONSE,
    PUBLIC_LIST_FILTER_PARAMS,
    PUBLIC_LIST_RESPONSE,
    TAG_R4J_ADMIN,
    TAG_R4J_BOUNTY,
    TAG_R4J_PUBLIC,
    TAG_R4J_USER,
    USER_BOUNTY_DETAIL_RESPONSE,
    USER_BOUNTY_FILTER_PARAMS,
    USER_BOUNTY_LIST_RESPONSE,
    USER_REPORT_DETAIL_RESPONSE,
    USER_REPORT_FILTER_PARAMS,
    USER_REPORT_LIST_RESPONSE,
    _build_filters_signature,
)


class R4JUserBountySetView(APIView):
    """
    تعیین یا ویرایش bounty توسط کاربر fully verified.

    endpoint: POST /api/v1/r4j/criminals/{criminal_id}/bounty/
    """

    permission_classes = [IsFullyVerifiedUser]
    throttle_classes = [R4JBountySetThrottle]

    @extend_schema(
        operation_id="r4j_user_bounty_set_or_update",
        tags=[TAG_R4J_BOUNTY],
        summary="تعیین یا ویرایش جایزه برای مجرم",
        description=(
            "کاربرانی که احراز هویت کامل داشته و پروفایل آن‌ها کامل باشد "
            "می‌توانند برای یک مجرم جایزه تعیین کنند.\n\n"
            "اگر قبلاً برای همان مجرم جایزه‌ای فعال ثبت کرده باشند، همان رکورد "
            "به‌روزرسانی می‌شود؛ در غیر این صورت رکورد جدید ساخته می‌شود."
        ),
        request=R4JBountySetSerializer,
        responses={
            201: USER_BOUNTY_DETAIL_RESPONSE,
            200: USER_BOUNTY_DETAIL_RESPONSE,
            400: GENERIC_ERROR_RESPONSE,
            401: GENERIC_ERROR_RESPONSE,
            403: GENERIC_ERROR_RESPONSE,
            404: GENERIC_ERROR_RESPONSE,
            429: GENERIC_ERROR_RESPONSE,
        },
    )
    def post(self, request: Request, criminal_id: int) -> Response:
        criminal = selectors.get_public_criminal_detail(lookup=criminal_id)
        if criminal is None:
            return ErrorResponse(
                message="مجرمی با این شناسه یافت نشد.",
                status_code=status.HTTP_404_NOT_FOUND,
            )

        serializer = R4JBountySetSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        try:
            bounty, created = services.set_or_update_bounty(
                criminal=criminal,
                user=request.user,
                amount_toman=serializer.validated_data["amount_toman"],
            )
        except (InvalidBountyAmount, BountyUpdateNotAllowed) as exc:
            return ErrorResponse(message=str(exc))

        metadata = extract_audit_metadata(request)
        log_action_async(
            user_id=request.user.pk,
            action=(
                audit_actions.R4J_BOUNTY_CREATED if created else audit_actions.R4J_BOUNTY_UPDATED
            ),
            resource_type="r4j_bounty",
            resource_id=str(bounty.pk),
            extra_data={
                "criminal_id": criminal_id,
                "amount_toman": bounty.amount_toman,
            },
            **metadata,
        )

        bounty_detail = selectors.get_user_bounty_by_id(
            user_id=request.user.pk,
            bounty_id=bounty.pk,
        )

        if created:
            return CreatedResponse(
                data=R4JUserBountySerializer(bounty_detail).data,
                message="جایزه با موفقیت ثبت شد.",
            )

        return SuccessResponse(
            data=R4JUserBountySerializer(bounty_detail).data,
            message="جایزه با موفقیت بروزرسانی شد.",
        )


class R4JUserBountyCancelView(APIView):
    """
    درخواست لغو bounty توسط owner.

    endpoint: POST /api/v1/r4j/me/bounties/{bounty_id}/cancel/
    """

    permission_classes = [IsAuthenticated]

    @extend_schema(
        operation_id="r4j_user_bounty_cancel_request",
        tags=[TAG_R4J_BOUNTY],
        summary="درخواست لغو جایزه",
        description=(
            "کاربر می‌تواند برای جایزه‌ای که خودش تعیین کرده درخواست لغو ثبت کند.\n\n"
            "فقط جایزه‌های فعال قابل درخواست لغو هستند و درخواست لغو باید "
            "توسط ادمین تأیید یا رد شود."
        ),
        request=None,
        responses={
            200: USER_BOUNTY_DETAIL_RESPONSE,
            400: GENERIC_ERROR_RESPONSE,
            401: GENERIC_ERROR_RESPONSE,
            404: GENERIC_ERROR_RESPONSE,
        },
    )
    def post(self, request: Request, bounty_id: int) -> Response:
        bounty = selectors.get_user_bounty_by_id(
            user_id=request.user.pk,
            bounty_id=bounty_id,
        )
        if bounty is None:
            return ErrorResponse(
                message="جایزه‌ای با این شناسه یافت نشد.",
                status_code=status.HTTP_404_NOT_FOUND,
            )

        try:
            bounty = services.request_bounty_cancel(
                bounty=bounty,
                user=request.user,
            )
        except BountyNotCancelable as exc:
            return ErrorResponse(message=str(exc))

        metadata = extract_audit_metadata(request)
        log_action_async(
            user_id=request.user.pk,
            action=audit_actions.R4J_BOUNTY_CANCEL_REQUESTED,
            resource_type="r4j_bounty",
            resource_id=str(bounty.pk),
            **metadata,
        )

        bounty_refreshed = selectors.get_user_bounty_by_id(
            user_id=request.user.pk,
            bounty_id=bounty.pk,
        )

        return SuccessResponse(
            data=R4JUserBountySerializer(bounty_refreshed).data,
            message="درخواست لغو جایزه با موفقیت ثبت شد.",
        )


# ============================================================
# Admin — Bounties
# ============================================================


@extend_schema_view(
    get=extend_schema(
        operation_id="r4j_admin_bounties_list",
        tags=[TAG_R4J_ADMIN],
        summary="لیست جوایز — ادمین",
        description="دریافت لیست تمام جوایز ثبت‌شده با امکان فیلتر کامل.",
        parameters=ADMIN_BOUNTY_FILTER_PARAMS,
        responses={
            200: ADMIN_BOUNTY_LIST_RESPONSE,
            403: GENERIC_ERROR_RESPONSE,
        },
    ),
)
class R4JAdminBountyListView(APIView):
    """لیست تمام bountyها — admin."""

    permission_classes = [IsR4JAdminUser]

    def get(self, request: Request) -> Response:
        queryset = selectors.get_admin_bounties_queryset()
        filterset = R4JBountyAdminFilter(request.query_params, queryset=queryset)
        if filterset.is_valid():
            queryset = filterset.qs

        paginator = StandardPagination()
        page = paginator.paginate_queryset(queryset, request, view=self)

        if page is not None:
            serializer = R4JAdminBountyListSerializer(page, many=True)
            return paginator.get_paginated_response(
                serializer.data,
                message="لیست جوایز با موفقیت دریافت شد.",
            )

        serializer = R4JAdminBountyListSerializer(queryset, many=True)
        return SuccessResponse(
            data=serializer.data,
            message="لیست جوایز با موفقیت دریافت شد.",
        )


class R4JAdminBountyDetailView(APIView):
    """جزئیات یک bounty — admin."""

    permission_classes = [IsR4JAdminUser]

    @extend_schema(
        operation_id="r4j_admin_bounty_retrieve",
        tags=[TAG_R4J_ADMIN],
        summary="جزئیات جایزه — ادمین",
        responses={
            200: ADMIN_BOUNTY_DETAIL_RESPONSE,
            403: GENERIC_ERROR_RESPONSE,
            404: GENERIC_ERROR_RESPONSE,
        },
    )
    def get(self, request: Request, bounty_id: int) -> Response:
        bounty = selectors.get_admin_bounty_by_id(bounty_id=bounty_id)
        if bounty is None:
            return ErrorResponse(
                message="جایزه‌ای با این شناسه یافت نشد.",
                status_code=status.HTTP_404_NOT_FOUND,
            )
        return SuccessResponse(
            data=R4JAdminBountyDetailSerializer(bounty).data,
            message="جزئیات جایزه با موفقیت دریافت شد.",
        )


class R4JAdminBountyCancelApproveView(APIView):
    """
    تأیید درخواست لغو bounty توسط ادمین.

    endpoint: POST /api/v1/r4j/admin/bounties/{bounty_id}/cancel/approve/
    """

    permission_classes = [IsR4JAdminUser]

    @extend_schema(
        operation_id="r4j_admin_bounty_cancel_approve",
        tags=[TAG_R4J_ADMIN],
        summary="تأیید درخواست لغو جایزه — ادمین",
        request=R4JBountyCancelActionSerializer,
        responses={
            200: ADMIN_BOUNTY_DETAIL_RESPONSE,
            400: GENERIC_ERROR_RESPONSE,
            403: GENERIC_ERROR_RESPONSE,
            404: GENERIC_ERROR_RESPONSE,
        },
    )
    def post(self, request: Request, bounty_id: int) -> Response:
        bounty = selectors.get_admin_bounty_by_id(bounty_id=bounty_id)
        if bounty is None:
            return ErrorResponse(
                message="جایزه‌ای با این شناسه یافت نشد.",
                status_code=status.HTTP_404_NOT_FOUND,
            )

        serializer = R4JBountyCancelActionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        try:
            bounty = services.approve_bounty_cancel(
                bounty=bounty,
                admin=request.user,
                admin_note=serializer.validated_data.get("admin_note", ""),
            )
        except BountyNotInCancelRequested as exc:
            return ErrorResponse(message=str(exc))

        metadata = extract_audit_metadata(request)
        log_action_async(
            user_id=request.user.pk,
            action=audit_actions.R4J_BOUNTY_CANCEL_APPROVED,
            resource_type="r4j_bounty",
            resource_id=str(bounty.pk),
            **metadata,
        )

        bounty_refreshed = selectors.get_admin_bounty_by_id(bounty_id=bounty.pk)

        return SuccessResponse(
            data=R4JAdminBountyDetailSerializer(bounty_refreshed).data,
            message="درخواست لغو جایزه تأیید شد.",
        )


class R4JAdminBountyCancelRejectView(APIView):
    """
    رد درخواست لغو bounty توسط ادمین.

    endpoint: POST /api/v1/r4j/admin/bounties/{bounty_id}/cancel/reject/
    """

    permission_classes = [IsR4JAdminUser]

    @extend_schema(
        operation_id="r4j_admin_bounty_cancel_reject",
        tags=[TAG_R4J_ADMIN],
        summary="رد درخواست لغو جایزه — ادمین",
        request=R4JBountyCancelActionSerializer,
        responses={
            200: ADMIN_BOUNTY_DETAIL_RESPONSE,
            400: GENERIC_ERROR_RESPONSE,
            403: GENERIC_ERROR_RESPONSE,
            404: GENERIC_ERROR_RESPONSE,
        },
    )
    def post(self, request: Request, bounty_id: int) -> Response:
        bounty = selectors.get_admin_bounty_by_id(bounty_id=bounty_id)
        if bounty is None:
            return ErrorResponse(
                message="جایزه‌ای با این شناسه یافت نشد.",
                status_code=status.HTTP_404_NOT_FOUND,
            )

        serializer = R4JBountyCancelActionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        try:
            bounty = services.reject_bounty_cancel(
                bounty=bounty,
                admin=request.user,
                admin_note=serializer.validated_data.get("admin_note", ""),
            )
        except BountyNotInCancelRequested as exc:
            return ErrorResponse(message=str(exc))

        metadata = extract_audit_metadata(request)
        log_action_async(
            user_id=request.user.pk,
            action=audit_actions.R4J_BOUNTY_CANCEL_REJECTED,
            resource_type="r4j_bounty",
            resource_id=str(bounty.pk),
            **metadata,
        )

        bounty_refreshed = selectors.get_admin_bounty_by_id(bounty_id=bounty.pk)

        return SuccessResponse(
            data=R4JAdminBountyDetailSerializer(bounty_refreshed).data,
            message="درخواست لغو جایزه رد شد و جایزه دوباره فعال شد.",
        )

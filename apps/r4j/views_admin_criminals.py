"""گروه دامنه‌ای `views_admin_criminals` از views — فاز ۱۱ (تفکیک P3-16).

کلاس‌ها عیناً منتقل شده‌اند؛ مشترکات از views_common؛ نامِ عمومیِ این گروه‌ها را فقط از facade (apps.*.views) یا همین ماژول import کنید.
"""

from __future__ import annotations

from drf_spectacular.utils import (
    extend_schema,
    extend_schema_view,
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
    CreatedResponse,
    DeletedResponse,
    ErrorResponse,
    SuccessResponse,
)

from . import selectors, services
from .filters import (
    R4JCriminalAdminFilter,
)
from .permissions import IsR4JAdminUser
from .serializers import (
    R4JAdminCriminalDetailSerializer,
    R4JAdminCriminalListSerializer,
    R4JCriminalCreateSerializer,
    R4JCriminalUpdateSerializer,
)
from .services import (
    CriminalAlreadyPublished,
    CriminalAlreadyUnpublished,
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

# ============================================================
# Admin — Criminals CRUD
# ============================================================


@extend_schema_view(
    get=extend_schema(
        operation_id="r4j_admin_criminals_list",
        tags=[TAG_R4J_ADMIN],
        summary="لیست مجرمین — ادمین",
        description="لیست تمام مجرمین شامل draft و soft-deleted.",
        parameters=ADMIN_LIST_FILTER_PARAMS,
        responses={
            200: ADMIN_LIST_RESPONSE,
            403: GENERIC_ERROR_RESPONSE,
        },
    ),
    post=extend_schema(
        operation_id="r4j_admin_criminals_create",
        tags=[TAG_R4J_ADMIN],
        summary="ساخت پروفایل مجرم جدید — ادمین",
        description=(
            "ساخت پروفایل جدید. همیشه draft ساخته می‌شود و باید با endpoint publish منتشر شود."
        ),
        request=R4JCriminalCreateSerializer,
        responses={
            201: ADMIN_DETAIL_RESPONSE,
            400: GENERIC_ERROR_RESPONSE,
            403: GENERIC_ERROR_RESPONSE,
        },
    ),
)
class R4JAdminCriminalListCreateView(APIView):
    """list + create criminals — admin."""

    permission_classes = [IsR4JAdminUser]
    pagination_class = StandardPagination

    def get(self, request: Request) -> Response:
        queryset = selectors.get_admin_criminals_queryset()
        filterset = R4JCriminalAdminFilter(request.query_params, queryset=queryset)
        if filterset.is_valid():
            queryset = filterset.qs

        paginator = self.pagination_class()
        page = paginator.paginate_queryset(queryset, request, view=self)

        if page is not None:
            serializer = R4JAdminCriminalListSerializer(page, many=True)
            return paginator.get_paginated_response(
                serializer.data,
                message="لیست مجرمین با موفقیت دریافت شد.",
            )

        serializer = R4JAdminCriminalListSerializer(queryset, many=True)
        return SuccessResponse(
            data=serializer.data,
            message="لیست مجرمین با موفقیت دریافت شد.",
        )

    def post(self, request: Request) -> Response:
        serializer = R4JCriminalCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        criminal = services.create_criminal(
            created_by=request.user,
            **serializer.validated_data,
        )

        metadata = extract_audit_metadata(request)
        log_action_async(
            user_id=request.user.pk,
            action=audit_actions.R4J_CRIMINAL_CREATED,
            resource_type="r4j_criminal",
            resource_id=str(criminal.pk),
            extra_data={"slug": criminal.slug},
            **metadata,
        )

        return CreatedResponse(
            data=R4JAdminCriminalDetailSerializer(criminal).data,
            message="پروفایل مجرم با موفقیت ساخته شد.",
        )


@extend_schema_view(
    get=extend_schema(
        operation_id="r4j_admin_criminal_retrieve",
        tags=[TAG_R4J_ADMIN],
        summary="جزئیات مجرم — ادمین",
        responses={
            200: ADMIN_DETAIL_RESPONSE,
            403: GENERIC_ERROR_RESPONSE,
            404: GENERIC_ERROR_RESPONSE,
        },
    ),
    patch=extend_schema(
        operation_id="r4j_admin_criminal_update",
        tags=[TAG_R4J_ADMIN],
        summary="ویرایش مجرم — ادمین",
        request=R4JCriminalUpdateSerializer,
        responses={
            200: ADMIN_DETAIL_RESPONSE,
            400: GENERIC_ERROR_RESPONSE,
            403: GENERIC_ERROR_RESPONSE,
            404: GENERIC_ERROR_RESPONSE,
        },
    ),
    delete=extend_schema(
        operation_id="r4j_admin_criminal_delete",
        tags=[TAG_R4J_ADMIN],
        summary="حذف نرم مجرم — ادمین",
        description="غیرفعال (soft delete) و خودکار unpublish می‌شود.",
        responses={
            200: EMPTY_SUCCESS_RESPONSE,
            403: GENERIC_ERROR_RESPONSE,
            404: GENERIC_ERROR_RESPONSE,
        },
    ),
)
class R4JAdminCriminalDetailView(APIView):
    """retrieve + update + delete — admin."""

    permission_classes = [IsR4JAdminUser]

    def get(self, request: Request, criminal_id: int) -> Response:
        criminal = selectors.get_admin_criminal_detail(lookup=criminal_id)
        if criminal is None:
            return ErrorResponse(
                message="مجرمی با این شناسه یافت نشد.",
                status_code=status.HTTP_404_NOT_FOUND,
            )
        return SuccessResponse(
            data=R4JAdminCriminalDetailSerializer(criminal).data,
            message="جزئیات با موفقیت دریافت شد.",
        )

    def patch(self, request: Request, criminal_id: int) -> Response:
        criminal = selectors.get_admin_criminal_by_id(criminal_id)
        if criminal is None:
            return ErrorResponse(
                message="مجرمی با این شناسه یافت نشد.",
                status_code=status.HTTP_404_NOT_FOUND,
            )
        serializer = R4JCriminalUpdateSerializer(data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)

        criminal = services.update_criminal(
            criminal=criminal,
            **serializer.validated_data,
        )

        metadata = extract_audit_metadata(request)
        log_action_async(
            user_id=request.user.pk,
            action=audit_actions.R4J_CRIMINAL_UPDATED,
            resource_type="r4j_criminal",
            resource_id=str(criminal.pk),
            changes={k: v for k, v in serializer.validated_data.items()},
            **metadata,
        )

        return SuccessResponse(
            data=R4JAdminCriminalDetailSerializer(criminal).data,
            message="پروفایل با موفقیت بروزرسانی شد.",
        )

    def delete(self, request: Request, criminal_id: int) -> Response:
        criminal = selectors.get_admin_criminal_by_id(criminal_id)
        if criminal is None:
            return ErrorResponse(
                message="مجرمی با این شناسه یافت نشد.",
                status_code=status.HTTP_404_NOT_FOUND,
            )
        services.soft_delete_criminal(criminal=criminal)

        metadata = extract_audit_metadata(request)
        log_action(
            user_id=request.user.pk,
            action=audit_actions.R4J_CRIMINAL_DELETED,
            resource_type="r4j_criminal",
            resource_id=str(criminal_id),
            extra_data={"slug": criminal.slug},
            **metadata,
        )

        return DeletedResponse(message="پروفایل با موفقیت غیرفعال شد.")


# ============================================================
# Admin — Publish / Unpublish
# ============================================================


class R4JAdminCriminalPublishView(APIView):
    """انتشار یک مجرم — admin."""

    permission_classes = [IsR4JAdminUser]

    @extend_schema(
        operation_id="r4j_admin_criminal_publish",
        tags=[TAG_R4J_ADMIN],
        summary="انتشار مجرم — ادمین",
        request=None,
        responses={
            200: ADMIN_DETAIL_RESPONSE,
            400: GENERIC_ERROR_RESPONSE,
            403: GENERIC_ERROR_RESPONSE,
            404: GENERIC_ERROR_RESPONSE,
        },
    )
    def post(self, request: Request, criminal_id: int) -> Response:
        criminal = selectors.get_admin_criminal_by_id(criminal_id)
        if criminal is None:
            return ErrorResponse(
                message="مجرمی با این شناسه یافت نشد.",
                status_code=status.HTTP_404_NOT_FOUND,
            )
        try:
            criminal = services.publish_criminal(criminal=criminal)
        except CriminalAlreadyPublished as exc:
            return ErrorResponse(message=str(exc))

        metadata = extract_audit_metadata(request)
        log_action_async(
            user_id=request.user.pk,
            action=audit_actions.R4J_CRIMINAL_PUBLISHED,
            resource_type="r4j_criminal",
            resource_id=str(criminal.pk),
            **metadata,
        )

        return SuccessResponse(
            data=R4JAdminCriminalDetailSerializer(criminal).data,
            message="پروفایل با موفقیت منتشر شد.",
        )


class R4JAdminCriminalUnpublishView(APIView):
    """خروج از انتشار یک مجرم — admin."""

    permission_classes = [IsR4JAdminUser]

    @extend_schema(
        operation_id="r4j_admin_criminal_unpublish",
        tags=[TAG_R4J_ADMIN],
        summary="خروج از انتشار مجرم — ادمین",
        request=None,
        responses={
            200: ADMIN_DETAIL_RESPONSE,
            400: GENERIC_ERROR_RESPONSE,
            403: GENERIC_ERROR_RESPONSE,
            404: GENERIC_ERROR_RESPONSE,
        },
    )
    def post(self, request: Request, criminal_id: int) -> Response:
        criminal = selectors.get_admin_criminal_by_id(criminal_id)
        if criminal is None:
            return ErrorResponse(
                message="مجرمی با این شناسه یافت نشد.",
                status_code=status.HTTP_404_NOT_FOUND,
            )
        try:
            criminal = services.unpublish_criminal(criminal=criminal)
        except CriminalAlreadyUnpublished as exc:
            return ErrorResponse(message=str(exc))

        metadata = extract_audit_metadata(request)
        log_action_async(
            user_id=request.user.pk,
            action=audit_actions.R4J_CRIMINAL_UNPUBLISHED,
            resource_type="r4j_criminal",
            resource_id=str(criminal.pk),
            **metadata,
        )

        return SuccessResponse(
            data=R4JAdminCriminalDetailSerializer(criminal).data,
            message="انتشار پروفایل با موفقیت لغو شد.",
        )

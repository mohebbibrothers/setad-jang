"""
Views اپ audit_logs — Admin API برای مشاهده و جستجوی لاگ‌های فعالیت.

ساختار:
- فقط Admin endpoints — هیچ public endpoint وجود ندارد.
- فقط read-only — هیچ mutation endpoint وجود ندارد.

اصول طراحی:
- View هیچ business logic مستقیمی ندارد.
- تمام queryها از selector layer عبور می‌کنند.
- pagination و filter استاندارد پروژه رعایت می‌شود.
- Swagger/ReDoc documentation کامل.
"""

from __future__ import annotations

from drf_spectacular.utils import OpenApiParameter, OpenApiTypes, extend_schema
from rest_framework import status
from rest_framework.request import Request
from rest_framework.views import APIView

from apps.authentication.permissions import IsAdminUser
from apps.core.pagination import StandardPagination
from apps.core.responses import ErrorResponse, SuccessResponse
from apps.core.schemas import (
    build_error_response_serializer,
    build_paginated_success_response_serializer,
    build_success_response_serializer,
)

from .filters import AuditLogFilter
from .selectors import get_all_audit_logs, get_audit_log_by_id
from .serializers import AuditLogDetailSerializer, AuditLogListSerializer

# ============================================================
# Tag Constants
# ============================================================

TAG_AUDIT_ADMIN = "لاگ فعالیت — مدیریت"

# ============================================================
# Swagger Response Schemas
# ============================================================

GENERIC_ERROR_RESPONSE = build_error_response_serializer(
    name="AuditLogGenericErrorResponse",
)
AUDIT_LOG_LIST_RESPONSE = build_paginated_success_response_serializer(
    name="AuditLogPaginatedListResponse",
    item_serializer=AuditLogListSerializer,
)
AUDIT_LOG_DETAIL_RESPONSE = build_success_response_serializer(
    name="AuditLogDetailResponse",
    data_serializer=AuditLogDetailSerializer,
)

# ============================================================
# Query Parameters
# ============================================================

AUDIT_LOG_LIST_PARAMETERS = [
    OpenApiParameter(
        name="page",
        type=OpenApiTypes.INT,
        location=OpenApiParameter.QUERY,
        description="شماره صفحه",
    ),
    OpenApiParameter(
        name="page_size",
        type=OpenApiTypes.INT,
        location=OpenApiParameter.QUERY,
        description="تعداد آیتم در هر صفحه (حداکثر ۱۰۰)",
    ),
    OpenApiParameter(
        name="action",
        type=OpenApiTypes.STR,
        location=OpenApiParameter.QUERY,
        description="فیلتر بر اساس نوع عملیات (exact match)",
    ),
    OpenApiParameter(
        name="user_id",
        type=OpenApiTypes.INT,
        location=OpenApiParameter.QUERY,
        description="فیلتر بر اساس شناسه کاربر",
    ),
    OpenApiParameter(
        name="resource_type",
        type=OpenApiTypes.STR,
        location=OpenApiParameter.QUERY,
        description="فیلتر بر اساس نوع منبع (user, report, tabyin_content, ...)",
    ),
    OpenApiParameter(
        name="resource_id",
        type=OpenApiTypes.STR,
        location=OpenApiParameter.QUERY,
        description="فیلتر بر اساس شناسه منبع",
    ),
    OpenApiParameter(
        name="request_id",
        type=OpenApiTypes.STR,
        location=OpenApiParameter.QUERY,
        description="فیلتر بر اساس شناسه درخواست (X-Request-ID)",
    ),
    OpenApiParameter(
        name="ip_address",
        type=OpenApiTypes.STR,
        location=OpenApiParameter.QUERY,
        description="فیلتر بر اساس آدرس IP",
    ),
    OpenApiParameter(
        name="created_after",
        type=OpenApiTypes.DATETIME,
        location=OpenApiParameter.QUERY,
        description="فیلتر از تاریخ (ISO 8601)",
    ),
    OpenApiParameter(
        name="created_before",
        type=OpenApiTypes.DATETIME,
        location=OpenApiParameter.QUERY,
        description="فیلتر تا تاریخ (ISO 8601)",
    ),
    OpenApiParameter(
        name="search",
        type=OpenApiTypes.STR,
        location=OpenApiParameter.QUERY,
        description="جستجو در action، resource_type و resource_id",
    ),
]


# ============================================================
# Admin Views
# ============================================================


class AdminAuditLogListAPIView(APIView):
    """لیست تمام لاگ‌های فعالیت — ادمین."""

    permission_classes = [IsAdminUser]
    pagination_class = StandardPagination

    @extend_schema(
        operation_id="audit_logs_admin_list",
        tags=[TAG_AUDIT_ADMIN],
        summary="لیست لاگ‌های فعالیت",
        description=(
            "دریافت لیست تمام لاگ‌های فعالیت سیستم با pagination و فیلتر.\n\n"
            "**فیلترهای موجود:**\n"
            "- `action`: نوع عملیات (مثل LOGIN_SUCCESS, REPORT_CREATED)\n"
            "- `user_id`: شناسه کاربر\n"
            "- `resource_type`: نوع منبع (user, report, tabyin_content, ...)\n"
            "- `resource_id`: شناسه منبع\n"
            "- `request_id`: شناسه درخواست (X-Request-ID)\n"
            "- `ip_address`: آدرس IP\n"
            "- `created_after` / `created_before`: بازه زمانی\n"
            "- `search`: جستجو در action, resource_type, resource_id\n\n"
            "نیازمند احراز هویت با نقش admin."
        ),
        parameters=AUDIT_LOG_LIST_PARAMETERS,
        responses={
            200: AUDIT_LOG_LIST_RESPONSE,
            403: GENERIC_ERROR_RESPONSE,
        },
    )
    def get(self, request: Request) -> SuccessResponse:
        queryset = get_all_audit_logs()

        filterset = AuditLogFilter(request.query_params, queryset=queryset)
        if filterset.is_valid():
            queryset = filterset.qs

        paginator = self.pagination_class()
        page = paginator.paginate_queryset(queryset, request, view=self)

        if page is not None:
            serializer = AuditLogListSerializer(page, many=True)
            return paginator.get_paginated_response(
                serializer.data,
                message="لیست لاگ‌های فعالیت با موفقیت دریافت شد.",
            )

        serializer = AuditLogListSerializer(queryset, many=True)
        return SuccessResponse(
            data=serializer.data,
            message="لیست لاگ‌های فعالیت با موفقیت دریافت شد.",
        )


class AdminAuditLogDetailAPIView(APIView):
    """جزئیات یک لاگ فعالیت — ادمین."""

    permission_classes = [IsAdminUser]

    @extend_schema(
        operation_id="audit_logs_admin_retrieve",
        tags=[TAG_AUDIT_ADMIN],
        summary="جزئیات لاگ فعالیت",
        description=(
            "دریافت جزئیات کامل یک لاگ فعالیت شامل changes و extra_data.\n\n"
            "نیازمند احراز هویت با نقش admin."
        ),
        responses={
            200: AUDIT_LOG_DETAIL_RESPONSE,
            403: GENERIC_ERROR_RESPONSE,
            404: GENERIC_ERROR_RESPONSE,
        },
    )
    def get(
        self,
        request: Request,
        audit_log_id: int,
    ) -> SuccessResponse | ErrorResponse:
        audit_log = get_audit_log_by_id(audit_log_id)
        if audit_log is None:
            return ErrorResponse(
                message="لاگ فعالیتی با این شناسه یافت نشد.",
                status_code=status.HTTP_404_NOT_FOUND,
            )

        return SuccessResponse(
            data=AuditLogDetailSerializer(audit_log).data,
            message="جزئیات لاگ فعالیت با موفقیت دریافت شد.",
        )

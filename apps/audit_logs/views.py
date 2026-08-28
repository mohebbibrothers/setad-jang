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

from django.http import HttpResponse
from drf_spectacular.utils import OpenApiParameter, OpenApiResponse, OpenApiTypes, extend_schema
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

from .chain import AuditChainVerificationError
from .exporters import AuditExportFilters, build_audit_export_package
from .filters import AuditLogFilter
from .selectors import get_all_audit_logs, get_audit_log_by_id
from .serializers import (
    AuditExportManifestSerializer,
    AuditLogDetailSerializer,
    AuditLogExportQuerySerializer,
    AuditLogListSerializer,
)

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
AUDIT_EXPORT_MANIFEST_RESPONSE = build_success_response_serializer(
    name="AuditExportManifestResponse",
    data_serializer=AuditExportManifestSerializer,
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
        name="method",
        type=OpenApiTypes.STR,
        location=OpenApiParameter.QUERY,
        description="فیلتر بر اساس متد HTTP",
    ),
    OpenApiParameter(
        name="path",
        type=OpenApiTypes.STR,
        location=OpenApiParameter.QUERY,
        description="فیلتر بر اساس مسیر درخواست",
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
            "- `method`: متد HTTP\n"
            "- `path`: مسیر درخواست\n"
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


class AdminAuditLogExportAPIView(APIView):
    """خروجی forensic package برای audit logs — ادمین."""

    permission_classes = [IsAdminUser]

    @extend_schema(
        operation_id="audit_logs_admin_export_forensic_package",
        tags=[TAG_AUDIT_ADMIN],
        summary="خروجی بسته forensic لاگ‌های فعالیت",
        description=(
            "تولید بسته ZIP شامل `manifest.json`, `audit_logs.jsonl`, `audit_logs.csv` و "
            "`audit_logs.xlsx`. قبل از export، زنجیره هش کامل audit trail بررسی می‌شود و خود "
            "عملیات export نیز با action `AUDIT_PACKAGE_EXPORTED` ثبت می‌گردد."
        ),
        parameters=AUDIT_LOG_LIST_PARAMETERS,
        responses={
            200: OpenApiResponse(
                response=OpenApiTypes.BINARY,
                description="ZIP forensic package",
            ),
            400: GENERIC_ERROR_RESPONSE,
            403: GENERIC_ERROR_RESPONSE,
        },
    )
    def get(self, request: Request) -> HttpResponse | ErrorResponse:
        serializer = AuditLogExportQuerySerializer(data=request.query_params)
        if not serializer.is_valid():
            return ErrorResponse(
                message="پارامترهای خروجی audit نامعتبر است.",
                errors=serializer.errors,
                status_code=status.HTTP_400_BAD_REQUEST,
            )

        filters = _build_export_filters(serializer.validated_data)
        try:
            package = build_audit_export_package(
                filters=filters,
                actor_user_id=request.user.pk if request.user.is_authenticated else None,
                actor_ip_address=_get_client_ip(request),
                actor_request_id=getattr(request, "request_id", None)
                or request.headers.get("X-Request-ID"),
                actor_user_agent=request.headers.get("User-Agent", ""),
                actor_path=request.path,
                actor_method=request.method,
                record_export_event=True,
            )
        except AuditChainVerificationError as exc:
            return ErrorResponse(
                message="زنجیره audit trail مخدوش است و خروجی forensic تولید نشد.",
                errors={"chain": str(exc)},
                status_code=status.HTTP_409_CONFLICT,
            )
        except ValueError as exc:
            return ErrorResponse(
                message="تولید خروجی audit امکان‌پذیر نیست.",
                errors={"export": str(exc)},
                status_code=status.HTTP_400_BAD_REQUEST,
            )

        response = HttpResponse(package.content, content_type="application/zip")
        response["Content-Disposition"] = f'attachment; filename="{package.filename}"'
        response["X-Audit-Package-SHA256"] = package.sha256
        response["X-Audit-Package-Records"] = str(package.manifest["record_count"])
        return response


def _build_export_filters(validated_data: dict) -> AuditExportFilters:
    """Translate validated API query params into service-layer export filters."""
    return AuditExportFilters(
        action=validated_data.get("action") or None,
        user_id=validated_data.get("user_id"),
        resource_type=validated_data.get("resource_type") or None,
        resource_id=validated_data.get("resource_id") or None,
        request_id=validated_data.get("request_id") or None,
        ip_address=validated_data.get("ip_address") or None,
        method=validated_data.get("method") or None,
        path=validated_data.get("path") or None,
        created_after=validated_data.get("created_after"),
        created_before=validated_data.get("created_before"),
        search=validated_data.get("search") or None,
    )


def _get_client_ip(request: Request) -> str | None:
    """Extract client IP with X-Forwarded-For support for audited admin exports."""
    forwarded_for = request.META.get("HTTP_X_FORWARDED_FOR")
    if forwarded_for:
        return forwarded_for.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR")

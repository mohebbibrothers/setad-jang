"""
Views اپ گزارشات مردمی — endpointهای ثبت گزارش و مدیریت موضوعات.

ساختار:
- Public: ثبت گزارش و مشاهده موضوعات (بدون نیاز به لاگین).
- Admin: CRUD کامل موضوعات و مدیریت گزارش‌های دریافتی.

اصول طراحی:
- View هیچ business logic مستقیمی ندارد و فقط orchestration می‌کند.
- IP و metadata در view extract شده و به service پاس داده می‌شود.
- Audit log برای تمام mutationها ثبت می‌شود.
"""

from __future__ import annotations

from drf_spectacular.utils import extend_schema
from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.audit_logs import actions as audit_actions
from apps.audit_logs.helpers import extract_audit_metadata, get_client_ip
from apps.audit_logs.services import log_action, log_action_async
from apps.core.pagination import StandardPagination
from apps.core.permissions import IsAdmin
from apps.core.responses import (
    CreatedResponse,
    DeletedResponse,
    ErrorResponse,
    SuccessResponse,
)
from apps.core.schemas import (
    build_error_response_serializer,
    build_paginated_success_response_serializer,
    build_success_response_serializer,
)

from .filters import ReportFilter, ReportSubjectFilter
from .selectors import (
    get_active_subjects,
    get_all_reports,
    get_all_subjects_for_admin,
    get_report_by_id,
    get_subject_by_id_for_admin,
)
from .serializers import (
    ReportCreateSerializer,
    ReportDetailSerializer,
    ReportListSerializer,
    ReportStatusUpdateSerializer,
    ReportSubjectAdminSerializer,
    ReportSubjectCreateSerializer,
    ReportSubjectPublicSerializer,
    ReportSubjectUpdateSerializer,
)
from .services import (
    create_report,
    create_subject,
    delete_subject,
    update_report_status,
    update_subject,
)
from .throttles import ReportCreateAnonThrottle, ReportCreateUserThrottle

# ============================================================
# Tag Constants — استاندارد یکپارچه پروژه
# ============================================================

TAG_REPORTS_PUBLIC = "گزارشات مردمی — عمومی"
TAG_REPORTS_ADMIN_SUBJECTS = "گزارشات مردمی — موضوعات (مدیریت)"
TAG_REPORTS_ADMIN_REPORTS = "گزارشات مردمی — گزارشات (مدیریت)"


# ============================================================
# Swagger Response Schemas
# ============================================================

GENERIC_ERROR_RESPONSE = build_error_response_serializer(
    name="PublicReportsGenericErrorResponse",
)
EMPTY_SUCCESS_RESPONSE = build_success_response_serializer(
    name="PublicReportsEmptySuccessResponse",
)

# Subject schemas
SUBJECT_PUBLIC_LIST_SUCCESS_RESPONSE = build_success_response_serializer(
    name="ReportSubjectPublicListSuccessResponse",
    data_serializer=ReportSubjectPublicSerializer,
    many=True,
)
SUBJECT_ADMIN_LIST_SUCCESS_RESPONSE = build_success_response_serializer(
    name="ReportSubjectAdminListSuccessResponse",
    data_serializer=ReportSubjectAdminSerializer,
    many=True,
)
SUBJECT_ADMIN_DETAIL_SUCCESS_RESPONSE = build_success_response_serializer(
    name="ReportSubjectAdminDetailSuccessResponse",
    data_serializer=ReportSubjectAdminSerializer,
)

# Report schemas
REPORT_DETAIL_SUCCESS_RESPONSE = build_success_response_serializer(
    name="ReportDetailSuccessResponse",
    data_serializer=ReportDetailSerializer,
)
REPORT_PAGINATED_SUCCESS_RESPONSE = build_paginated_success_response_serializer(
    name="ReportListPaginatedSuccessResponse",
    item_serializer=ReportListSerializer,
)


# ============================================================
# Public Endpoints
# ============================================================


class ReportSubjectListAPIView(APIView):
    """لیست موضوعات گزارش — عمومی."""

    permission_classes = [AllowAny]

    @extend_schema(
        operation_id="reports_subjects_public_list",
        tags=[TAG_REPORTS_PUBLIC],
        summary="لیست موضوعات گزارش",
        description=(
            "دریافت لیست موضوعات فعال برای انتخاب در فرم ثبت گزارش.\n\n"
            "این endpoint بدون pagination است و فقط موضوعات فعال "
            "(با `is_active=True`) را برمی‌گرداند."
        ),
        responses={
            200: SUBJECT_PUBLIC_LIST_SUCCESS_RESPONSE,
        },
    )
    def get(self, request: Request) -> SuccessResponse:
        queryset = get_active_subjects()
        serializer = ReportSubjectPublicSerializer(queryset, many=True)
        return SuccessResponse(
            data=serializer.data,
            message="لیست موضوعات با موفقیت دریافت شد.",
        )


class ReportCreateAPIView(APIView):
    """ثبت گزارش جدید توسط کاربر عمومی."""

    permission_classes = [AllowAny]
    throttle_classes = [ReportCreateAnonThrottle, ReportCreateUserThrottle]

    @extend_schema(
        operation_id="reports_create",
        tags=[TAG_REPORTS_PUBLIC],
        summary="ثبت گزارش مردمی",
        description=(
            "ثبت گزارش جدید توسط کاربر عمومی همراه با پیوست‌های اختیاری.\n\n"
            "**محدودیت‌ها:**\n"
            "- حداکثر ۵ فایل پیوست\n"
            "- فقط jpg/jpeg/png/webp، حداکثر ۵ مگابایت برای هر فایل\n"
            "- ۵ گزارش در دقیقه برای کاربران مهمان\n"
            "- ۲۰ گزارش در دقیقه برای کاربران لاگین کرده"
        ),
        request=ReportCreateSerializer,
        responses={
            201: REPORT_DETAIL_SUCCESS_RESPONSE,
            400: GENERIC_ERROR_RESPONSE,
            429: GENERIC_ERROR_RESPONSE,
        },
    )
    def post(self, request: Request) -> CreatedResponse:
        serializer = ReportCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        submitter_ip = get_client_ip(request)

        report = create_report(
            full_name=serializer.validated_data["full_name"],
            phone_number=serializer.validated_data.get("phone_number"),
            subject=serializer.validated_data["subject"],
            description=serializer.validated_data["description"],
            attachments=serializer.validated_data.get("attachments", []),
            submitter_ip=submitter_ip,
        )

        # Audit — async چون public endpoint با latency sensitivity
        user_id = request.user.pk if request.user.is_authenticated else None
        metadata = extract_audit_metadata(request)
        log_action_async(
            user_id=user_id,
            action=audit_actions.REPORT_CREATED,
            resource_type="report",
            resource_id=str(report.pk),
            extra_data={
                "subject_id": report.subject_id,
                "has_attachments": bool(serializer.validated_data.get("attachments")),
            },
            **metadata,
        )

        return CreatedResponse(
            data=ReportDetailSerializer(report).data,
            message="گزارش شما با موفقیت ثبت شد.",
        )


# ============================================================
# Admin: Subjects CRUD
# ============================================================


class AdminSubjectListCreateAPIView(APIView):
    """لیست تمام موضوعات و ساخت موضوع جدید — ادمین."""

    permission_classes = [IsAdmin]

    @extend_schema(
        operation_id="reports_admin_subjects_list",
        tags=[TAG_REPORTS_ADMIN_SUBJECTS],
        summary="لیست تمام موضوعات گزارش",
        description=(
            "دریافت لیست تمام موضوعات شامل غیرفعال‌ها — برای پنل مدیریت.\n\n"
            "قابل فیلتر بر اساس وضعیت فعال بودن."
        ),
        responses={
            200: SUBJECT_ADMIN_LIST_SUCCESS_RESPONSE,
            403: GENERIC_ERROR_RESPONSE,
        },
    )
    def get(self, request: Request) -> SuccessResponse:
        queryset = get_all_subjects_for_admin()

        filterset = ReportSubjectFilter(request.GET, queryset=queryset)
        if filterset.is_valid():
            queryset = filterset.qs

        serializer = ReportSubjectAdminSerializer(queryset, many=True)
        return SuccessResponse(
            data=serializer.data,
            message="لیست موضوعات با موفقیت دریافت شد.",
        )

    @extend_schema(
        operation_id="reports_admin_subjects_create",
        tags=[TAG_REPORTS_ADMIN_SUBJECTS],
        summary="ساخت موضوع گزارش جدید",
        description="ایجاد یک موضوع جدید برای دسته‌بندی گزارش‌های مردمی.",
        request=ReportSubjectCreateSerializer,
        responses={
            201: SUBJECT_ADMIN_DETAIL_SUCCESS_RESPONSE,
            400: GENERIC_ERROR_RESPONSE,
            403: GENERIC_ERROR_RESPONSE,
        },
    )
    def post(self, request: Request) -> CreatedResponse:
        serializer = ReportSubjectCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        subject = create_subject(
            title=serializer.validated_data["title"],
            description=serializer.validated_data.get("description", ""),
            order=serializer.validated_data.get("order", 0),
        )

        # Audit — async
        metadata = extract_audit_metadata(request)
        log_action_async(
            user_id=request.user.pk,
            action=audit_actions.SUBJECT_CREATED,
            resource_type="report_subject",
            resource_id=str(subject.pk),
            extra_data={"title": subject.title},
            **metadata,
        )

        # re-fetch برای reports_count annotation
        subject = get_subject_by_id_for_admin(subject.id)

        return CreatedResponse(
            data=ReportSubjectAdminSerializer(subject).data,
            message="موضوع جدید با موفقیت ساخته شد.",
        )


class AdminSubjectDetailAPIView(APIView):
    """مشاهده، ویرایش و حذف نرم موضوع — ادمین."""

    permission_classes = [IsAdmin]

    @extend_schema(
        operation_id="reports_admin_subject_retrieve",
        tags=[TAG_REPORTS_ADMIN_SUBJECTS],
        summary="جزئیات یک موضوع",
        description="دریافت جزئیات کامل یک موضوع شامل تعداد گزارش‌های مرتبط.",
        responses={
            200: SUBJECT_ADMIN_DETAIL_SUCCESS_RESPONSE,
            403: GENERIC_ERROR_RESPONSE,
            404: GENERIC_ERROR_RESPONSE,
        },
    )
    def get(
        self,
        request: Request,
        subject_id: int,
    ) -> SuccessResponse | ErrorResponse:
        subject = get_subject_by_id_for_admin(subject_id)
        if not subject:
            return ErrorResponse(
                message="موضوعی با این شناسه یافت نشد.",
                status_code=status.HTTP_404_NOT_FOUND,
            )

        return SuccessResponse(
            data=ReportSubjectAdminSerializer(subject).data,
            message="جزئیات موضوع با موفقیت دریافت شد.",
        )

    @extend_schema(
        operation_id="reports_admin_subject_update",
        tags=[TAG_REPORTS_ADMIN_SUBJECTS],
        summary="ویرایش موضوع",
        description=(
            "ویرایش اطلاعات یک موضوع.\n\n"
            "تمام فیلدها optional هستند — فقط مقادیر ارسالی به‌روزرسانی می‌شوند."
        ),
        request=ReportSubjectUpdateSerializer,
        responses={
            200: SUBJECT_ADMIN_DETAIL_SUCCESS_RESPONSE,
            400: GENERIC_ERROR_RESPONSE,
            403: GENERIC_ERROR_RESPONSE,
            404: GENERIC_ERROR_RESPONSE,
        },
    )
    def patch(
        self,
        request: Request,
        subject_id: int,
    ) -> SuccessResponse | ErrorResponse:
        subject = get_subject_by_id_for_admin(subject_id)
        if not subject:
            return ErrorResponse(
                message="موضوعی با این شناسه یافت نشد.",
                status_code=status.HTTP_404_NOT_FOUND,
            )

        serializer = ReportSubjectUpdateSerializer(data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)

        subject = update_subject(
            subject=subject,
            title=serializer.validated_data.get("title"),
            description=serializer.validated_data.get("description"),
            order=serializer.validated_data.get("order"),
            is_active=serializer.validated_data.get("is_active"),
        )

        # Audit — async
        metadata = extract_audit_metadata(request)
        log_action_async(
            user_id=request.user.pk,
            action=audit_actions.SUBJECT_UPDATED,
            resource_type="report_subject",
            resource_id=str(subject.pk),
            changes={
                field: serializer.validated_data[field]
                for field in serializer.validated_data
            },
            **metadata,
        )

        subject = get_subject_by_id_for_admin(subject.id)

        return SuccessResponse(
            data=ReportSubjectAdminSerializer(subject).data,
            message="موضوع با موفقیت ویرایش شد.",
        )

    @extend_schema(
        operation_id="reports_admin_subject_delete",
        tags=[TAG_REPORTS_ADMIN_SUBJECTS],
        summary="حذف نرم موضوع",
        description=(
            "غیرفعال کردن (soft delete) یک موضوع.\n\n"
            "موضوع از سیستم حذف نمی‌شود ولی دیگر در لیست عمومی نمایش "
            "داده نمی‌شود و گزارش‌های موجود حفظ می‌شوند."
        ),
        responses={
            200: EMPTY_SUCCESS_RESPONSE,
            403: GENERIC_ERROR_RESPONSE,
            404: GENERIC_ERROR_RESPONSE,
        },
    )
    def delete(
        self,
        request: Request,
        subject_id: int,
    ) -> DeletedResponse | ErrorResponse:
        subject = get_subject_by_id_for_admin(subject_id)
        if not subject:
            return ErrorResponse(
                message="موضوعی با این شناسه یافت نشد.",
                status_code=status.HTTP_404_NOT_FOUND,
            )

        delete_subject(subject=subject)

        # Audit — sync چون compliance-critical deletion
        metadata = extract_audit_metadata(request)
        log_action(
            user_id=request.user.pk,
            action=audit_actions.SUBJECT_DELETED,
            resource_type="report_subject",
            resource_id=str(subject_id),
            extra_data={"title": subject.title},
            **metadata,
        )

        return DeletedResponse(message="موضوع با موفقیت غیرفعال شد.")


# ============================================================
# Admin: Reports
# ============================================================


class AdminReportListAPIView(APIView):
    """لیست تمام گزارش‌های دریافتی — ادمین."""

    permission_classes = [IsAdmin]
    pagination_class = StandardPagination

    @extend_schema(
        operation_id="reports_admin_reports_list",
        tags=[TAG_REPORTS_ADMIN_REPORTS],
        summary="لیست گزارشات",
        description=(
            "دریافت لیست تمام گزارش‌های ثبت‌شده با pagination و فیلتر.\n\n"
            "**فیلترهای موجود:**\n"
            "- `status`: pending / reviewing / approved / rejected\n"
            "- `subject`: شناسه موضوع\n"
            "- جستجو در نام، شماره تماس و توضیحات"
        ),
        responses={
            200: REPORT_PAGINATED_SUCCESS_RESPONSE,
            403: GENERIC_ERROR_RESPONSE,
        },
    )
    def get(self, request: Request) -> Response:
        queryset = get_all_reports()

        filterset = ReportFilter(request.query_params, queryset=queryset)
        if filterset.is_valid():
            queryset = filterset.qs

        paginator = self.pagination_class()
        page = paginator.paginate_queryset(queryset, request, view=self)

        if page is not None:
            serializer = ReportListSerializer(page, many=True)
            return paginator.get_paginated_response(
                serializer.data,
                message="لیست گزارشات با موفقیت دریافت شد.",
            )

        return SuccessResponse(
            data=ReportListSerializer(queryset, many=True).data,
            message="لیست گزارشات با موفقیت دریافت شد.",
        )


class AdminReportDetailAPIView(APIView):
    """جزئیات یک گزارش — ادمین."""

    permission_classes = [IsAdmin]

    @extend_schema(
        operation_id="reports_admin_report_retrieve",
        tags=[TAG_REPORTS_ADMIN_REPORTS],
        summary="جزئیات یک گزارش",
        description=(
            "دریافت اطلاعات کامل یک گزارش شامل پیوست‌ها و یادداشت‌های مدیریتی."
        ),
        responses={
            200: REPORT_DETAIL_SUCCESS_RESPONSE,
            403: GENERIC_ERROR_RESPONSE,
            404: GENERIC_ERROR_RESPONSE,
        },
    )
    def get(
        self,
        request: Request,
        report_id: int,
    ) -> SuccessResponse | ErrorResponse:
        report = get_report_by_id(report_id)
        if not report:
            return ErrorResponse(
                message="گزارشی با این شناسه یافت نشد.",
                status_code=status.HTTP_404_NOT_FOUND,
            )

        return SuccessResponse(
            data=ReportDetailSerializer(report).data,
            message="جزئیات گزارش با موفقیت دریافت شد.",
        )


class AdminReportStatusUpdateAPIView(APIView):
    """تغییر وضعیت یک گزارش — ادمین."""

    permission_classes = [IsAdmin]

    @extend_schema(
        operation_id="reports_admin_report_status_update",
        tags=[TAG_REPORTS_ADMIN_REPORTS],
        summary="تغییر وضعیت گزارش",
        description=(
            "تغییر وضعیت یک گزارش به همراه یادداشت اختیاری.\n\n"
            "**وضعیت‌های ممکن:**\n"
            "- `pending`: در انتظار بررسی\n"
            "- `reviewing`: در حال بررسی\n"
            "- `approved`: تأیید شده\n"
            "- `rejected`: رد شده"
        ),
        request=ReportStatusUpdateSerializer,
        responses={
            200: REPORT_DETAIL_SUCCESS_RESPONSE,
            400: GENERIC_ERROR_RESPONSE,
            403: GENERIC_ERROR_RESPONSE,
            404: GENERIC_ERROR_RESPONSE,
        },
    )
    def patch(
        self,
        request: Request,
        report_id: int,
    ) -> SuccessResponse | ErrorResponse:
        report = get_report_by_id(report_id)
        if not report:
            return ErrorResponse(
                message="گزارشی با این شناسه یافت نشد.",
                status_code=status.HTTP_404_NOT_FOUND,
            )

        serializer = ReportStatusUpdateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        old_status = report.status
        new_status = serializer.validated_data["status"]

        report = update_report_status(
            report=report,
            status=new_status,
            admin_note=serializer.validated_data.get("admin_note", ""),
        )

        # Audit — sync چون status change compliance-critical است
        metadata = extract_audit_metadata(request)
        log_action(
            user_id=request.user.pk,
            action=audit_actions.REPORT_STATUS_CHANGED,
            resource_type="report",
            resource_id=str(report.pk),
            changes={
                "status": {"before": old_status, "after": new_status},
            },
            **metadata,
        )

        return SuccessResponse(
            data=ReportDetailSerializer(report).data,
            message="وضعیت گزارش با موفقیت بروزرسانی شد.",
        )

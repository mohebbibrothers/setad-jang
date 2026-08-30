"""گروه دامنه‌ای `views_reports` از views — فاز ۱۱ (تفکیک P3-16).

کلاس‌ها عیناً منتقل شده‌اند؛ مشترکات از views_common؛ نامِ عمومیِ این گروه‌ها را فقط از facade (apps.*.views) یا همین ماژول import کنید.
"""

from __future__ import annotations

from drf_spectacular.utils import (
    extend_schema,
    extend_schema_view,
)
from rest_framework import status
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
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
    R4JReportAdminFilter,
    R4JReportUserFilter,
)
from .permissions import IsR4JAdminUser
from .serializers import (
    R4JAdminReportDetailSerializer,
    R4JAdminReportListSerializer,
    R4JReportCancelActionSerializer,
    R4JReportReviewSerializer,
    R4JReportSubmitSerializer,
    R4JUserReportDetailSerializer,
    R4JUserReportListSerializer,
)
from .services import (
    InvalidReportableField,
    ReportNotCancelable,
    ReportNotInCancelRequested,
    ReportNotReviewable,
)
from .throttles import (
    R4JReportCreateThrottle,
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
# User — Reports (submit + my reports)
# ============================================================


class R4JUserReportSubmitView(APIView):
    """
    ارسال گزارش community توسط کاربر.

    پشتیبانی از دو حالت:
    - JSON: field_changes به‌صورت list مستقیم
    - Multipart: field_changes به‌صورت JSON string + attachments به‌صورت فایل

    endpoint: POST /api/v1/r4j/criminals/{criminal_id}/reports/
    """

    permission_classes = [IsAuthenticated]
    throttle_classes = [R4JReportCreateThrottle]
    parser_classes = [MultiPartParser, FormParser, JSONParser]

    @extend_schema(
        operation_id="r4j_user_report_submit",
        tags=[TAG_R4J_USER],
        summary="ارسال گزارش تکمیلی برای مجرم",
        description=(
            "کاربر لاگین‌کرده می‌تواند گزارشی برای تکمیل یا اصلاح "
            "اطلاعات یک مجرم ارسال کند.\n\n"
            "**حالت JSON:**\n"
            "```json\n"
            "{\n"
            '  "notes": "متن آزاد",\n'
            '  "field_changes": [{"field_name": "city", "suggested_value": "Tehran"}]\n'
            "}\n"
            "```\n\n"
            "**حالت Multipart (با فایل ضمیمه):**\n"
            "- `notes`: string\n"
            "- `field_changes`: JSON string\n"
            "- `attachments`: یک یا چند فایل\n\n"
            "گزارش باید حداقل شامل یک پیشنهاد تغییر فیلد یا یادداشت باشد.\n\n"
            "تا قبل از تأیید ادمین، هیچ تغییری روی پروفایل مجرم اعمال نمی‌شود."
        ),
        request=R4JReportSubmitSerializer,
        responses={
            201: USER_REPORT_DETAIL_RESPONSE,
            400: GENERIC_ERROR_RESPONSE,
            401: GENERIC_ERROR_RESPONSE,
            404: GENERIC_ERROR_RESPONSE,
        },
    )
    def post(self, request: Request, criminal_id: int) -> Response:
        criminal = selectors.get_public_criminal_detail(lookup=criminal_id)
        if criminal is None:
            return ErrorResponse(
                message="مجرمی با این شناسه یافت نشد.",
                status_code=status.HTTP_404_NOT_FOUND,
            )

        serializer = R4JReportSubmitSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        # استخراج فایل‌های ضمیمه از request.FILES
        # کلید 'attachments' می‌تواند چند فایل داشته باشد
        raw_files = request.FILES.getlist("attachments")
        attachments = (
            [{"file": f, "title": f.name, "kind": "document"} for f in raw_files]
            if raw_files
            else None
        )

        try:
            report = services.submit_report(
                criminal=criminal,
                submitted_by=request.user,
                notes=serializer.validated_data.get("notes", ""),
                field_changes=serializer.validated_data.get("field_changes", []),
                attachments=attachments,
                alias_suggestions=serializer.validated_data.get("alias_suggestions", []),
                phone_suggestions=serializer.validated_data.get("phone_suggestions", []),
                social_suggestions=serializer.validated_data.get("social_suggestions", []),
            )
        except InvalidReportableField as exc:
            return ErrorResponse(message=str(exc))

        metadata = extract_audit_metadata(request)
        log_action_async(
            user_id=request.user.pk,
            action=audit_actions.R4J_REPORT_SUBMITTED,
            resource_type="r4j_report",
            resource_id=str(report.pk),
            extra_data={
                "criminal_id": criminal_id,
                "attachment_count": len(raw_files),
            },
            **metadata,
        )

        report_detail = selectors.get_user_report_by_id(
            user_id=request.user.pk,
            report_id=report.pk,
        )

        return CreatedResponse(
            data=R4JUserReportDetailSerializer(report_detail).data,
            message="گزارش شما با موفقیت ثبت شد و در انتظار بررسی است.",
        )


@extend_schema_view(
    get=extend_schema(
        operation_id="r4j_user_my_reports_list",
        tags=[TAG_R4J_USER],
        summary="لیست گزارشات من",
        description="دریافت لیست تمام گزارشاتی که توسط کاربر جاری ارسال شده‌اند.",
        parameters=USER_REPORT_FILTER_PARAMS,
        responses={
            200: USER_REPORT_LIST_RESPONSE,
            401: GENERIC_ERROR_RESPONSE,
        },
    ),
)
class R4JUserMyReportsListView(APIView):
    """لیست گزارشات کاربر جاری."""

    permission_classes = [IsAuthenticated]

    def get(self, request: Request) -> Response:
        queryset = selectors.get_user_reports_queryset(user_id=request.user.pk)
        filterset = R4JReportUserFilter(request.query_params, queryset=queryset)
        if filterset.is_valid():
            queryset = filterset.qs

        paginator = StandardPagination()
        page = paginator.paginate_queryset(queryset, request, view=self)

        if page is not None:
            serializer = R4JUserReportListSerializer(page, many=True)
            return paginator.get_paginated_response(
                serializer.data,
                message="لیست گزارشات با موفقیت دریافت شد.",
            )

        serializer = R4JUserReportListSerializer(queryset, many=True)
        return SuccessResponse(
            data=serializer.data,
            message="لیست گزارشات با موفقیت دریافت شد.",
        )


class R4JUserMyReportDetailView(APIView):
    """جزئیات یک گزارش کاربر + cancel request."""

    permission_classes = [IsAuthenticated]

    @extend_schema(
        operation_id="r4j_user_my_report_retrieve",
        tags=[TAG_R4J_USER],
        summary="جزئیات یک گزارش من",
        responses={
            200: USER_REPORT_DETAIL_RESPONSE,
            401: GENERIC_ERROR_RESPONSE,
            404: GENERIC_ERROR_RESPONSE,
        },
    )
    def get(self, request: Request, report_id: int) -> Response:
        report = selectors.get_user_report_by_id(
            user_id=request.user.pk,
            report_id=report_id,
        )
        if report is None:
            return ErrorResponse(
                message="گزارشی با این شناسه یافت نشد.",
                status_code=status.HTTP_404_NOT_FOUND,
            )
        return SuccessResponse(
            data=R4JUserReportDetailSerializer(report).data,
            message="جزئیات گزارش با موفقیت دریافت شد.",
        )


class R4JUserReportCancelView(APIView):
    """
    درخواست لغو گزارش توسط کاربر.

    endpoint: POST /api/v1/r4j/me/reports/{report_id}/cancel/
    """

    permission_classes = [IsAuthenticated]

    @extend_schema(
        operation_id="r4j_user_report_cancel",
        tags=[TAG_R4J_USER],
        summary="درخواست لغو گزارش",
        description=(
            "کاربر می‌تواند درخواست لغو گزارشی که ارسال کرده را بدهد.\n\n"
            "فقط گزارش‌هایی که در وضعیت «در انتظار بررسی» هستند قابل لغو می‌باشند.\n\n"
            "درخواست لغو باید توسط ادمین تأیید یا رد شود."
        ),
        request=None,
        responses={
            200: USER_REPORT_DETAIL_RESPONSE,
            400: GENERIC_ERROR_RESPONSE,
            401: GENERIC_ERROR_RESPONSE,
            404: GENERIC_ERROR_RESPONSE,
        },
    )
    def post(self, request: Request, report_id: int) -> Response:
        report = selectors.get_user_report_by_id(
            user_id=request.user.pk,
            report_id=report_id,
        )
        if report is None:
            return ErrorResponse(
                message="گزارشی با این شناسه یافت نشد.",
                status_code=status.HTTP_404_NOT_FOUND,
            )

        try:
            report = services.request_report_cancel(
                report=report,
                user=request.user,
            )
        except ReportNotCancelable as exc:
            return ErrorResponse(message=str(exc))

        metadata = extract_audit_metadata(request)
        log_action_async(
            user_id=request.user.pk,
            action=audit_actions.R4J_REPORT_CANCEL_REQUESTED,
            resource_type="r4j_report",
            resource_id=str(report.pk),
            **metadata,
        )

        report_refreshed = selectors.get_user_report_by_id(
            user_id=request.user.pk,
            report_id=report.pk,
        )

        return SuccessResponse(
            data=R4JUserReportDetailSerializer(report_refreshed).data,
            message="درخواست لغو گزارش با موفقیت ثبت شد.",
        )


# ============================================================
# Admin — Reports
# ============================================================


@extend_schema_view(
    get=extend_schema(
        operation_id="r4j_admin_reports_list",
        tags=[TAG_R4J_ADMIN],
        summary="لیست گزارشات — ادمین",
        description="دریافت لیست تمام گزارشات با امکان فیلتر کامل.",
        parameters=ADMIN_REPORT_FILTER_PARAMS,
        responses={
            200: ADMIN_REPORT_LIST_RESPONSE,
            403: GENERIC_ERROR_RESPONSE,
        },
    ),
)
class R4JAdminReportListView(APIView):
    """لیست همه گزارشات — admin."""

    permission_classes = [IsR4JAdminUser]

    def get(self, request: Request) -> Response:
        queryset = selectors.get_admin_reports_queryset()
        filterset = R4JReportAdminFilter(request.query_params, queryset=queryset)
        if filterset.is_valid():
            queryset = filterset.qs

        paginator = StandardPagination()
        page = paginator.paginate_queryset(queryset, request, view=self)

        if page is not None:
            serializer = R4JAdminReportListSerializer(page, many=True)
            return paginator.get_paginated_response(
                serializer.data,
                message="لیست گزارشات با موفقیت دریافت شد.",
            )

        serializer = R4JAdminReportListSerializer(queryset, many=True)
        return SuccessResponse(
            data=serializer.data,
            message="لیست گزارشات با موفقیت دریافت شد.",
        )


class R4JAdminReportDetailView(APIView):
    """جزئیات یک گزارش — admin."""

    permission_classes = [IsR4JAdminUser]

    @extend_schema(
        operation_id="r4j_admin_report_retrieve",
        tags=[TAG_R4J_ADMIN],
        summary="جزئیات گزارش — ادمین",
        responses={
            200: ADMIN_REPORT_DETAIL_RESPONSE,
            403: GENERIC_ERROR_RESPONSE,
            404: GENERIC_ERROR_RESPONSE,
        },
    )
    def get(self, request: Request, report_id: int) -> Response:
        report = selectors.get_admin_report_by_id(report_id=report_id)
        if report is None:
            return ErrorResponse(
                message="گزارشی با این شناسه یافت نشد.",
                status_code=status.HTTP_404_NOT_FOUND,
            )
        return SuccessResponse(
            data=R4JAdminReportDetailSerializer(report).data,
            message="جزئیات گزارش با موفقیت دریافت شد.",
        )


class R4JAdminReportReviewView(APIView):
    """
    بررسی گزارش توسط ادمین — per-field approve/reject + apply.

    endpoint: POST /api/v1/r4j/admin/reports/{report_id}/review/
    """

    permission_classes = [IsR4JAdminUser]

    @extend_schema(
        operation_id="r4j_admin_report_review",
        tags=[TAG_R4J_ADMIN],
        summary="بررسی گزارش — ادمین",
        description=(
            "ادمین می‌تواند برای هر فیلد گزارش به‌صورت مستقل تصمیم بگیرد.\n\n"
            "بعد از review:\n"
            "- اگر همه field_changeها approve شوند → وضعیت APPROVED\n"
            "- اگر برخی approve شوند → وضعیت PARTIALLY_APPROVED\n"
            "- اگر هیچ‌کدام approve نشوند → وضعیت REJECTED\n\n"
            "تغییرات approved بلافاصله روی پروفایل مجرم اعمال می‌شوند."
        ),
        request=R4JReportReviewSerializer,
        responses={
            200: ADMIN_REPORT_DETAIL_RESPONSE,
            400: GENERIC_ERROR_RESPONSE,
            403: GENERIC_ERROR_RESPONSE,
            404: GENERIC_ERROR_RESPONSE,
        },
    )
    def post(self, request: Request, report_id: int) -> Response:
        report = selectors.get_admin_report_by_id(report_id=report_id)
        if report is None:
            return ErrorResponse(
                message="گزارشی با این شناسه یافت نشد.",
                status_code=status.HTTP_404_NOT_FOUND,
            )

        serializer = R4JReportReviewSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        try:
            report = services.review_report(
                report=report,
                reviewed_by=request.user,
                field_decisions=serializer.validated_data.get("field_decisions", []),
                alias_decisions=serializer.validated_data.get("alias_decisions", []),
                phone_decisions=serializer.validated_data.get("phone_decisions", []),
                social_decisions=serializer.validated_data.get("social_decisions", []),
                attachment_decisions=serializer.validated_data.get("attachment_decisions", []),
                admin_note=serializer.validated_data.get("admin_note", ""),
            )
        except ReportNotReviewable as exc:
            return ErrorResponse(message=str(exc))

        metadata = extract_audit_metadata(request)
        log_action_async(
            user_id=request.user.pk,
            action=audit_actions.R4J_REPORT_REVIEWED,
            resource_type="r4j_report",
            resource_id=str(report.pk),
            extra_data={"final_status": report.status},
            **metadata,
        )

        report_refreshed = selectors.get_admin_report_by_id(report_id=report.pk)

        return SuccessResponse(
            data=R4JAdminReportDetailSerializer(report_refreshed).data,
            message="گزارش با موفقیت بررسی شد.",
        )


class R4JAdminReportCancelApproveView(APIView):
    """
    تأیید درخواست لغو گزارش توسط ادمین.

    endpoint: POST /api/v1/r4j/admin/reports/{report_id}/cancel/approve/
    """

    permission_classes = [IsR4JAdminUser]

    @extend_schema(
        operation_id="r4j_admin_report_cancel_approve",
        tags=[TAG_R4J_ADMIN],
        summary="تأیید درخواست لغو گزارش — ادمین",
        request=R4JReportCancelActionSerializer,
        responses={
            200: ADMIN_REPORT_DETAIL_RESPONSE,
            400: GENERIC_ERROR_RESPONSE,
            403: GENERIC_ERROR_RESPONSE,
            404: GENERIC_ERROR_RESPONSE,
        },
    )
    def post(self, request: Request, report_id: int) -> Response:
        report = selectors.get_admin_report_by_id(report_id=report_id)
        if report is None:
            return ErrorResponse(
                message="گزارشی با این شناسه یافت نشد.",
                status_code=status.HTTP_404_NOT_FOUND,
            )

        serializer = R4JReportCancelActionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        try:
            report = services.approve_report_cancel(
                report=report,
                admin=request.user,
                admin_note=serializer.validated_data.get("admin_note", ""),
            )
        except ReportNotInCancelRequested as exc:
            return ErrorResponse(message=str(exc))

        metadata = extract_audit_metadata(request)
        log_action_async(
            user_id=request.user.pk,
            action=audit_actions.R4J_REPORT_CANCEL_APPROVED,
            resource_type="r4j_report",
            resource_id=str(report.pk),
            **metadata,
        )

        report_refreshed = selectors.get_admin_report_by_id(report_id=report.pk)

        return SuccessResponse(
            data=R4JAdminReportDetailSerializer(report_refreshed).data,
            message="درخواست لغو گزارش تأیید شد.",
        )


class R4JAdminReportCancelRejectView(APIView):
    """
    رد درخواست لغو گزارش توسط ادمین.

    endpoint: POST /api/v1/r4j/admin/reports/{report_id}/cancel/reject/
    """

    permission_classes = [IsR4JAdminUser]

    @extend_schema(
        operation_id="r4j_admin_report_cancel_reject",
        tags=[TAG_R4J_ADMIN],
        summary="رد درخواست لغو گزارش — ادمین",
        request=R4JReportCancelActionSerializer,
        responses={
            200: ADMIN_REPORT_DETAIL_RESPONSE,
            400: GENERIC_ERROR_RESPONSE,
            403: GENERIC_ERROR_RESPONSE,
            404: GENERIC_ERROR_RESPONSE,
        },
    )
    def post(self, request: Request, report_id: int) -> Response:
        report = selectors.get_admin_report_by_id(report_id=report_id)
        if report is None:
            return ErrorResponse(
                message="گزارشی با این شناسه یافت نشد.",
                status_code=status.HTTP_404_NOT_FOUND,
            )

        serializer = R4JReportCancelActionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        try:
            report = services.reject_report_cancel(
                report=report,
                admin=request.user,
                admin_note=serializer.validated_data.get("admin_note", ""),
            )
        except ReportNotInCancelRequested as exc:
            return ErrorResponse(message=str(exc))

        metadata = extract_audit_metadata(request)
        log_action_async(
            user_id=request.user.pk,
            action=audit_actions.R4J_REPORT_CANCEL_REJECTED,
            resource_type="r4j_report",
            resource_id=str(report.pk),
            **metadata,
        )

        report_refreshed = selectors.get_admin_report_by_id(report_id=report.pk)

        return SuccessResponse(
            data=R4JAdminReportDetailSerializer(report_refreshed).data,
            message="درخواست لغو گزارش رد شد و گزارش به وضعیت در انتظار بررسی بازگشت.",
        )

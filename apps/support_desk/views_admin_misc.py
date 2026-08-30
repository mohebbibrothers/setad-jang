"""گروه دامنه‌ای `views_admin_misc` از views — فاز ۱۱ (تفکیک P3-16).

کلاس‌ها عیناً منتقل شده‌اند؛ مشترکات از views_common؛ نامِ عمومیِ این گروه‌ها را فقط از facade (apps.*.views) یا همین ماژول import کنید.
"""

from __future__ import annotations

from django.http import HttpResponse
from drf_spectacular.utils import extend_schema
from rest_framework import status
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.audit_logs import actions as audit_actions
from apps.audit_logs.helpers import extract_audit_metadata
from apps.audit_logs.services import log_action_async
from apps.core.pagination import StandardPagination
from apps.core.responses import ErrorResponse, SuccessResponse
from apps.core.views import paginated_list_response
from apps.support_desk import selectors, services
from apps.support_desk.export import (
    build_csat_workbook,
    build_messages_workbook,
    build_sla_workbook,
    build_support_export_filename,
)
from apps.support_desk.filters import (
    SupportDuplicateCandidateAdminFilter,
)
from apps.support_desk.permissions import IsSupportAdminUser
from apps.support_desk.serializers import (
    SupportAdminAnalyticsSerializer,
    SupportDuplicateCandidateSerializer,
    SupportDuplicateReviewSerializer,
)

from .views_common import (  # noqa: F401 — re-exportِ رایگان برای بدنه‌های منتقل‌شده
    ADMIN_ANALYTICS_RESPONSE,
    ADMIN_CANNED_RESPONSE,
    ADMIN_CATEGORY_RESPONSE,
    ADMIN_DEPARTMENT_RESPONSE,
    ADMIN_DUPLICATE_RESPONSE,
    ADMIN_SLA_RESPONSE,
    ADMIN_TICKET_DETAIL_RESPONSE,
    ADMIN_TICKET_LIST_RESPONSE,
    ADMIN_TICKET_TYPE_RESPONSE,
    ASSIGNMENT_RECOMMENDATION_RESPONSE,
    ATTACHMENT_RESPONSE,
    CATEGORY_LIST_RESPONSE,
    DEPARTMENT_LIST_RESPONSE,
    KNOWLEDGE_ARTICLE_DETAIL_RESPONSE,
    KNOWLEDGE_ARTICLE_LIST_RESPONSE,
    KNOWLEDGE_ARTICLE_USE_RESPONSE,
    MESSAGE_LIST_RESPONSE,
    SMART_REPLY_BUNDLE_RESPONSE,
    SUPPORT_ERROR_RESPONSE,
    TAG_SUPPORT_TAXONOMY,
    TAG_SUPPORT_USER,
    TICKET_DETAIL_RESPONSE,
    TICKET_LIST_RESPONSE,
    TICKET_TYPE_LIST_RESPONSE,
    TRIAGE_RESPONSE,
    _get_user_ticket_or_error,
    _serialize_assignment_recommendation,
    _serialize_smart_reply_bundle,
    _service_error_response,
)


class SupportAdminDuplicateCandidateListView(APIView):
    """Admin duplicate candidate list endpoint."""

    permission_classes = [IsSupportAdminUser]
    serializer_class = SupportDuplicateCandidateSerializer

    def get(self, request: Request) -> Response:
        """Return duplicate candidates."""
        return paginated_list_response(
            request=request,
            view=self,
            queryset=selectors.get_admin_duplicate_candidates(),
            serializer_class=SupportDuplicateCandidateSerializer,
            pagination_class=StandardPagination,
            filterset_class=SupportDuplicateCandidateAdminFilter,
        )


class SupportAdminDuplicateCandidateReviewView(APIView):
    """Admin duplicate candidate review endpoint."""

    permission_classes = [IsSupportAdminUser]
    serializer_class = SupportDuplicateCandidateSerializer

    def post(self, request: Request, duplicate_id: int) -> SuccessResponse | ErrorResponse:
        """Review duplicate candidate."""
        duplicate = selectors.get_admin_duplicate_candidate_by_id(duplicate_id=duplicate_id)
        if duplicate is None:
            return ErrorResponse(
                message="کاندیدای تکراری یافت نشد.", status_code=status.HTTP_404_NOT_FOUND
            )
        serializer = SupportDuplicateReviewSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        duplicate = services.review_duplicate_candidate(
            duplicate=duplicate, admin=request.user, **serializer.validated_data
        )
        log_action_async(
            user_id=request.user.pk,
            action=audit_actions.SUPPORT_DUPLICATE_REVIEWED,
            resource_type="support_duplicate_candidate",
            resource_id=str(duplicate.pk),
            **extract_audit_metadata(request),
        )
        return SuccessResponse(
            data=SupportDuplicateCandidateSerializer(duplicate).data,
            message="وضعیت کاندیدای تکراری بروزرسانی شد.",
        )


class SupportAdminAnalyticsView(APIView):
    """Admin support analytics dashboard."""

    permission_classes = [IsSupportAdminUser]
    serializer_class = SupportAdminAnalyticsSerializer

    @extend_schema(
        operation_id="support_admin_analytics",
        tags=[TAG_SUPPORT_USER],
        responses={200: ADMIN_ANALYTICS_RESPONSE},
    )
    def get(self, request: Request) -> SuccessResponse:
        """Return support desk analytics summary."""
        return SuccessResponse(
            data=services.get_admin_analytics_summary(),
            message="گزارش تحلیلی میز پشتیبانی دریافت شد.",
        )


class SupportAdminMessageExportView(APIView):
    """Admin Excel export for support messages."""

    permission_classes = [IsSupportAdminUser]

    @extend_schema(
        operation_id="support_admin_export_messages", tags=[TAG_SUPPORT_USER], responses={200: None}
    )
    def get(self, request: Request) -> HttpResponse:
        """Export timeline messages as an RTL Excel workbook."""
        workbook = build_messages_workbook(messages=selectors.get_admin_messages())
        filename = build_support_export_filename(export_type="messages")
        log_action_async(
            user_id=request.user.pk,
            action=audit_actions.SUPPORT_EXPORT_GENERATED,
            resource_type="support_ticket_message",
            resource_id="bulk",
            extra_data={"filename": filename, "export_type": "messages"},
            **extract_audit_metadata(request),
        )
        response = HttpResponse(
            workbook.getvalue(),
            content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
        response["Content-Disposition"] = f'attachment; filename="{filename}"'
        return response


class SupportAdminSLAExportView(APIView):
    """Admin Excel export for SLA reporting."""

    permission_classes = [IsSupportAdminUser]

    @extend_schema(
        operation_id="support_admin_export_sla", tags=[TAG_SUPPORT_USER], responses={200: None}
    )
    def get(self, request: Request) -> HttpResponse:
        """Export SLA ticket data as an RTL Excel workbook."""
        workbook = build_sla_workbook(tickets=selectors.get_admin_sla_tickets())
        filename = build_support_export_filename(export_type="sla")
        log_action_async(
            user_id=request.user.pk,
            action=audit_actions.SUPPORT_EXPORT_GENERATED,
            resource_type="support_sla",
            resource_id="bulk",
            extra_data={"filename": filename, "export_type": "sla"},
            **extract_audit_metadata(request),
        )
        response = HttpResponse(
            workbook.getvalue(),
            content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
        response["Content-Disposition"] = f'attachment; filename="{filename}"'
        return response


class SupportAdminCSATExportView(APIView):
    """Admin Excel export for CSAT ratings."""

    permission_classes = [IsSupportAdminUser]

    @extend_schema(
        operation_id="support_admin_export_csat", tags=[TAG_SUPPORT_USER], responses={200: None}
    )
    def get(self, request: Request) -> HttpResponse:
        """Export CSAT data as an RTL Excel workbook."""
        workbook = build_csat_workbook(ratings=selectors.get_admin_satisfaction_ratings())
        filename = build_support_export_filename(export_type="csat")
        log_action_async(
            user_id=request.user.pk,
            action=audit_actions.SUPPORT_EXPORT_GENERATED,
            resource_type="support_csat",
            resource_id="bulk",
            extra_data={"filename": filename, "export_type": "csat"},
            **extract_audit_metadata(request),
        )
        response = HttpResponse(
            workbook.getvalue(),
            content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
        response["Content-Disposition"] = f'attachment; filename="{filename}"'
        return response

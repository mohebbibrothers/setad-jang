"""گروه دامنه‌ای `views_admin_tickets` از views — فاز ۱۱ (تفکیک P3-16).

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
from apps.core.responses import CreatedResponse, ErrorResponse, SuccessResponse
from apps.core.schemas import (
    build_success_response_serializer,
)
from apps.core.views import paginated_list_response
from apps.support_desk import selectors, services
from apps.support_desk.export import (
    build_support_export_filename,
    build_tickets_workbook,
)
from apps.support_desk.filters import (
    SupportAdminTicketFilter,
)
from apps.support_desk.permissions import IsSupportAdminUser
from apps.support_desk.serializers import (
    SupportAdminAssignSerializer,
    SupportAdminReasonSerializer,
    SupportAdminStatusSerializer,
    SupportAdminTicketDetailSerializer,
    SupportAdminTicketMessageSerializer,
    SupportAssignmentRecommendationSerializer,
    SupportSmartReplyBundleSerializer,
    SupportSmartReplyUseSerializer,
    SupportTicketListSerializer,
    SupportTicketReplySerializer,
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


class SupportAdminTicketListView(APIView):
    """Admin ticket queue endpoint."""

    permission_classes = [IsSupportAdminUser]
    serializer_class = SupportTicketListSerializer

    @extend_schema(
        operation_id="support_admin_tickets_list",
        tags=[TAG_SUPPORT_USER],
        responses={200: ADMIN_TICKET_LIST_RESPONSE},
    )
    def get(self, request: Request) -> Response:
        """Return filtered admin ticket queue."""
        return paginated_list_response(
            request=request,
            view=self,
            queryset=selectors.get_admin_tickets(),
            serializer_class=SupportTicketListSerializer,
            pagination_class=StandardPagination,
            filterset_class=SupportAdminTicketFilter,
        )


class SupportAdminTicketDetailView(APIView):
    """Admin ticket detail endpoint."""

    permission_classes = [IsSupportAdminUser]
    serializer_class = SupportAdminTicketDetailSerializer

    @extend_schema(
        operation_id="support_admin_tickets_retrieve",
        tags=[TAG_SUPPORT_USER],
        responses={200: ADMIN_TICKET_DETAIL_RESPONSE, 404: SUPPORT_ERROR_RESPONSE},
    )
    def get(self, request: Request, ticket_number: str) -> SuccessResponse | ErrorResponse:
        """Return ticket with internal timeline."""
        ticket = selectors.get_admin_ticket_by_number(ticket_number=ticket_number)
        if ticket is None:
            return ErrorResponse(message="تیکت یافت نشد.", status_code=status.HTTP_404_NOT_FOUND)
        return SuccessResponse(data=SupportAdminTicketDetailSerializer(ticket).data)


class SupportAdminTicketReplyView(APIView):
    """Admin public reply endpoint."""

    permission_classes = [IsSupportAdminUser]
    serializer_class = SupportAdminTicketMessageSerializer

    def post(self, request: Request, ticket_number: str) -> CreatedResponse | ErrorResponse:
        """Add admin public reply."""
        ticket = selectors.get_admin_ticket_by_number(ticket_number=ticket_number)
        if ticket is None:
            return ErrorResponse(message="تیکت یافت نشد.", status_code=status.HTTP_404_NOT_FOUND)
        serializer = SupportTicketReplySerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            message = services.add_admin_reply(
                ticket=ticket, admin=request.user, **serializer.validated_data
            )
        except (services.SupportPermissionError, services.SupportTicketStateError) as exc:
            return _service_error_response(exc, status_code=status.HTTP_403_FORBIDDEN)
        log_action_async(
            user_id=request.user.pk,
            action=audit_actions.SUPPORT_TICKET_REPLIED,
            resource_type="support_ticket",
            resource_id=ticket.ticket_number,
            **extract_audit_metadata(request),
        )
        return CreatedResponse(
            data=SupportAdminTicketMessageSerializer(message).data, message="پاسخ ادمین ثبت شد."
        )


class SupportAdminTicketInternalNoteView(APIView):
    """Admin internal note endpoint."""

    permission_classes = [IsSupportAdminUser]
    serializer_class = SupportAdminTicketMessageSerializer

    def post(self, request: Request, ticket_number: str) -> CreatedResponse | ErrorResponse:
        """Add internal note."""
        ticket = selectors.get_admin_ticket_by_number(ticket_number=ticket_number)
        if ticket is None:
            return ErrorResponse(message="تیکت یافت نشد.", status_code=status.HTTP_404_NOT_FOUND)
        serializer = SupportTicketReplySerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        message = services.add_internal_note(
            ticket=ticket, admin=request.user, **serializer.validated_data
        )
        log_action_async(
            user_id=request.user.pk,
            action=audit_actions.SUPPORT_TICKET_INTERNAL_NOTE_ADDED,
            resource_type="support_ticket",
            resource_id=ticket.ticket_number,
            **extract_audit_metadata(request),
        )
        return CreatedResponse(
            data=SupportAdminTicketMessageSerializer(message).data, message="یادداشت داخلی ثبت شد."
        )


class SupportAdminTicketAssignView(APIView):
    """Admin ticket assignment endpoint."""

    permission_classes = [IsSupportAdminUser]
    serializer_class = SupportAdminTicketDetailSerializer

    def post(self, request: Request, ticket_number: str) -> SuccessResponse | ErrorResponse:
        """Assign ticket to admin/department."""
        ticket = selectors.get_admin_ticket_by_number(ticket_number=ticket_number)
        if ticket is None:
            return ErrorResponse(message="تیکت یافت نشد.", status_code=status.HTTP_404_NOT_FOUND)
        serializer = SupportAdminAssignSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        ticket = services.assign_ticket(
            ticket=ticket, admin=request.user, **serializer.validated_data
        )
        log_action_async(
            user_id=request.user.pk,
            action=audit_actions.SUPPORT_TICKET_ASSIGNED,
            resource_type="support_ticket",
            resource_id=ticket.ticket_number,
            **extract_audit_metadata(request),
        )
        return SuccessResponse(
            data=SupportAdminTicketDetailSerializer(ticket).data, message="تیکت ارجاع شد."
        )


class SupportAdminTicketAssignmentRecommendationView(APIView):
    """Admin endpoint for load-balanced support assignment recommendation."""

    permission_classes = [IsSupportAdminUser]
    serializer_class = SupportAssignmentRecommendationSerializer

    @extend_schema(
        operation_id="support_admin_ticket_assignment_recommendation",
        tags=[TAG_SUPPORT_USER],
        responses={200: ASSIGNMENT_RECOMMENDATION_RESPONSE, 404: SUPPORT_ERROR_RESPONSE},
    )
    def get(self, request: Request, ticket_number: str) -> SuccessResponse | ErrorResponse:
        """Return transparent least-loaded assignment recommendation."""
        ticket = selectors.get_admin_ticket_by_number(ticket_number=ticket_number)
        if ticket is None:
            return ErrorResponse(message="تیکت یافت نشد.", status_code=status.HTTP_404_NOT_FOUND)
        recommendation = services.get_support_assignment_recommendation(ticket=ticket)
        payload = _serialize_assignment_recommendation(recommendation)
        log_action_async(
            user_id=request.user.pk,
            action=audit_actions.SUPPORT_ASSIGNMENT_RECOMMENDED,
            resource_type="support_ticket",
            resource_id=ticket.ticket_number,
            extra_data={
                "recommended_assignee_id": payload["recommended_assignee_id"],
                "policy_version": payload["policy_version"],
            },
            **extract_audit_metadata(request),
        )
        return SuccessResponse(data=payload, message="پیشنهاد ارجاع تیکت با موفقیت تولید شد.")


class SupportAdminTicketAutoAssignView(APIView):
    """Admin endpoint that applies load-balanced assignment recommendation."""

    permission_classes = [IsSupportAdminUser]
    serializer_class = SupportAdminTicketDetailSerializer

    @extend_schema(
        operation_id="support_admin_ticket_auto_assign",
        tags=[TAG_SUPPORT_USER],
        request=SupportAdminAssignSerializer,
        responses={
            200: TICKET_DETAIL_RESPONSE,
            400: SUPPORT_ERROR_RESPONSE,
            404: SUPPORT_ERROR_RESPONSE,
        },
    )
    def post(self, request: Request, ticket_number: str) -> SuccessResponse | ErrorResponse:
        """Auto-assign ticket to the least-loaded support admin."""
        ticket = selectors.get_admin_ticket_by_number(ticket_number=ticket_number)
        if ticket is None:
            return ErrorResponse(message="تیکت یافت نشد.", status_code=status.HTTP_404_NOT_FOUND)
        serializer = SupportAdminAssignSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            ticket = services.auto_assign_ticket(
                ticket=ticket,
                admin=request.user,
                department=serializer.validated_data.get("department"),
                reason=serializer.validated_data.get("reason", ""),
            )
        except services.SupportDeskServiceError as exc:
            return _service_error_response(exc)
        log_action_async(
            user_id=request.user.pk,
            action=audit_actions.SUPPORT_TICKET_ASSIGNED,
            resource_type="support_ticket",
            resource_id=ticket.ticket_number,
            extra_data={"auto_assigned": True, "assigned_to_id": ticket.assigned_to_id},
            **extract_audit_metadata(request),
        )
        return SuccessResponse(
            data=SupportAdminTicketDetailSerializer(ticket).data,
            message="تیکت به‌صورت خودکار ارجاع شد.",
        )


class SupportAdminTicketSmartReplyView(APIView):
    """Admin endpoint for safe smart reply suggestions."""

    permission_classes = [IsSupportAdminUser]
    serializer_class = SupportSmartReplyBundleSerializer

    @extend_schema(
        operation_id="support_admin_ticket_smart_replies",
        tags=[TAG_SUPPORT_USER],
        responses={200: SMART_REPLY_BUNDLE_RESPONSE, 404: SUPPORT_ERROR_RESPONSE},
    )
    def get(self, request: Request, ticket_number: str) -> SuccessResponse | ErrorResponse:
        """Generate smart reply suggestions from KB/canned responses/public timeline."""
        ticket = selectors.get_admin_ticket_by_number(ticket_number=ticket_number)
        if ticket is None:
            return ErrorResponse(message="تیکت یافت نشد.", status_code=status.HTTP_404_NOT_FOUND)
        bundle = services.generate_smart_reply_suggestions(ticket=ticket)
        payload = _serialize_smart_reply_bundle(bundle)
        log_action_async(
            user_id=request.user.pk,
            action=audit_actions.SUPPORT_SMART_REPLY_SUGGESTED,
            resource_type="support_ticket",
            resource_id=ticket.ticket_number,
            extra_data={
                "suggestions_count": len(payload["suggestions"]),
                "policy_version": payload["policy_version"],
            },
            **extract_audit_metadata(request),
        )
        return SuccessResponse(data=payload, message="پیشنهادهای پاسخ هوشمند با موفقیت تولید شد.")


class SupportAdminTicketSmartReplyUseView(APIView):
    """Admin endpoint to send a reviewed smart reply suggestion."""

    permission_classes = [IsSupportAdminUser]
    serializer_class = SupportAdminTicketMessageSerializer

    @extend_schema(
        operation_id="support_admin_ticket_smart_reply_use",
        tags=[TAG_SUPPORT_USER],
        request=SupportSmartReplyUseSerializer,
        responses={
            201: build_success_response_serializer(
                name="SupportSmartReplyUseResponse",
                data_serializer=SupportAdminTicketMessageSerializer,
            ),
            403: SUPPORT_ERROR_RESPONSE,
            404: SUPPORT_ERROR_RESPONSE,
        },
    )
    def post(self, request: Request, ticket_number: str) -> CreatedResponse | ErrorResponse:
        """Send reviewed smart reply body as an admin reply and audit source metadata."""
        ticket = selectors.get_admin_ticket_by_number(ticket_number=ticket_number)
        if ticket is None:
            return ErrorResponse(message="تیکت یافت نشد.", status_code=status.HTTP_404_NOT_FOUND)
        serializer = SupportSmartReplyUseSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            message = services.add_admin_reply(
                ticket=ticket, admin=request.user, body=serializer.validated_data["body"]
            )
        except (services.SupportPermissionError, services.SupportTicketStateError) as exc:
            return _service_error_response(exc, status_code=status.HTTP_403_FORBIDDEN)
        source_type = serializer.validated_data.get("source_type", "")
        source_id = serializer.validated_data.get("source_id")
        if source_type == "knowledge_article" and source_id:
            article = selectors.get_admin_knowledge_article_by_id(article_id=source_id)
            if article is not None:
                services.record_knowledge_article_use(
                    article=article, user=request.user, ticket=ticket, context="smart_reply"
                )
        log_action_async(
            user_id=request.user.pk,
            action=audit_actions.SUPPORT_SMART_REPLY_USED,
            resource_type="support_ticket",
            resource_id=ticket.ticket_number,
            extra_data={
                "source_type": source_type,
                "source_id": source_id,
                "message_id": message.pk,
            },
            **extract_audit_metadata(request),
        )
        log_action_async(
            user_id=request.user.pk,
            action=audit_actions.SUPPORT_TICKET_REPLIED,
            resource_type="support_ticket",
            resource_id=ticket.ticket_number,
            **extract_audit_metadata(request),
        )
        return CreatedResponse(
            data=SupportAdminTicketMessageSerializer(message).data,
            message="پاسخ هوشمند بازبینی‌شده ارسال شد.",
        )


class SupportAdminTicketStatusView(APIView):
    """Admin ticket status endpoint."""

    permission_classes = [IsSupportAdminUser]
    serializer_class = SupportAdminTicketDetailSerializer

    def post(self, request: Request, ticket_number: str) -> SuccessResponse | ErrorResponse:
        """Change ticket status."""
        ticket = selectors.get_admin_ticket_by_number(ticket_number=ticket_number)
        if ticket is None:
            return ErrorResponse(message="تیکت یافت نشد.", status_code=status.HTTP_404_NOT_FOUND)
        serializer = SupportAdminStatusSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        ticket = services.change_ticket_status(
            ticket=ticket, admin=request.user, **serializer.validated_data
        )
        log_action_async(
            user_id=request.user.pk,
            action=audit_actions.SUPPORT_TICKET_STATUS_CHANGED,
            resource_type="support_ticket",
            resource_id=ticket.ticket_number,
            **extract_audit_metadata(request),
        )
        return SuccessResponse(
            data=SupportAdminTicketDetailSerializer(ticket).data, message="وضعیت تیکت تغییر کرد."
        )


class SupportAdminTicketEscalateView(APIView):
    """Admin ticket escalation endpoint."""

    permission_classes = [IsSupportAdminUser]
    serializer_class = SupportAdminTicketDetailSerializer

    def post(self, request: Request, ticket_number: str) -> SuccessResponse | ErrorResponse:
        """Escalate ticket."""
        ticket = selectors.get_admin_ticket_by_number(ticket_number=ticket_number)
        if ticket is None:
            return ErrorResponse(message="تیکت یافت نشد.", status_code=status.HTTP_404_NOT_FOUND)
        serializer = SupportAdminReasonSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        ticket = services.escalate_ticket(
            ticket=ticket,
            admin=request.user,
            reason=serializer.validated_data.get("reason", "ارجاع فوری"),
        )
        log_action_async(
            user_id=request.user.pk,
            action=audit_actions.SUPPORT_TICKET_ESCALATED,
            resource_type="support_ticket",
            resource_id=ticket.ticket_number,
            **extract_audit_metadata(request),
        )
        return SuccessResponse(
            data=SupportAdminTicketDetailSerializer(ticket).data, message="تیکت ارجاع فوری شد."
        )


class SupportAdminTicketCloseView(APIView):
    """Admin ticket close endpoint."""

    permission_classes = [IsSupportAdminUser]
    serializer_class = SupportAdminTicketDetailSerializer

    def post(self, request: Request, ticket_number: str) -> SuccessResponse | ErrorResponse:
        """Close ticket by admin."""
        ticket = selectors.get_admin_ticket_by_number(ticket_number=ticket_number)
        if ticket is None:
            return ErrorResponse(message="تیکت یافت نشد.", status_code=status.HTTP_404_NOT_FOUND)
        serializer = SupportAdminReasonSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            ticket = services.close_ticket(
                ticket=ticket,
                actor=request.user,
                reason=serializer.validated_data.get("reason", ""),
            )
        except (services.SupportPermissionError, services.SupportTicketStateError) as exc:
            return _service_error_response(exc, status_code=status.HTTP_403_FORBIDDEN)
        log_action_async(
            user_id=request.user.pk,
            action=audit_actions.SUPPORT_TICKET_CLOSED,
            resource_type="support_ticket",
            resource_id=ticket.ticket_number,
            **extract_audit_metadata(request),
        )
        return SuccessResponse(
            data=SupportAdminTicketDetailSerializer(ticket).data, message="تیکت بسته شد."
        )


class SupportAdminTicketExportView(APIView):
    """Admin Excel export for support tickets."""

    permission_classes = [IsSupportAdminUser]

    @extend_schema(
        operation_id="support_admin_export_tickets", tags=[TAG_SUPPORT_USER], responses={200: None}
    )
    def get(self, request: Request) -> HttpResponse:
        """Export filtered ticket queue as an RTL Excel workbook."""
        queryset = selectors.get_admin_tickets()
        filterset = SupportAdminTicketFilter(request.query_params, queryset=queryset)
        if filterset.is_valid():
            queryset = filterset.qs
        workbook = build_tickets_workbook(tickets=queryset)
        filename = build_support_export_filename(export_type="tickets")
        log_action_async(
            user_id=request.user.pk,
            action=audit_actions.SUPPORT_EXPORT_GENERATED,
            resource_type="support_ticket",
            resource_id="bulk",
            extra_data={"filename": filename, "export_type": "tickets"},
            **extract_audit_metadata(request),
        )
        response = HttpResponse(
            workbook.getvalue(),
            content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
        response["Content-Disposition"] = f'attachment; filename="{filename}"'
        return response

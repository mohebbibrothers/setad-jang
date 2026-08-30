"""گروه دامنه‌ای `views_user` از views — فاز ۱۱ (تفکیک P3-16).

کلاس‌ها عیناً منتقل شده‌اند؛ مشترکات از views_common؛ نامِ عمومیِ این گروه‌ها را فقط از facade (apps.*.views) یا همین ماژول import کنید.
"""

from __future__ import annotations

from drf_spectacular.utils import extend_schema
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
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
from apps.support_desk import selectors, services
from apps.support_desk.filters import (
    SupportUserTicketFilter,
)
from apps.support_desk.serializers import (
    SupportTicketAttachmentCreateSerializer,
    SupportTicketAttachmentSerializer,
    SupportTicketCreateUpdateSerializer,
    SupportTicketDetailSerializer,
    SupportTicketListSerializer,
    SupportTicketMessageSerializer,
    SupportTicketReopenSerializer,
    SupportTicketReplySerializer,
    SupportTicketSatisfactionCreateSerializer,
)
from apps.support_desk.throttles import (
    SupportAttachmentUploadThrottle,
    SupportTicketCreateThrottle,
    SupportTicketMessageThrottle,
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


class SupportUserTicketListCreateView(APIView):
    """User ticket dashboard and draft creation."""

    permission_classes = [IsAuthenticated]

    def get_throttles(self):
        """Apply creation throttle only to POST while keeping browse user-friendly."""
        if self.request.method == "POST":
            return [SupportTicketCreateThrottle()]
        return super().get_throttles()

    @extend_schema(
        operation_id="support_user_tickets_list",
        tags=[TAG_SUPPORT_USER],
        responses={200: TICKET_LIST_RESPONSE},
    )
    def get(self, request: Request) -> Response:
        """Return current user's tickets."""
        queryset = selectors.get_user_tickets(user_id=request.user.pk)
        filterset = SupportUserTicketFilter(request.query_params, queryset=queryset)
        if filterset.is_valid():
            queryset = filterset.qs
        paginator = StandardPagination()
        page = paginator.paginate_queryset(queryset, request, view=self)
        return paginator.get_paginated_response(
            SupportTicketListSerializer(page, many=True).data, message="لیست تیکت‌های شما دریافت شد."
        )

    @extend_schema(
        operation_id="support_user_tickets_create",
        tags=[TAG_SUPPORT_USER],
        request=SupportTicketCreateUpdateSerializer,
        responses={201: TICKET_DETAIL_RESPONSE, 400: SUPPORT_ERROR_RESPONSE},
    )
    def post(self, request: Request) -> CreatedResponse | ErrorResponse:
        """Create a draft ticket for current user."""
        serializer = SupportTicketCreateUpdateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            ticket = services.create_ticket(owner=request.user, **serializer.validated_data)
        except services.SupportDeskServiceError as exc:
            return _service_error_response(exc)
        log_action_async(
            user_id=request.user.pk,
            action=audit_actions.SUPPORT_TICKET_CREATED,
            resource_type="support_ticket",
            resource_id=ticket.ticket_number,
            **extract_audit_metadata(request),
        )
        return CreatedResponse(
            data=SupportTicketDetailSerializer(ticket).data,
            message="تیکت شما به‌صورت پیش‌نویس ساخته شد.",
        )


class SupportUserTicketDetailView(APIView):
    """User ticket retrieve/update endpoint."""

    permission_classes = [IsAuthenticated]

    @extend_schema(
        operation_id="support_user_tickets_retrieve",
        tags=[TAG_SUPPORT_USER],
        responses={200: TICKET_DETAIL_RESPONSE, 404: SUPPORT_ERROR_RESPONSE},
    )
    def get(self, request: Request, ticket_number: str) -> SuccessResponse | ErrorResponse:
        """Return current user's ticket detail."""
        ticket, error = _get_user_ticket_or_error(request=request, ticket_number=ticket_number)
        if error:
            return error
        return SuccessResponse(data=SupportTicketDetailSerializer(ticket).data)

    @extend_schema(
        operation_id="support_user_tickets_update",
        tags=[TAG_SUPPORT_USER],
        request=SupportTicketCreateUpdateSerializer,
        responses={
            200: TICKET_DETAIL_RESPONSE,
            403: SUPPORT_ERROR_RESPONSE,
            404: SUPPORT_ERROR_RESPONSE,
        },
    )
    def patch(self, request: Request, ticket_number: str) -> SuccessResponse | ErrorResponse:
        """Update a draft ticket before submission."""
        ticket, error = _get_user_ticket_or_error(request=request, ticket_number=ticket_number)
        if error:
            return error
        serializer = SupportTicketCreateUpdateSerializer(data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        try:
            ticket = services.update_draft_ticket(
                ticket=ticket, user=request.user, **serializer.validated_data
            )
        except (
            services.SupportPermissionError,
            services.SupportTicketStateError,
            services.SupportDeskServiceError,
        ) as exc:
            return _service_error_response(exc, status_code=status.HTTP_403_FORBIDDEN)
        log_action_async(
            user_id=request.user.pk,
            action=audit_actions.SUPPORT_TICKET_UPDATED,
            resource_type="support_ticket",
            resource_id=ticket.ticket_number,
            **extract_audit_metadata(request),
        )
        return SuccessResponse(
            data=SupportTicketDetailSerializer(ticket).data, message="تیکت بروزرسانی شد."
        )


class SupportUserTicketSubmitView(APIView):
    """Submit a draft ticket for support processing."""

    permission_classes = [IsAuthenticated]

    @extend_schema(
        operation_id="support_user_tickets_submit",
        tags=[TAG_SUPPORT_USER],
        request=None,
        responses={
            200: TICKET_DETAIL_RESPONSE,
            403: SUPPORT_ERROR_RESPONSE,
            404: SUPPORT_ERROR_RESPONSE,
        },
    )
    def post(self, request: Request, ticket_number: str) -> SuccessResponse | ErrorResponse:
        """Submit current user's draft ticket."""
        ticket, error = _get_user_ticket_or_error(request=request, ticket_number=ticket_number)
        if error:
            return error
        try:
            ticket = services.submit_ticket(ticket=ticket, user=request.user)
        except (services.SupportPermissionError, services.SupportTicketStateError) as exc:
            return _service_error_response(exc, status_code=status.HTTP_403_FORBIDDEN)
        log_action_async(
            user_id=request.user.pk,
            action=audit_actions.SUPPORT_TICKET_SUBMITTED,
            resource_type="support_ticket",
            resource_id=ticket.ticket_number,
            **extract_audit_metadata(request),
        )
        return SuccessResponse(
            data=SupportTicketDetailSerializer(ticket).data, message="تیکت برای بررسی ارسال شد."
        )


class SupportUserTicketReplyView(APIView):
    """Add a public user reply to a ticket."""

    permission_classes = [IsAuthenticated]
    throttle_classes = [SupportTicketMessageThrottle]

    @extend_schema(
        operation_id="support_user_tickets_reply",
        tags=[TAG_SUPPORT_USER],
        request=SupportTicketReplySerializer,
        responses={
            201: build_success_response_serializer(
                name="SupportTicketReplyResponse", data_serializer=SupportTicketMessageSerializer
            ),
            403: SUPPORT_ERROR_RESPONSE,
            404: SUPPORT_ERROR_RESPONSE,
        },
    )
    def post(self, request: Request, ticket_number: str) -> CreatedResponse | ErrorResponse:
        """Append a user reply to the public timeline."""
        ticket, error = _get_user_ticket_or_error(request=request, ticket_number=ticket_number)
        if error:
            return error
        serializer = SupportTicketReplySerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            message = services.add_user_reply(
                ticket=ticket, user=request.user, **serializer.validated_data
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
            data=SupportTicketMessageSerializer(message).data, message="پاسخ شما ثبت شد."
        )


class SupportUserTicketTimelineView(APIView):
    """Return public timeline for a user-owned ticket."""

    permission_classes = [IsAuthenticated]

    @extend_schema(
        operation_id="support_user_tickets_timeline",
        tags=[TAG_SUPPORT_USER],
        responses={200: MESSAGE_LIST_RESPONSE, 404: SUPPORT_ERROR_RESPONSE},
    )
    def get(self, request: Request, ticket_number: str) -> SuccessResponse | ErrorResponse:
        """Return public messages only; internal notes are never exposed."""
        ticket, error = _get_user_ticket_or_error(request=request, ticket_number=ticket_number)
        if error:
            return error
        return SuccessResponse(
            data=SupportTicketMessageSerializer(
                selectors.get_user_ticket_timeline(ticket=ticket), many=True
            ).data
        )


class SupportUserTicketAttachmentView(APIView):
    """Upload a public attachment for a user-owned ticket."""

    permission_classes = [IsAuthenticated]
    throttle_classes = [SupportAttachmentUploadThrottle]

    @extend_schema(
        operation_id="support_user_tickets_attachment_create",
        tags=[TAG_SUPPORT_USER],
        request=SupportTicketAttachmentCreateSerializer,
        responses={
            201: ATTACHMENT_RESPONSE,
            403: SUPPORT_ERROR_RESPONSE,
            404: SUPPORT_ERROR_RESPONSE,
        },
    )
    def post(self, request: Request, ticket_number: str) -> CreatedResponse | ErrorResponse:
        """Attach a validated public file to the ticket."""
        ticket, error = _get_user_ticket_or_error(request=request, ticket_number=ticket_number)
        if error:
            return error
        serializer = SupportTicketAttachmentCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        file_obj = serializer.validated_data["file"]
        try:
            attachment = services.add_attachment(
                ticket=ticket,
                user=request.user,
                file_obj=file_obj,
                original_filename=getattr(file_obj, "name", "attachment"),
                content_type=getattr(file_obj, "content_type", "") or "",
                attachment_kind=serializer.validated_data.get("attachment_kind", "other"),
                visibility="public",
            )
        except (services.SupportPermissionError, services.SupportTicketStateError) as exc:
            return _service_error_response(exc, status_code=status.HTTP_403_FORBIDDEN)
        log_action_async(
            user_id=request.user.pk,
            action=audit_actions.SUPPORT_ATTACHMENT_ADDED,
            resource_type="support_ticket_attachment",
            resource_id=str(attachment.pk),
            extra_data={"ticket_number": ticket.ticket_number},
            **extract_audit_metadata(request),
        )
        return CreatedResponse(
            data=SupportTicketAttachmentSerializer(attachment).data, message="ضمیمه تیکت ثبت شد."
        )


class SupportUserTicketReopenView(APIView):
    """Reopen a resolved/closed user-owned ticket."""

    permission_classes = [IsAuthenticated]

    @extend_schema(
        operation_id="support_user_tickets_reopen",
        tags=[TAG_SUPPORT_USER],
        request=SupportTicketReopenSerializer,
        responses={
            200: TICKET_DETAIL_RESPONSE,
            403: SUPPORT_ERROR_RESPONSE,
            404: SUPPORT_ERROR_RESPONSE,
        },
    )
    def post(self, request: Request, ticket_number: str) -> SuccessResponse | ErrorResponse:
        """Reopen ticket within the policy window."""
        ticket, error = _get_user_ticket_or_error(request=request, ticket_number=ticket_number)
        if error:
            return error
        serializer = SupportTicketReopenSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            ticket = services.reopen_ticket(
                ticket=ticket, user=request.user, **serializer.validated_data
            )
        except (services.SupportPermissionError, services.SupportTicketStateError) as exc:
            return _service_error_response(exc, status_code=status.HTTP_403_FORBIDDEN)
        log_action_async(
            user_id=request.user.pk,
            action=audit_actions.SUPPORT_TICKET_REOPENED,
            resource_type="support_ticket",
            resource_id=ticket.ticket_number,
            **extract_audit_metadata(request),
        )
        return SuccessResponse(
            data=SupportTicketDetailSerializer(ticket).data, message="تیکت بازگشایی شد."
        )


class SupportUserTicketSatisfactionView(APIView):
    """Submit a user satisfaction rating for a resolved/closed ticket."""

    permission_classes = [IsAuthenticated]

    @extend_schema(
        operation_id="support_user_tickets_satisfaction",
        tags=[TAG_SUPPORT_USER],
        request=SupportTicketSatisfactionCreateSerializer,
        responses={
            201: build_success_response_serializer(name="SupportTicketSatisfactionResponse"),
            403: SUPPORT_ERROR_RESPONSE,
            404: SUPPORT_ERROR_RESPONSE,
        },
    )
    def post(self, request: Request, ticket_number: str) -> CreatedResponse | ErrorResponse:
        """Submit CSAT rating."""
        ticket, error = _get_user_ticket_or_error(request=request, ticket_number=ticket_number)
        if error:
            return error
        serializer = SupportTicketSatisfactionCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            satisfaction = services.submit_satisfaction(
                ticket=ticket, user=request.user, **serializer.validated_data
            )
        except (
            services.SupportPermissionError,
            services.SupportTicketStateError,
            services.SupportDeskServiceError,
        ) as exc:
            return _service_error_response(exc, status_code=status.HTTP_403_FORBIDDEN)
        log_action_async(
            user_id=request.user.pk,
            action=audit_actions.SUPPORT_SATISFACTION_SUBMITTED,
            resource_type="support_ticket",
            resource_id=ticket.ticket_number,
            extra_data={"rating": satisfaction.rating},
            **extract_audit_metadata(request),
        )
        return CreatedResponse(
            data={"ticket_number": ticket.ticket_number, "rating": satisfaction.rating},
            message="امتیاز رضایت شما ثبت شد.",
        )

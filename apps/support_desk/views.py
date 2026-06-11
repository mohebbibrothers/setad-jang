"""API views for Support Desk user-facing workflows."""

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
    build_error_response_serializer,
    build_paginated_success_response_serializer,
    build_success_response_serializer,
)
from apps.support_desk import selectors, services
from apps.support_desk.filters import SupportUserTicketFilter
from apps.support_desk.serializers import (
    SupportCategorySerializer,
    SupportDepartmentSerializer,
    SupportTicketAttachmentCreateSerializer,
    SupportTicketAttachmentSerializer,
    SupportTicketCreateUpdateSerializer,
    SupportTicketDetailSerializer,
    SupportTicketListSerializer,
    SupportTicketMessageSerializer,
    SupportTicketReopenSerializer,
    SupportTicketReplySerializer,
    SupportTicketSatisfactionCreateSerializer,
    SupportTicketSuggestSerializer,
    SupportTicketTypeSerializer,
    SupportTriageSuggestionSerializer,
)
from apps.support_desk.throttles import (
    SupportAttachmentUploadThrottle,
    SupportSuggestThrottle,
    SupportTicketCreateThrottle,
    SupportTicketMessageThrottle,
)

TAG_SUPPORT_USER = "میز پشتیبانی — کاربر"
TAG_SUPPORT_TAXONOMY = "میز پشتیبانی — دسته‌بندی"

SUPPORT_ERROR_RESPONSE = build_error_response_serializer(name="SupportDeskErrorResponse")
DEPARTMENT_LIST_RESPONSE = build_success_response_serializer(name="SupportDepartmentListResponse", data_serializer=SupportDepartmentSerializer, many=True)
CATEGORY_LIST_RESPONSE = build_success_response_serializer(name="SupportCategoryListResponse", data_serializer=SupportCategorySerializer, many=True)
TICKET_TYPE_LIST_RESPONSE = build_success_response_serializer(name="SupportTicketTypeListResponse", data_serializer=SupportTicketTypeSerializer, many=True)
TICKET_LIST_RESPONSE = build_paginated_success_response_serializer(name="SupportTicketListResponse", item_serializer=SupportTicketListSerializer)
TICKET_DETAIL_RESPONSE = build_success_response_serializer(name="SupportTicketDetailResponse", data_serializer=SupportTicketDetailSerializer)
MESSAGE_LIST_RESPONSE = build_success_response_serializer(name="SupportTicketTimelineResponse", data_serializer=SupportTicketMessageSerializer, many=True)
ATTACHMENT_RESPONSE = build_success_response_serializer(name="SupportTicketAttachmentResponse", data_serializer=SupportTicketAttachmentSerializer)
TRIAGE_RESPONSE = build_success_response_serializer(name="SupportTriageSuggestionResponse", data_serializer=SupportTriageSuggestionSerializer)


def _service_error_response(exc: Exception, *, status_code: int = status.HTTP_400_BAD_REQUEST) -> ErrorResponse:
    """Convert service-layer exception to project error response."""
    return ErrorResponse(message=str(exc), status_code=status_code)


def _get_user_ticket_or_error(*, request: Request, ticket_number: str):
    """Return user ticket or a standardized 404 response."""
    ticket = selectors.get_user_ticket_by_number(user_id=request.user.pk, ticket_number=ticket_number)
    if ticket is None:
        return None, ErrorResponse(message="تیکت یافت نشد.", status_code=status.HTTP_404_NOT_FOUND)
    return ticket, None


class SupportDepartmentListView(APIView):
    """Authenticated users can browse active support departments."""

    permission_classes = [IsAuthenticated]

    @extend_schema(operation_id="support_departments_list", tags=[TAG_SUPPORT_TAXONOMY], responses={200: DEPARTMENT_LIST_RESPONSE})
    def get(self, request: Request) -> SuccessResponse:
        """Return active support departments."""
        return SuccessResponse(data=SupportDepartmentSerializer(selectors.get_active_departments(), many=True).data)


class SupportCategoryListView(APIView):
    """Authenticated users can browse active support category tree."""

    permission_classes = [IsAuthenticated]

    @extend_schema(operation_id="support_categories_list", tags=[TAG_SUPPORT_TAXONOMY], responses={200: CATEGORY_LIST_RESPONSE})
    def get(self, request: Request) -> SuccessResponse:
        """Return active support categories."""
        return SuccessResponse(data=SupportCategorySerializer(selectors.get_active_category_tree(), many=True).data)


class SupportTicketTypeListView(APIView):
    """Authenticated users can browse dynamic ticket types."""

    permission_classes = [IsAuthenticated]

    @extend_schema(operation_id="support_ticket_types_list", tags=[TAG_SUPPORT_TAXONOMY], responses={200: TICKET_TYPE_LIST_RESPONSE})
    def get(self, request: Request) -> SuccessResponse:
        """Return active support ticket types."""
        return SuccessResponse(data=SupportTicketTypeSerializer(selectors.get_active_ticket_types(), many=True).data)


class SupportTicketSuggestView(APIView):
    """Smart triage suggestion endpoint before creating a ticket."""

    permission_classes = [IsAuthenticated]
    throttle_classes = [SupportSuggestThrottle]

    @extend_schema(operation_id="support_user_tickets_suggest", tags=[TAG_SUPPORT_USER], request=SupportTicketSuggestSerializer, responses={200: TRIAGE_RESPONSE})
    def post(self, request: Request) -> SuccessResponse:
        """Return smart triage suggestions and duplicate warning."""
        serializer = SupportTicketSuggestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        suggestion = services.suggest_ticket_triage(owner=request.user, **serializer.validated_data)
        return SuccessResponse(data=SupportTriageSuggestionSerializer(suggestion).data, message="پیشنهاد هوشمند تریاژ دریافت شد.")


class SupportUserTicketListCreateView(APIView):
    """User ticket dashboard and draft creation."""

    permission_classes = [IsAuthenticated]

    def get_throttles(self):
        """Apply creation throttle only to POST while keeping browse user-friendly."""
        if self.request.method == "POST":
            return [SupportTicketCreateThrottle()]
        return super().get_throttles()

    @extend_schema(operation_id="support_user_tickets_list", tags=[TAG_SUPPORT_USER], responses={200: TICKET_LIST_RESPONSE})
    def get(self, request: Request) -> Response:
        """Return current user's tickets."""
        queryset = selectors.get_user_tickets(user_id=request.user.pk)
        filterset = SupportUserTicketFilter(request.query_params, queryset=queryset)
        if filterset.is_valid():
            queryset = filterset.qs
        paginator = StandardPagination()
        page = paginator.paginate_queryset(queryset, request, view=self)
        return paginator.get_paginated_response(SupportTicketListSerializer(page, many=True).data, message="لیست تیکت‌های شما دریافت شد.")

    @extend_schema(operation_id="support_user_tickets_create", tags=[TAG_SUPPORT_USER], request=SupportTicketCreateUpdateSerializer, responses={201: TICKET_DETAIL_RESPONSE, 400: SUPPORT_ERROR_RESPONSE})
    def post(self, request: Request) -> CreatedResponse | ErrorResponse:
        """Create a draft ticket for current user."""
        serializer = SupportTicketCreateUpdateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            ticket = services.create_ticket(owner=request.user, **serializer.validated_data)
        except services.SupportDeskServiceError as exc:
            return _service_error_response(exc)
        log_action_async(user_id=request.user.pk, action=audit_actions.SUPPORT_TICKET_CREATED, resource_type="support_ticket", resource_id=ticket.ticket_number, **extract_audit_metadata(request))
        return CreatedResponse(data=SupportTicketDetailSerializer(ticket).data, message="تیکت شما به‌صورت پیش‌نویس ساخته شد.")


class SupportUserTicketDetailView(APIView):
    """User ticket retrieve/update endpoint."""

    permission_classes = [IsAuthenticated]

    @extend_schema(operation_id="support_user_tickets_retrieve", tags=[TAG_SUPPORT_USER], responses={200: TICKET_DETAIL_RESPONSE, 404: SUPPORT_ERROR_RESPONSE})
    def get(self, request: Request, ticket_number: str) -> SuccessResponse | ErrorResponse:
        """Return current user's ticket detail."""
        ticket, error = _get_user_ticket_or_error(request=request, ticket_number=ticket_number)
        if error:
            return error
        return SuccessResponse(data=SupportTicketDetailSerializer(ticket).data)

    @extend_schema(operation_id="support_user_tickets_update", tags=[TAG_SUPPORT_USER], request=SupportTicketCreateUpdateSerializer, responses={200: TICKET_DETAIL_RESPONSE, 403: SUPPORT_ERROR_RESPONSE, 404: SUPPORT_ERROR_RESPONSE})
    def patch(self, request: Request, ticket_number: str) -> SuccessResponse | ErrorResponse:
        """Update a draft ticket before submission."""
        ticket, error = _get_user_ticket_or_error(request=request, ticket_number=ticket_number)
        if error:
            return error
        serializer = SupportTicketCreateUpdateSerializer(data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        try:
            ticket = services.update_draft_ticket(ticket=ticket, user=request.user, **serializer.validated_data)
        except (services.SupportPermissionError, services.SupportTicketStateError, services.SupportDeskServiceError) as exc:
            return _service_error_response(exc, status_code=status.HTTP_403_FORBIDDEN)
        log_action_async(user_id=request.user.pk, action=audit_actions.SUPPORT_TICKET_UPDATED, resource_type="support_ticket", resource_id=ticket.ticket_number, **extract_audit_metadata(request))
        return SuccessResponse(data=SupportTicketDetailSerializer(ticket).data, message="تیکت بروزرسانی شد.")


class SupportUserTicketSubmitView(APIView):
    """Submit a draft ticket for support processing."""

    permission_classes = [IsAuthenticated]

    @extend_schema(operation_id="support_user_tickets_submit", tags=[TAG_SUPPORT_USER], request=None, responses={200: TICKET_DETAIL_RESPONSE, 403: SUPPORT_ERROR_RESPONSE, 404: SUPPORT_ERROR_RESPONSE})
    def post(self, request: Request, ticket_number: str) -> SuccessResponse | ErrorResponse:
        """Submit current user's draft ticket."""
        ticket, error = _get_user_ticket_or_error(request=request, ticket_number=ticket_number)
        if error:
            return error
        try:
            ticket = services.submit_ticket(ticket=ticket, user=request.user)
        except (services.SupportPermissionError, services.SupportTicketStateError) as exc:
            return _service_error_response(exc, status_code=status.HTTP_403_FORBIDDEN)
        log_action_async(user_id=request.user.pk, action=audit_actions.SUPPORT_TICKET_SUBMITTED, resource_type="support_ticket", resource_id=ticket.ticket_number, **extract_audit_metadata(request))
        return SuccessResponse(data=SupportTicketDetailSerializer(ticket).data, message="تیکت برای بررسی ارسال شد.")


class SupportUserTicketReplyView(APIView):
    """Add a public user reply to a ticket."""

    permission_classes = [IsAuthenticated]
    throttle_classes = [SupportTicketMessageThrottle]

    @extend_schema(operation_id="support_user_tickets_reply", tags=[TAG_SUPPORT_USER], request=SupportTicketReplySerializer, responses={201: build_success_response_serializer(name="SupportTicketReplyResponse", data_serializer=SupportTicketMessageSerializer), 403: SUPPORT_ERROR_RESPONSE, 404: SUPPORT_ERROR_RESPONSE})
    def post(self, request: Request, ticket_number: str) -> CreatedResponse | ErrorResponse:
        """Append a user reply to the public timeline."""
        ticket, error = _get_user_ticket_or_error(request=request, ticket_number=ticket_number)
        if error:
            return error
        serializer = SupportTicketReplySerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            message = services.add_user_reply(ticket=ticket, user=request.user, **serializer.validated_data)
        except (services.SupportPermissionError, services.SupportTicketStateError) as exc:
            return _service_error_response(exc, status_code=status.HTTP_403_FORBIDDEN)
        log_action_async(user_id=request.user.pk, action=audit_actions.SUPPORT_TICKET_REPLIED, resource_type="support_ticket", resource_id=ticket.ticket_number, **extract_audit_metadata(request))
        return CreatedResponse(data=SupportTicketMessageSerializer(message).data, message="پاسخ شما ثبت شد.")


class SupportUserTicketTimelineView(APIView):
    """Return public timeline for a user-owned ticket."""

    permission_classes = [IsAuthenticated]

    @extend_schema(operation_id="support_user_tickets_timeline", tags=[TAG_SUPPORT_USER], responses={200: MESSAGE_LIST_RESPONSE, 404: SUPPORT_ERROR_RESPONSE})
    def get(self, request: Request, ticket_number: str) -> SuccessResponse | ErrorResponse:
        """Return public messages only; internal notes are never exposed."""
        ticket, error = _get_user_ticket_or_error(request=request, ticket_number=ticket_number)
        if error:
            return error
        return SuccessResponse(data=SupportTicketMessageSerializer(selectors.get_user_ticket_timeline(ticket=ticket), many=True).data)


class SupportUserTicketAttachmentView(APIView):
    """Upload a public attachment for a user-owned ticket."""

    permission_classes = [IsAuthenticated]
    throttle_classes = [SupportAttachmentUploadThrottle]

    @extend_schema(operation_id="support_user_tickets_attachment_create", tags=[TAG_SUPPORT_USER], request=SupportTicketAttachmentCreateSerializer, responses={201: ATTACHMENT_RESPONSE, 403: SUPPORT_ERROR_RESPONSE, 404: SUPPORT_ERROR_RESPONSE})
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
        log_action_async(user_id=request.user.pk, action=audit_actions.SUPPORT_ATTACHMENT_ADDED, resource_type="support_ticket_attachment", resource_id=str(attachment.pk), extra_data={"ticket_number": ticket.ticket_number}, **extract_audit_metadata(request))
        return CreatedResponse(data=SupportTicketAttachmentSerializer(attachment).data, message="ضمیمه تیکت ثبت شد.")


class SupportUserTicketReopenView(APIView):
    """Reopen a resolved/closed user-owned ticket."""

    permission_classes = [IsAuthenticated]

    @extend_schema(operation_id="support_user_tickets_reopen", tags=[TAG_SUPPORT_USER], request=SupportTicketReopenSerializer, responses={200: TICKET_DETAIL_RESPONSE, 403: SUPPORT_ERROR_RESPONSE, 404: SUPPORT_ERROR_RESPONSE})
    def post(self, request: Request, ticket_number: str) -> SuccessResponse | ErrorResponse:
        """Reopen ticket within the policy window."""
        ticket, error = _get_user_ticket_or_error(request=request, ticket_number=ticket_number)
        if error:
            return error
        serializer = SupportTicketReopenSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            ticket = services.reopen_ticket(ticket=ticket, user=request.user, **serializer.validated_data)
        except (services.SupportPermissionError, services.SupportTicketStateError) as exc:
            return _service_error_response(exc, status_code=status.HTTP_403_FORBIDDEN)
        log_action_async(user_id=request.user.pk, action=audit_actions.SUPPORT_TICKET_REOPENED, resource_type="support_ticket", resource_id=ticket.ticket_number, **extract_audit_metadata(request))
        return SuccessResponse(data=SupportTicketDetailSerializer(ticket).data, message="تیکت بازگشایی شد.")


class SupportUserTicketSatisfactionView(APIView):
    """Submit a user satisfaction rating for a resolved/closed ticket."""

    permission_classes = [IsAuthenticated]

    @extend_schema(operation_id="support_user_tickets_satisfaction", tags=[TAG_SUPPORT_USER], request=SupportTicketSatisfactionCreateSerializer, responses={201: build_success_response_serializer(name="SupportTicketSatisfactionResponse"), 403: SUPPORT_ERROR_RESPONSE, 404: SUPPORT_ERROR_RESPONSE})
    def post(self, request: Request, ticket_number: str) -> CreatedResponse | ErrorResponse:
        """Submit CSAT rating."""
        ticket, error = _get_user_ticket_or_error(request=request, ticket_number=ticket_number)
        if error:
            return error
        serializer = SupportTicketSatisfactionCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            satisfaction = services.submit_satisfaction(ticket=ticket, user=request.user, **serializer.validated_data)
        except (services.SupportPermissionError, services.SupportTicketStateError, services.SupportDeskServiceError) as exc:
            return _service_error_response(exc, status_code=status.HTTP_403_FORBIDDEN)
        log_action_async(user_id=request.user.pk, action=audit_actions.SUPPORT_SATISFACTION_SUBMITTED, resource_type="support_ticket", resource_id=ticket.ticket_number, extra_data={"rating": satisfaction.rating}, **extract_audit_metadata(request))
        return CreatedResponse(data={"ticket_number": ticket.ticket_number, "rating": satisfaction.rating}, message="امتیاز رضایت شما ثبت شد.")

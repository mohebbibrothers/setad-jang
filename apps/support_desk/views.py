"""API views for Support Desk user-facing workflows."""

from __future__ import annotations

from django.http import HttpResponse
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
from apps.support_desk.export import (
    build_csat_workbook,
    build_messages_workbook,
    build_sla_workbook,
    build_support_export_filename,
    build_tickets_workbook,
)
from apps.support_desk.filters import (
    SupportAdminTicketFilter,
    SupportDuplicateCandidateAdminFilter,
    SupportUserTicketFilter,
)
from apps.support_desk.permissions import IsSupportAdminUser
from apps.support_desk.serializers import (
    SupportAdminAnalyticsSerializer,
    SupportAdminAssignSerializer,
    SupportAdminReasonSerializer,
    SupportAdminStatusSerializer,
    SupportAdminTicketDetailSerializer,
    SupportAdminTicketMessageSerializer,
    SupportAssignmentRecommendationSerializer,
    SupportBusinessCalendarInputSerializer,
    SupportBusinessCalendarSerializer,
    SupportCannedResponseInputSerializer,
    SupportCannedResponseSerializer,
    SupportCategoryInputSerializer,
    SupportCategorySerializer,
    SupportDepartmentInputSerializer,
    SupportDepartmentSerializer,
    SupportDuplicateCandidateSerializer,
    SupportDuplicateReviewSerializer,
    SupportHolidayInputSerializer,
    SupportHolidaySerializer,
    SupportSLAPolicyInputSerializer,
    SupportSLAPolicySerializer,
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
    SupportTicketTypeInputSerializer,
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
ASSIGNMENT_RECOMMENDATION_RESPONSE = build_success_response_serializer(name="SupportAssignmentRecommendationResponse", data_serializer=SupportAssignmentRecommendationSerializer)


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


ADMIN_TICKET_LIST_RESPONSE = build_paginated_success_response_serializer(name="SupportAdminTicketListResponse", item_serializer=SupportTicketListSerializer)
ADMIN_TICKET_DETAIL_RESPONSE = build_success_response_serializer(name="SupportAdminTicketDetailResponse", data_serializer=SupportAdminTicketDetailSerializer)
ADMIN_DEPARTMENT_RESPONSE = build_success_response_serializer(name="SupportAdminDepartmentResponse", data_serializer=SupportDepartmentSerializer)
ADMIN_CATEGORY_RESPONSE = build_success_response_serializer(name="SupportAdminCategoryResponse", data_serializer=SupportCategorySerializer)
ADMIN_TICKET_TYPE_RESPONSE = build_success_response_serializer(name="SupportAdminTicketTypeResponse", data_serializer=SupportTicketTypeSerializer)
ADMIN_SLA_RESPONSE = build_success_response_serializer(name="SupportAdminSLAPolicyResponse", data_serializer=SupportSLAPolicySerializer)
ADMIN_CANNED_RESPONSE = build_success_response_serializer(name="SupportAdminCannedResponseResponse", data_serializer=SupportCannedResponseSerializer)
ADMIN_DUPLICATE_RESPONSE = build_success_response_serializer(name="SupportAdminDuplicateCandidateResponse", data_serializer=SupportDuplicateCandidateSerializer)


class SupportAdminDepartmentListCreateView(APIView):
    """Admin department list/create endpoint."""

    permission_classes = [IsSupportAdminUser]
    serializer_class = SupportDepartmentSerializer

    @extend_schema(operation_id="support_admin_departments_list", tags=[TAG_SUPPORT_TAXONOMY], responses={200: build_success_response_serializer(name="SupportAdminDepartmentListResponse", data_serializer=SupportDepartmentSerializer, many=True)})
    def get(self, request: Request) -> SuccessResponse:
        """Return all departments for admin taxonomy management."""
        return SuccessResponse(data=SupportDepartmentSerializer(selectors.get_admin_departments(), many=True).data)

    def post(self, request: Request) -> CreatedResponse:
        """Create support department."""
        serializer = SupportDepartmentInputSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        department = services.create_department(**serializer.validated_data)
        log_action_async(user_id=request.user.pk, action=audit_actions.SUPPORT_DEPARTMENT_CREATED, resource_type="support_department", resource_id=str(department.pk), **extract_audit_metadata(request))
        return CreatedResponse(data=SupportDepartmentSerializer(department).data, message="دپارتمان پشتیبانی ساخته شد.")


class SupportAdminDepartmentDetailView(APIView):
    """Admin department detail/update/deactivate endpoint."""

    permission_classes = [IsSupportAdminUser]
    serializer_class = SupportDepartmentSerializer

    @extend_schema(operation_id="support_admin_departments_retrieve", tags=[TAG_SUPPORT_TAXONOMY], responses={200: ADMIN_DEPARTMENT_RESPONSE, 404: SUPPORT_ERROR_RESPONSE})
    def get(self, request: Request, department_id: int) -> SuccessResponse | ErrorResponse:
        """Return one department."""
        department = selectors.get_admin_department_by_id(department_id=department_id)
        if department is None:
            return ErrorResponse(message="دپارتمان یافت نشد.", status_code=status.HTTP_404_NOT_FOUND)
        return SuccessResponse(data=SupportDepartmentSerializer(department).data)

    def patch(self, request: Request, department_id: int) -> SuccessResponse | ErrorResponse:
        """Update department."""
        department = selectors.get_admin_department_by_id(department_id=department_id)
        if department is None:
            return ErrorResponse(message="دپارتمان یافت نشد.", status_code=status.HTTP_404_NOT_FOUND)
        serializer = SupportDepartmentInputSerializer(data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        department = services.update_department(department=department, **serializer.validated_data)
        log_action_async(user_id=request.user.pk, action=audit_actions.SUPPORT_DEPARTMENT_UPDATED, resource_type="support_department", resource_id=str(department.pk), **extract_audit_metadata(request))
        return SuccessResponse(data=SupportDepartmentSerializer(department).data, message="دپارتمان بروزرسانی شد.")

    def delete(self, request: Request, department_id: int) -> SuccessResponse | ErrorResponse:
        """Deactivate department safely."""
        department = selectors.get_admin_department_by_id(department_id=department_id)
        if department is None:
            return ErrorResponse(message="دپارتمان یافت نشد.", status_code=status.HTTP_404_NOT_FOUND)
        try:
            department = services.deactivate_department(department=department)
        except services.SupportDeskServiceError as exc:
            return _service_error_response(exc)
        log_action_async(user_id=request.user.pk, action=audit_actions.SUPPORT_DEPARTMENT_DEACTIVATED, resource_type="support_department", resource_id=str(department.pk), **extract_audit_metadata(request))
        return SuccessResponse(data=SupportDepartmentSerializer(department).data, message="دپارتمان غیرفعال شد.")


class SupportAdminCategoryListCreateView(APIView):
    """Admin category tree list/create endpoint."""

    permission_classes = [IsSupportAdminUser]
    serializer_class = SupportCategorySerializer

    def get(self, request: Request) -> SuccessResponse:
        """Return all categories for admin tree management."""
        return SuccessResponse(data=SupportCategorySerializer(selectors.get_admin_category_tree(), many=True).data)

    def post(self, request: Request) -> CreatedResponse | ErrorResponse:
        """Create support category."""
        serializer = SupportCategoryInputSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            category = services.create_category(**serializer.validated_data)
        except services.SupportTaxonomyTreeError as exc:
            return _service_error_response(exc)
        log_action_async(user_id=request.user.pk, action=audit_actions.SUPPORT_CATEGORY_CREATED, resource_type="support_category", resource_id=str(category.pk), **extract_audit_metadata(request))
        return CreatedResponse(data=SupportCategorySerializer(category).data, message="دسته‌بندی پشتیبانی ساخته شد.")


class SupportAdminCategoryDetailView(APIView):
    """Admin category detail/update/deactivate endpoint."""

    permission_classes = [IsSupportAdminUser]
    serializer_class = SupportCategorySerializer

    def patch(self, request: Request, category_id: int) -> SuccessResponse | ErrorResponse:
        """Update category tree node."""
        category = selectors.get_admin_category_by_id(category_id=category_id)
        if category is None:
            return ErrorResponse(message="دسته‌بندی یافت نشد.", status_code=status.HTTP_404_NOT_FOUND)
        serializer = SupportCategoryInputSerializer(data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        try:
            category = services.update_category(category=category, **serializer.validated_data)
        except services.SupportTaxonomyTreeError as exc:
            return _service_error_response(exc)
        log_action_async(user_id=request.user.pk, action=audit_actions.SUPPORT_CATEGORY_UPDATED, resource_type="support_category", resource_id=str(category.pk), **extract_audit_metadata(request))
        return SuccessResponse(data=SupportCategorySerializer(category).data, message="دسته‌بندی بروزرسانی شد.")

    def delete(self, request: Request, category_id: int) -> SuccessResponse | ErrorResponse:
        """Deactivate category safely."""
        category = selectors.get_admin_category_by_id(category_id=category_id)
        if category is None:
            return ErrorResponse(message="دسته‌بندی یافت نشد.", status_code=status.HTTP_404_NOT_FOUND)
        try:
            category = services.deactivate_category(category=category)
        except services.SupportTaxonomyTreeError as exc:
            return _service_error_response(exc)
        log_action_async(user_id=request.user.pk, action=audit_actions.SUPPORT_CATEGORY_DEACTIVATED, resource_type="support_category", resource_id=str(category.pk), **extract_audit_metadata(request))
        return SuccessResponse(data=SupportCategorySerializer(category).data, message="دسته‌بندی غیرفعال شد.")


class SupportAdminTicketTypeListCreateView(APIView):
    """Admin ticket type list/create endpoint."""

    permission_classes = [IsSupportAdminUser]
    serializer_class = SupportTicketTypeSerializer

    def get(self, request: Request) -> SuccessResponse:
        """Return ticket types."""
        return SuccessResponse(data=SupportTicketTypeSerializer(selectors.get_admin_ticket_types(), many=True).data)

    def post(self, request: Request) -> CreatedResponse | ErrorResponse:
        """Create ticket type."""
        serializer = SupportTicketTypeInputSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            ticket_type = services.create_ticket_type(**serializer.validated_data)
        except services.SupportDeskServiceError as exc:
            return _service_error_response(exc)
        log_action_async(user_id=request.user.pk, action=audit_actions.SUPPORT_TICKET_TYPE_CREATED, resource_type="support_ticket_type", resource_id=str(ticket_type.pk), **extract_audit_metadata(request))
        return CreatedResponse(data=SupportTicketTypeSerializer(ticket_type).data, message="نوع تیکت ساخته شد.")


class SupportAdminTicketTypeDetailView(APIView):
    """Admin ticket type update endpoint."""

    permission_classes = [IsSupportAdminUser]
    serializer_class = SupportTicketTypeSerializer

    def patch(self, request: Request, ticket_type_id: int) -> SuccessResponse | ErrorResponse:
        """Update ticket type."""
        ticket_type = selectors.get_admin_ticket_type_by_id(ticket_type_id=ticket_type_id)
        if ticket_type is None:
            return ErrorResponse(message="نوع تیکت یافت نشد.", status_code=status.HTTP_404_NOT_FOUND)
        serializer = SupportTicketTypeInputSerializer(data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        try:
            ticket_type = services.update_ticket_type(ticket_type=ticket_type, **serializer.validated_data)
        except services.SupportDeskServiceError as exc:
            return _service_error_response(exc)
        log_action_async(user_id=request.user.pk, action=audit_actions.SUPPORT_TICKET_TYPE_UPDATED, resource_type="support_ticket_type", resource_id=str(ticket_type.pk), **extract_audit_metadata(request))
        return SuccessResponse(data=SupportTicketTypeSerializer(ticket_type).data, message="نوع تیکت بروزرسانی شد.")


class SupportAdminBusinessCalendarListCreateView(APIView):
    """Admin business calendar list/create endpoint."""

    permission_classes = [IsSupportAdminUser]
    serializer_class = SupportBusinessCalendarSerializer

    def get(self, request: Request) -> SuccessResponse:
        """Return business calendars."""
        return SuccessResponse(data=SupportBusinessCalendarSerializer(selectors.get_admin_business_calendars(), many=True).data)

    def post(self, request: Request) -> CreatedResponse:
        """Create business calendar."""
        serializer = SupportBusinessCalendarInputSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        calendar = services.create_business_calendar(**serializer.validated_data)
        return CreatedResponse(data=SupportBusinessCalendarSerializer(calendar).data, message="تقویم کاری ساخته شد.")


class SupportAdminBusinessCalendarDetailView(APIView):
    """Admin business calendar update endpoint."""

    permission_classes = [IsSupportAdminUser]
    serializer_class = SupportBusinessCalendarSerializer

    def patch(self, request: Request, calendar_id: int) -> SuccessResponse | ErrorResponse:
        """Update business calendar."""
        calendar = selectors.get_admin_business_calendar_by_id(calendar_id=calendar_id)
        if calendar is None:
            return ErrorResponse(message="تقویم کاری یافت نشد.", status_code=status.HTTP_404_NOT_FOUND)
        serializer = SupportBusinessCalendarInputSerializer(data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        calendar = services.update_business_calendar(calendar=calendar, **serializer.validated_data)
        return SuccessResponse(data=SupportBusinessCalendarSerializer(calendar).data, message="تقویم کاری بروزرسانی شد.")


class SupportAdminHolidayListCreateView(APIView):
    """Admin support holiday list/create endpoint."""

    permission_classes = [IsSupportAdminUser]
    serializer_class = SupportHolidaySerializer

    def get(self, request: Request) -> SuccessResponse:
        """Return support holidays."""
        return SuccessResponse(data=SupportHolidaySerializer(selectors.get_admin_holidays(), many=True).data)

    def post(self, request: Request) -> CreatedResponse:
        """Create support holiday."""
        serializer = SupportHolidayInputSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        holiday = services.create_holiday(**serializer.validated_data)
        return CreatedResponse(data=SupportHolidaySerializer(holiday).data, message="تعطیلی پشتیبانی ثبت شد.")


class SupportAdminHolidayDetailView(APIView):
    """Admin support holiday update endpoint."""

    permission_classes = [IsSupportAdminUser]
    serializer_class = SupportHolidaySerializer

    def patch(self, request: Request, holiday_id: int) -> SuccessResponse | ErrorResponse:
        """Update support holiday."""
        holiday = selectors.get_admin_holiday_by_id(holiday_id=holiday_id)
        if holiday is None:
            return ErrorResponse(message="تعطیلی یافت نشد.", status_code=status.HTTP_404_NOT_FOUND)
        serializer = SupportHolidayInputSerializer(data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        holiday = services.update_holiday(holiday=holiday, **serializer.validated_data)
        return SuccessResponse(data=SupportHolidaySerializer(holiday).data, message="تعطیلی بروزرسانی شد.")


class SupportAdminSLAPolicyListCreateView(APIView):
    """Admin SLA policy list/create endpoint."""

    permission_classes = [IsSupportAdminUser]
    serializer_class = SupportSLAPolicySerializer

    def get(self, request: Request) -> SuccessResponse:
        """Return SLA policies."""
        return SuccessResponse(data=SupportSLAPolicySerializer(selectors.get_admin_sla_policies(), many=True).data)

    def post(self, request: Request) -> CreatedResponse:
        """Create SLA policy."""
        serializer = SupportSLAPolicyInputSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        policy = services.create_sla_policy(**serializer.validated_data)
        log_action_async(user_id=request.user.pk, action=audit_actions.SUPPORT_SLA_POLICY_CREATED, resource_type="support_sla_policy", resource_id=str(policy.pk), **extract_audit_metadata(request))
        return CreatedResponse(data=SupportSLAPolicySerializer(policy).data, message="سیاست SLA ساخته شد.")


class SupportAdminSLAPolicyDetailView(APIView):
    """Admin SLA policy update endpoint."""

    permission_classes = [IsSupportAdminUser]
    serializer_class = SupportSLAPolicySerializer

    def patch(self, request: Request, policy_id: int) -> SuccessResponse | ErrorResponse:
        """Update SLA policy."""
        policy = selectors.get_admin_sla_policy_by_id(policy_id=policy_id)
        if policy is None:
            return ErrorResponse(message="سیاست SLA یافت نشد.", status_code=status.HTTP_404_NOT_FOUND)
        serializer = SupportSLAPolicyInputSerializer(data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        policy = services.update_sla_policy(policy=policy, **serializer.validated_data)
        log_action_async(user_id=request.user.pk, action=audit_actions.SUPPORT_SLA_POLICY_UPDATED, resource_type="support_sla_policy", resource_id=str(policy.pk), **extract_audit_metadata(request))
        return SuccessResponse(data=SupportSLAPolicySerializer(policy).data, message="سیاست SLA بروزرسانی شد.")


class SupportAdminCannedResponseListCreateView(APIView):
    """Admin canned response list/create endpoint."""

    permission_classes = [IsSupportAdminUser]
    serializer_class = SupportCannedResponseSerializer

    def get(self, request: Request) -> SuccessResponse:
        """Return canned responses."""
        return SuccessResponse(data=SupportCannedResponseSerializer(selectors.get_admin_canned_responses(), many=True).data)

    def post(self, request: Request) -> CreatedResponse | ErrorResponse:
        """Create canned response."""
        serializer = SupportCannedResponseInputSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            canned = services.create_canned_response(**serializer.validated_data)
        except services.SupportDeskServiceError as exc:
            return _service_error_response(exc)
        log_action_async(user_id=request.user.pk, action=audit_actions.SUPPORT_CANNED_RESPONSE_CREATED, resource_type="support_canned_response", resource_id=str(canned.pk), **extract_audit_metadata(request))
        return CreatedResponse(data=SupportCannedResponseSerializer(canned).data, message="پاسخ آماده ساخته شد.")


class SupportAdminCannedResponseDetailView(APIView):
    """Admin canned response update/use endpoint."""

    permission_classes = [IsSupportAdminUser]
    serializer_class = SupportCannedResponseSerializer

    def patch(self, request: Request, canned_response_id: int) -> SuccessResponse | ErrorResponse:
        """Update canned response."""
        canned = selectors.get_admin_canned_response_by_id(canned_response_id=canned_response_id)
        if canned is None:
            return ErrorResponse(message="پاسخ آماده یافت نشد.", status_code=status.HTTP_404_NOT_FOUND)
        serializer = SupportCannedResponseInputSerializer(data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        try:
            canned = services.update_canned_response(canned_response=canned, **serializer.validated_data)
        except services.SupportDeskServiceError as exc:
            return _service_error_response(exc)
        return SuccessResponse(data=SupportCannedResponseSerializer(canned).data, message="پاسخ آماده بروزرسانی شد.")


class SupportAdminCannedResponseUseView(APIView):
    """Admin canned response usage counter endpoint."""

    permission_classes = [IsSupportAdminUser]
    serializer_class = SupportCannedResponseSerializer

    def post(self, request: Request, canned_response_id: int) -> SuccessResponse | ErrorResponse:
        """Mark canned response as used."""
        canned = selectors.get_admin_canned_response_by_id(canned_response_id=canned_response_id)
        if canned is None:
            return ErrorResponse(message="پاسخ آماده یافت نشد.", status_code=status.HTTP_404_NOT_FOUND)
        canned = services.use_canned_response(canned_response=canned)
        log_action_async(user_id=request.user.pk, action=audit_actions.SUPPORT_CANNED_RESPONSE_USED, resource_type="support_canned_response", resource_id=str(canned.pk), **extract_audit_metadata(request))
        return SuccessResponse(data=SupportCannedResponseSerializer(canned).data, message="استفاده از پاسخ آماده ثبت شد.")


class SupportAdminTicketListView(APIView):
    """Admin ticket queue endpoint."""

    permission_classes = [IsSupportAdminUser]
    serializer_class = SupportTicketListSerializer

    @extend_schema(operation_id="support_admin_tickets_list", tags=[TAG_SUPPORT_USER], responses={200: ADMIN_TICKET_LIST_RESPONSE})
    def get(self, request: Request) -> Response:
        """Return filtered admin ticket queue."""
        queryset = selectors.get_admin_tickets()
        filterset = SupportAdminTicketFilter(request.query_params, queryset=queryset)
        if filterset.is_valid():
            queryset = filterset.qs
        paginator = StandardPagination()
        page = paginator.paginate_queryset(queryset, request, view=self)
        return paginator.get_paginated_response(SupportTicketListSerializer(page, many=True).data)


class SupportAdminTicketDetailView(APIView):
    """Admin ticket detail endpoint."""

    permission_classes = [IsSupportAdminUser]
    serializer_class = SupportAdminTicketDetailSerializer

    @extend_schema(operation_id="support_admin_tickets_retrieve", tags=[TAG_SUPPORT_USER], responses={200: ADMIN_TICKET_DETAIL_RESPONSE, 404: SUPPORT_ERROR_RESPONSE})
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
            message = services.add_admin_reply(ticket=ticket, admin=request.user, **serializer.validated_data)
        except (services.SupportPermissionError, services.SupportTicketStateError) as exc:
            return _service_error_response(exc, status_code=status.HTTP_403_FORBIDDEN)
        log_action_async(user_id=request.user.pk, action=audit_actions.SUPPORT_TICKET_REPLIED, resource_type="support_ticket", resource_id=ticket.ticket_number, **extract_audit_metadata(request))
        return CreatedResponse(data=SupportAdminTicketMessageSerializer(message).data, message="پاسخ ادمین ثبت شد.")


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
        message = services.add_internal_note(ticket=ticket, admin=request.user, **serializer.validated_data)
        log_action_async(user_id=request.user.pk, action=audit_actions.SUPPORT_TICKET_INTERNAL_NOTE_ADDED, resource_type="support_ticket", resource_id=ticket.ticket_number, **extract_audit_metadata(request))
        return CreatedResponse(data=SupportAdminTicketMessageSerializer(message).data, message="یادداشت داخلی ثبت شد.")


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
        ticket = services.assign_ticket(ticket=ticket, admin=request.user, **serializer.validated_data)
        log_action_async(user_id=request.user.pk, action=audit_actions.SUPPORT_TICKET_ASSIGNED, resource_type="support_ticket", resource_id=ticket.ticket_number, **extract_audit_metadata(request))
        return SuccessResponse(data=SupportAdminTicketDetailSerializer(ticket).data, message="تیکت ارجاع شد.")


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
            extra_data={"recommended_assignee_id": payload["recommended_assignee_id"], "policy_version": payload["policy_version"]},
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
        responses={200: TICKET_DETAIL_RESPONSE, 400: SUPPORT_ERROR_RESPONSE, 404: SUPPORT_ERROR_RESPONSE},
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
        return SuccessResponse(data=SupportAdminTicketDetailSerializer(ticket).data, message="تیکت به‌صورت خودکار ارجاع شد.")


def _serialize_assignment_recommendation(recommendation: services.SupportAssignmentRecommendation) -> dict:
    """Serialize assignment recommendation without leaking unnecessary user fields."""
    assignee = recommendation.recommended_assignee
    return {
        "ticket_number": recommendation.ticket.ticket_number,
        "recommended_assignee_id": assignee.pk if assignee else None,
        "recommended_assignee_email": getattr(assignee, "email", "") or "" if assignee else "",
        "policy_version": recommendation.policy_version,
        "reason_codes": recommendation.reason_codes,
        "candidates": [
            {
                "user_id": candidate.user.pk,
                "user_email": getattr(candidate.user, "email", "") or "",
                "user_display_name": getattr(candidate.user, "full_name", "") or getattr(candidate.user, "email", "") or f"user#{candidate.user.pk}",
                "workload_score": candidate.workload_score,
                "open_tickets": candidate.open_tickets,
                "urgent_or_critical_tickets": candidate.urgent_or_critical_tickets,
                "breached_sla_tickets": candidate.breached_sla_tickets,
                "waiting_admin_tickets": candidate.waiting_admin_tickets,
                "department_open_tickets": candidate.department_open_tickets,
                "reason_codes": candidate.reason_codes,
            }
            for candidate in recommendation.candidates
        ],
    }


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
        ticket = services.change_ticket_status(ticket=ticket, admin=request.user, **serializer.validated_data)
        log_action_async(user_id=request.user.pk, action=audit_actions.SUPPORT_TICKET_STATUS_CHANGED, resource_type="support_ticket", resource_id=ticket.ticket_number, **extract_audit_metadata(request))
        return SuccessResponse(data=SupportAdminTicketDetailSerializer(ticket).data, message="وضعیت تیکت تغییر کرد.")


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
        ticket = services.escalate_ticket(ticket=ticket, admin=request.user, reason=serializer.validated_data.get("reason", "ارجاع فوری"))
        log_action_async(user_id=request.user.pk, action=audit_actions.SUPPORT_TICKET_ESCALATED, resource_type="support_ticket", resource_id=ticket.ticket_number, **extract_audit_metadata(request))
        return SuccessResponse(data=SupportAdminTicketDetailSerializer(ticket).data, message="تیکت ارجاع فوری شد.")


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
            ticket = services.close_ticket(ticket=ticket, actor=request.user, reason=serializer.validated_data.get("reason", ""))
        except (services.SupportPermissionError, services.SupportTicketStateError) as exc:
            return _service_error_response(exc, status_code=status.HTTP_403_FORBIDDEN)
        log_action_async(user_id=request.user.pk, action=audit_actions.SUPPORT_TICKET_CLOSED, resource_type="support_ticket", resource_id=ticket.ticket_number, **extract_audit_metadata(request))
        return SuccessResponse(data=SupportAdminTicketDetailSerializer(ticket).data, message="تیکت بسته شد.")


class SupportAdminDuplicateCandidateListView(APIView):
    """Admin duplicate candidate list endpoint."""

    permission_classes = [IsSupportAdminUser]
    serializer_class = SupportDuplicateCandidateSerializer

    def get(self, request: Request) -> Response:
        """Return duplicate candidates."""
        queryset = selectors.get_admin_duplicate_candidates()
        filterset = SupportDuplicateCandidateAdminFilter(request.query_params, queryset=queryset)
        if filterset.is_valid():
            queryset = filterset.qs
        paginator = StandardPagination()
        page = paginator.paginate_queryset(queryset, request, view=self)
        return paginator.get_paginated_response(SupportDuplicateCandidateSerializer(page, many=True).data)


class SupportAdminDuplicateCandidateReviewView(APIView):
    """Admin duplicate candidate review endpoint."""

    permission_classes = [IsSupportAdminUser]
    serializer_class = SupportDuplicateCandidateSerializer

    def post(self, request: Request, duplicate_id: int) -> SuccessResponse | ErrorResponse:
        """Review duplicate candidate."""
        duplicate = selectors.get_admin_duplicate_candidate_by_id(duplicate_id=duplicate_id)
        if duplicate is None:
            return ErrorResponse(message="کاندیدای تکراری یافت نشد.", status_code=status.HTTP_404_NOT_FOUND)
        serializer = SupportDuplicateReviewSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        duplicate = services.review_duplicate_candidate(duplicate=duplicate, admin=request.user, **serializer.validated_data)
        log_action_async(user_id=request.user.pk, action=audit_actions.SUPPORT_DUPLICATE_REVIEWED, resource_type="support_duplicate_candidate", resource_id=str(duplicate.pk), **extract_audit_metadata(request))
        return SuccessResponse(data=SupportDuplicateCandidateSerializer(duplicate).data, message="وضعیت کاندیدای تکراری بروزرسانی شد.")


ADMIN_ANALYTICS_RESPONSE = build_success_response_serializer(name="SupportAdminAnalyticsResponse", data_serializer=SupportAdminAnalyticsSerializer)


class SupportAdminAnalyticsView(APIView):
    """Admin support analytics dashboard."""

    permission_classes = [IsSupportAdminUser]
    serializer_class = SupportAdminAnalyticsSerializer

    @extend_schema(operation_id="support_admin_analytics", tags=[TAG_SUPPORT_USER], responses={200: ADMIN_ANALYTICS_RESPONSE})
    def get(self, request: Request) -> SuccessResponse:
        """Return support desk analytics summary."""
        return SuccessResponse(data=services.get_admin_analytics_summary(), message="گزارش تحلیلی میز پشتیبانی دریافت شد.")


class SupportAdminTicketExportView(APIView):
    """Admin Excel export for support tickets."""

    permission_classes = [IsSupportAdminUser]

    @extend_schema(operation_id="support_admin_export_tickets", tags=[TAG_SUPPORT_USER], responses={200: None})
    def get(self, request: Request) -> HttpResponse:
        """Export filtered ticket queue as an RTL Excel workbook."""
        queryset = selectors.get_admin_tickets()
        filterset = SupportAdminTicketFilter(request.query_params, queryset=queryset)
        if filterset.is_valid():
            queryset = filterset.qs
        workbook = build_tickets_workbook(tickets=queryset)
        filename = build_support_export_filename(export_type="tickets")
        log_action_async(user_id=request.user.pk, action=audit_actions.SUPPORT_EXPORT_GENERATED, resource_type="support_ticket", resource_id="bulk", extra_data={"filename": filename, "export_type": "tickets"}, **extract_audit_metadata(request))
        response = HttpResponse(workbook.getvalue(), content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
        response["Content-Disposition"] = f'attachment; filename="{filename}"'
        return response


class SupportAdminMessageExportView(APIView):
    """Admin Excel export for support messages."""

    permission_classes = [IsSupportAdminUser]

    @extend_schema(operation_id="support_admin_export_messages", tags=[TAG_SUPPORT_USER], responses={200: None})
    def get(self, request: Request) -> HttpResponse:
        """Export timeline messages as an RTL Excel workbook."""
        workbook = build_messages_workbook(messages=selectors.get_admin_messages())
        filename = build_support_export_filename(export_type="messages")
        log_action_async(user_id=request.user.pk, action=audit_actions.SUPPORT_EXPORT_GENERATED, resource_type="support_ticket_message", resource_id="bulk", extra_data={"filename": filename, "export_type": "messages"}, **extract_audit_metadata(request))
        response = HttpResponse(workbook.getvalue(), content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
        response["Content-Disposition"] = f'attachment; filename="{filename}"'
        return response


class SupportAdminSLAExportView(APIView):
    """Admin Excel export for SLA reporting."""

    permission_classes = [IsSupportAdminUser]

    @extend_schema(operation_id="support_admin_export_sla", tags=[TAG_SUPPORT_USER], responses={200: None})
    def get(self, request: Request) -> HttpResponse:
        """Export SLA ticket data as an RTL Excel workbook."""
        workbook = build_sla_workbook(tickets=selectors.get_admin_sla_tickets())
        filename = build_support_export_filename(export_type="sla")
        log_action_async(user_id=request.user.pk, action=audit_actions.SUPPORT_EXPORT_GENERATED, resource_type="support_sla", resource_id="bulk", extra_data={"filename": filename, "export_type": "sla"}, **extract_audit_metadata(request))
        response = HttpResponse(workbook.getvalue(), content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
        response["Content-Disposition"] = f'attachment; filename="{filename}"'
        return response


class SupportAdminCSATExportView(APIView):
    """Admin Excel export for CSAT ratings."""

    permission_classes = [IsSupportAdminUser]

    @extend_schema(operation_id="support_admin_export_csat", tags=[TAG_SUPPORT_USER], responses={200: None})
    def get(self, request: Request) -> HttpResponse:
        """Export CSAT data as an RTL Excel workbook."""
        workbook = build_csat_workbook(ratings=selectors.get_admin_satisfaction_ratings())
        filename = build_support_export_filename(export_type="csat")
        log_action_async(user_id=request.user.pk, action=audit_actions.SUPPORT_EXPORT_GENERATED, resource_type="support_csat", resource_id="bulk", extra_data={"filename": filename, "export_type": "csat"}, **extract_audit_metadata(request))
        response = HttpResponse(workbook.getvalue(), content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
        response["Content-Disposition"] = f'attachment; filename="{filename}"'
        return response

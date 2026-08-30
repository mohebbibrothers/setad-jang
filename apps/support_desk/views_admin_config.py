"""گروه دامنه‌ای `views_admin_config` از views — فاز ۱۱ (تفکیک P3-16).

کلاس‌ها عیناً منتقل شده‌اند؛ مشترکات از views_common؛ نامِ عمومیِ این گروه‌ها را فقط از facade (apps.*.views) یا همین ماژول import کنید.
"""

from __future__ import annotations

from drf_spectacular.utils import extend_schema
from rest_framework import status
from rest_framework.request import Request
from rest_framework.views import APIView

from apps.audit_logs import actions as audit_actions
from apps.audit_logs.helpers import extract_audit_metadata
from apps.audit_logs.services import log_action_async
from apps.core.responses import CreatedResponse, ErrorResponse, SuccessResponse
from apps.core.schemas import (
    build_success_response_serializer,
)
from apps.support_desk import selectors, services
from apps.support_desk.permissions import IsSupportAdminUser
from apps.support_desk.serializers import (
    SupportBusinessCalendarInputSerializer,
    SupportBusinessCalendarSerializer,
    SupportCannedResponseInputSerializer,
    SupportCannedResponseSerializer,
    SupportCategoryInputSerializer,
    SupportCategorySerializer,
    SupportDepartmentInputSerializer,
    SupportDepartmentSerializer,
    SupportHolidayInputSerializer,
    SupportHolidaySerializer,
    SupportSLAPolicyInputSerializer,
    SupportSLAPolicySerializer,
    SupportTicketTypeInputSerializer,
    SupportTicketTypeSerializer,
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


class SupportAdminDepartmentListCreateView(APIView):
    """Admin department list/create endpoint."""

    permission_classes = [IsSupportAdminUser]
    serializer_class = SupportDepartmentSerializer

    @extend_schema(
        operation_id="support_admin_departments_list",
        tags=[TAG_SUPPORT_TAXONOMY],
        responses={
            200: build_success_response_serializer(
                name="SupportAdminDepartmentListResponse",
                data_serializer=SupportDepartmentSerializer,
                many=True,
            )
        },
    )
    def get(self, request: Request) -> SuccessResponse:
        """Return all departments for admin taxonomy management."""
        return SuccessResponse(
            data=SupportDepartmentSerializer(selectors.get_admin_departments(), many=True).data
        )

    def post(self, request: Request) -> CreatedResponse:
        """Create support department."""
        serializer = SupportDepartmentInputSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        department = services.create_department(**serializer.validated_data)
        log_action_async(
            user_id=request.user.pk,
            action=audit_actions.SUPPORT_DEPARTMENT_CREATED,
            resource_type="support_department",
            resource_id=str(department.pk),
            **extract_audit_metadata(request),
        )
        return CreatedResponse(
            data=SupportDepartmentSerializer(department).data, message="دپارتمان پشتیبانی ساخته شد."
        )


class SupportAdminDepartmentDetailView(APIView):
    """Admin department detail/update/deactivate endpoint."""

    permission_classes = [IsSupportAdminUser]
    serializer_class = SupportDepartmentSerializer

    @extend_schema(
        operation_id="support_admin_departments_retrieve",
        tags=[TAG_SUPPORT_TAXONOMY],
        responses={200: ADMIN_DEPARTMENT_RESPONSE, 404: SUPPORT_ERROR_RESPONSE},
    )
    def get(self, request: Request, department_id: int) -> SuccessResponse | ErrorResponse:
        """Return one department."""
        department = selectors.get_admin_department_by_id(department_id=department_id)
        if department is None:
            return ErrorResponse(
                message="دپارتمان یافت نشد.", status_code=status.HTTP_404_NOT_FOUND
            )
        return SuccessResponse(data=SupportDepartmentSerializer(department).data)

    def patch(self, request: Request, department_id: int) -> SuccessResponse | ErrorResponse:
        """Update department."""
        department = selectors.get_admin_department_by_id(department_id=department_id)
        if department is None:
            return ErrorResponse(
                message="دپارتمان یافت نشد.", status_code=status.HTTP_404_NOT_FOUND
            )
        serializer = SupportDepartmentInputSerializer(data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        department = services.update_department(department=department, **serializer.validated_data)
        log_action_async(
            user_id=request.user.pk,
            action=audit_actions.SUPPORT_DEPARTMENT_UPDATED,
            resource_type="support_department",
            resource_id=str(department.pk),
            **extract_audit_metadata(request),
        )
        return SuccessResponse(
            data=SupportDepartmentSerializer(department).data, message="دپارتمان بروزرسانی شد."
        )

    def delete(self, request: Request, department_id: int) -> SuccessResponse | ErrorResponse:
        """Deactivate department safely."""
        department = selectors.get_admin_department_by_id(department_id=department_id)
        if department is None:
            return ErrorResponse(
                message="دپارتمان یافت نشد.", status_code=status.HTTP_404_NOT_FOUND
            )
        try:
            department = services.deactivate_department(department=department)
        except services.SupportDeskServiceError as exc:
            return _service_error_response(exc)
        log_action_async(
            user_id=request.user.pk,
            action=audit_actions.SUPPORT_DEPARTMENT_DEACTIVATED,
            resource_type="support_department",
            resource_id=str(department.pk),
            **extract_audit_metadata(request),
        )
        return SuccessResponse(
            data=SupportDepartmentSerializer(department).data, message="دپارتمان غیرفعال شد."
        )


class SupportAdminCategoryListCreateView(APIView):
    """Admin category tree list/create endpoint."""

    permission_classes = [IsSupportAdminUser]
    serializer_class = SupportCategorySerializer

    def get(self, request: Request) -> SuccessResponse:
        """Return all categories for admin tree management."""
        return SuccessResponse(
            data=SupportCategorySerializer(selectors.get_admin_category_tree(), many=True).data
        )

    def post(self, request: Request) -> CreatedResponse | ErrorResponse:
        """Create support category."""
        serializer = SupportCategoryInputSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            category = services.create_category(**serializer.validated_data)
        except services.SupportTaxonomyTreeError as exc:
            return _service_error_response(exc)
        log_action_async(
            user_id=request.user.pk,
            action=audit_actions.SUPPORT_CATEGORY_CREATED,
            resource_type="support_category",
            resource_id=str(category.pk),
            **extract_audit_metadata(request),
        )
        return CreatedResponse(
            data=SupportCategorySerializer(category).data, message="دسته‌بندی پشتیبانی ساخته شد."
        )


class SupportAdminCategoryDetailView(APIView):
    """Admin category detail/update/deactivate endpoint."""

    permission_classes = [IsSupportAdminUser]
    serializer_class = SupportCategorySerializer

    def patch(self, request: Request, category_id: int) -> SuccessResponse | ErrorResponse:
        """Update category tree node."""
        category = selectors.get_admin_category_by_id(category_id=category_id)
        if category is None:
            return ErrorResponse(
                message="دسته‌بندی یافت نشد.", status_code=status.HTTP_404_NOT_FOUND
            )
        serializer = SupportCategoryInputSerializer(data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        try:
            category = services.update_category(category=category, **serializer.validated_data)
        except services.SupportTaxonomyTreeError as exc:
            return _service_error_response(exc)
        log_action_async(
            user_id=request.user.pk,
            action=audit_actions.SUPPORT_CATEGORY_UPDATED,
            resource_type="support_category",
            resource_id=str(category.pk),
            **extract_audit_metadata(request),
        )
        return SuccessResponse(
            data=SupportCategorySerializer(category).data, message="دسته‌بندی بروزرسانی شد."
        )

    def delete(self, request: Request, category_id: int) -> SuccessResponse | ErrorResponse:
        """Deactivate category safely."""
        category = selectors.get_admin_category_by_id(category_id=category_id)
        if category is None:
            return ErrorResponse(
                message="دسته‌بندی یافت نشد.", status_code=status.HTTP_404_NOT_FOUND
            )
        try:
            category = services.deactivate_category(category=category)
        except services.SupportTaxonomyTreeError as exc:
            return _service_error_response(exc)
        log_action_async(
            user_id=request.user.pk,
            action=audit_actions.SUPPORT_CATEGORY_DEACTIVATED,
            resource_type="support_category",
            resource_id=str(category.pk),
            **extract_audit_metadata(request),
        )
        return SuccessResponse(
            data=SupportCategorySerializer(category).data, message="دسته‌بندی غیرفعال شد."
        )


class SupportAdminTicketTypeListCreateView(APIView):
    """Admin ticket type list/create endpoint."""

    permission_classes = [IsSupportAdminUser]
    serializer_class = SupportTicketTypeSerializer

    def get(self, request: Request) -> SuccessResponse:
        """Return ticket types."""
        return SuccessResponse(
            data=SupportTicketTypeSerializer(selectors.get_admin_ticket_types(), many=True).data
        )

    def post(self, request: Request) -> CreatedResponse | ErrorResponse:
        """Create ticket type."""
        serializer = SupportTicketTypeInputSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            ticket_type = services.create_ticket_type(**serializer.validated_data)
        except services.SupportDeskServiceError as exc:
            return _service_error_response(exc)
        log_action_async(
            user_id=request.user.pk,
            action=audit_actions.SUPPORT_TICKET_TYPE_CREATED,
            resource_type="support_ticket_type",
            resource_id=str(ticket_type.pk),
            **extract_audit_metadata(request),
        )
        return CreatedResponse(
            data=SupportTicketTypeSerializer(ticket_type).data, message="نوع تیکت ساخته شد."
        )


class SupportAdminTicketTypeDetailView(APIView):
    """Admin ticket type update endpoint."""

    permission_classes = [IsSupportAdminUser]
    serializer_class = SupportTicketTypeSerializer

    def patch(self, request: Request, ticket_type_id: int) -> SuccessResponse | ErrorResponse:
        """Update ticket type."""
        ticket_type = selectors.get_admin_ticket_type_by_id(ticket_type_id=ticket_type_id)
        if ticket_type is None:
            return ErrorResponse(
                message="نوع تیکت یافت نشد.", status_code=status.HTTP_404_NOT_FOUND
            )
        serializer = SupportTicketTypeInputSerializer(data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        try:
            ticket_type = services.update_ticket_type(
                ticket_type=ticket_type, **serializer.validated_data
            )
        except services.SupportDeskServiceError as exc:
            return _service_error_response(exc)
        log_action_async(
            user_id=request.user.pk,
            action=audit_actions.SUPPORT_TICKET_TYPE_UPDATED,
            resource_type="support_ticket_type",
            resource_id=str(ticket_type.pk),
            **extract_audit_metadata(request),
        )
        return SuccessResponse(
            data=SupportTicketTypeSerializer(ticket_type).data, message="نوع تیکت بروزرسانی شد."
        )


class SupportAdminBusinessCalendarListCreateView(APIView):
    """Admin business calendar list/create endpoint."""

    permission_classes = [IsSupportAdminUser]
    serializer_class = SupportBusinessCalendarSerializer

    def get(self, request: Request) -> SuccessResponse:
        """Return business calendars."""
        return SuccessResponse(
            data=SupportBusinessCalendarSerializer(
                selectors.get_admin_business_calendars(), many=True
            ).data
        )

    def post(self, request: Request) -> CreatedResponse:
        """Create business calendar."""
        serializer = SupportBusinessCalendarInputSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        calendar = services.create_business_calendar(**serializer.validated_data)
        return CreatedResponse(
            data=SupportBusinessCalendarSerializer(calendar).data, message="تقویم کاری ساخته شد."
        )


class SupportAdminBusinessCalendarDetailView(APIView):
    """Admin business calendar update endpoint."""

    permission_classes = [IsSupportAdminUser]
    serializer_class = SupportBusinessCalendarSerializer

    def patch(self, request: Request, calendar_id: int) -> SuccessResponse | ErrorResponse:
        """Update business calendar."""
        calendar = selectors.get_admin_business_calendar_by_id(calendar_id=calendar_id)
        if calendar is None:
            return ErrorResponse(
                message="تقویم کاری یافت نشد.", status_code=status.HTTP_404_NOT_FOUND
            )
        serializer = SupportBusinessCalendarInputSerializer(data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        calendar = services.update_business_calendar(calendar=calendar, **serializer.validated_data)
        return SuccessResponse(
            data=SupportBusinessCalendarSerializer(calendar).data,
            message="تقویم کاری بروزرسانی شد.",
        )


class SupportAdminHolidayListCreateView(APIView):
    """Admin support holiday list/create endpoint."""

    permission_classes = [IsSupportAdminUser]
    serializer_class = SupportHolidaySerializer

    def get(self, request: Request) -> SuccessResponse:
        """Return support holidays."""
        return SuccessResponse(
            data=SupportHolidaySerializer(selectors.get_admin_holidays(), many=True).data
        )

    def post(self, request: Request) -> CreatedResponse:
        """Create support holiday."""
        serializer = SupportHolidayInputSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        holiday = services.create_holiday(**serializer.validated_data)
        return CreatedResponse(
            data=SupportHolidaySerializer(holiday).data, message="تعطیلی پشتیبانی ثبت شد."
        )


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
        return SuccessResponse(
            data=SupportHolidaySerializer(holiday).data, message="تعطیلی بروزرسانی شد."
        )


class SupportAdminSLAPolicyListCreateView(APIView):
    """Admin SLA policy list/create endpoint."""

    permission_classes = [IsSupportAdminUser]
    serializer_class = SupportSLAPolicySerializer

    def get(self, request: Request) -> SuccessResponse:
        """Return SLA policies."""
        return SuccessResponse(
            data=SupportSLAPolicySerializer(selectors.get_admin_sla_policies(), many=True).data
        )

    def post(self, request: Request) -> CreatedResponse:
        """Create SLA policy."""
        serializer = SupportSLAPolicyInputSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        policy = services.create_sla_policy(**serializer.validated_data)
        log_action_async(
            user_id=request.user.pk,
            action=audit_actions.SUPPORT_SLA_POLICY_CREATED,
            resource_type="support_sla_policy",
            resource_id=str(policy.pk),
            **extract_audit_metadata(request),
        )
        return CreatedResponse(
            data=SupportSLAPolicySerializer(policy).data, message="سیاست SLA ساخته شد."
        )


class SupportAdminSLAPolicyDetailView(APIView):
    """Admin SLA policy update endpoint."""

    permission_classes = [IsSupportAdminUser]
    serializer_class = SupportSLAPolicySerializer

    def patch(self, request: Request, policy_id: int) -> SuccessResponse | ErrorResponse:
        """Update SLA policy."""
        policy = selectors.get_admin_sla_policy_by_id(policy_id=policy_id)
        if policy is None:
            return ErrorResponse(
                message="سیاست SLA یافت نشد.", status_code=status.HTTP_404_NOT_FOUND
            )
        serializer = SupportSLAPolicyInputSerializer(data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        policy = services.update_sla_policy(policy=policy, **serializer.validated_data)
        log_action_async(
            user_id=request.user.pk,
            action=audit_actions.SUPPORT_SLA_POLICY_UPDATED,
            resource_type="support_sla_policy",
            resource_id=str(policy.pk),
            **extract_audit_metadata(request),
        )
        return SuccessResponse(
            data=SupportSLAPolicySerializer(policy).data, message="سیاست SLA بروزرسانی شد."
        )


class SupportAdminCannedResponseListCreateView(APIView):
    """Admin canned response list/create endpoint."""

    permission_classes = [IsSupportAdminUser]
    serializer_class = SupportCannedResponseSerializer

    def get(self, request: Request) -> SuccessResponse:
        """Return canned responses."""
        return SuccessResponse(
            data=SupportCannedResponseSerializer(
                selectors.get_admin_canned_responses(), many=True
            ).data
        )

    def post(self, request: Request) -> CreatedResponse | ErrorResponse:
        """Create canned response."""
        serializer = SupportCannedResponseInputSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            canned = services.create_canned_response(**serializer.validated_data)
        except services.SupportDeskServiceError as exc:
            return _service_error_response(exc)
        log_action_async(
            user_id=request.user.pk,
            action=audit_actions.SUPPORT_CANNED_RESPONSE_CREATED,
            resource_type="support_canned_response",
            resource_id=str(canned.pk),
            **extract_audit_metadata(request),
        )
        return CreatedResponse(
            data=SupportCannedResponseSerializer(canned).data, message="پاسخ آماده ساخته شد."
        )


class SupportAdminCannedResponseDetailView(APIView):
    """Admin canned response update/use endpoint."""

    permission_classes = [IsSupportAdminUser]
    serializer_class = SupportCannedResponseSerializer

    def patch(self, request: Request, canned_response_id: int) -> SuccessResponse | ErrorResponse:
        """Update canned response."""
        canned = selectors.get_admin_canned_response_by_id(canned_response_id=canned_response_id)
        if canned is None:
            return ErrorResponse(
                message="پاسخ آماده یافت نشد.", status_code=status.HTTP_404_NOT_FOUND
            )
        serializer = SupportCannedResponseInputSerializer(data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        try:
            canned = services.update_canned_response(
                canned_response=canned, **serializer.validated_data
            )
        except services.SupportDeskServiceError as exc:
            return _service_error_response(exc)
        return SuccessResponse(
            data=SupportCannedResponseSerializer(canned).data, message="پاسخ آماده بروزرسانی شد."
        )


class SupportAdminCannedResponseUseView(APIView):
    """Admin canned response usage counter endpoint."""

    permission_classes = [IsSupportAdminUser]
    serializer_class = SupportCannedResponseSerializer

    def post(self, request: Request, canned_response_id: int) -> SuccessResponse | ErrorResponse:
        """Mark canned response as used."""
        canned = selectors.get_admin_canned_response_by_id(canned_response_id=canned_response_id)
        if canned is None:
            return ErrorResponse(
                message="پاسخ آماده یافت نشد.", status_code=status.HTTP_404_NOT_FOUND
            )
        canned = services.use_canned_response(canned_response=canned)
        log_action_async(
            user_id=request.user.pk,
            action=audit_actions.SUPPORT_CANNED_RESPONSE_USED,
            resource_type="support_canned_response",
            resource_id=str(canned.pk),
            **extract_audit_metadata(request),
        )
        return SuccessResponse(
            data=SupportCannedResponseSerializer(canned).data,
            message="استفاده از پاسخ آماده ثبت شد.",
        )

"""گروه دامنه‌ای `views_public` از views — فاز ۱۱ (تفکیک P3-16).

کلاس‌ها عیناً منتقل شده‌اند؛ مشترکات از views_common؛ نامِ عمومیِ این گروه‌ها را فقط از facade (apps.*.views) یا همین ماژول import کنید.
"""

from __future__ import annotations

from drf_spectacular.utils import extend_schema
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.views import APIView

from apps.core.responses import SuccessResponse
from apps.support_desk import selectors, services
from apps.support_desk.serializers import (
    SupportCategorySerializer,
    SupportDepartmentSerializer,
    SupportTicketSuggestSerializer,
    SupportTicketTypeSerializer,
    SupportTriageSuggestionSerializer,
)
from apps.support_desk.throttles import (
    SupportSuggestThrottle,
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


class SupportDepartmentListView(APIView):
    """Authenticated users can browse active support departments."""

    permission_classes = [IsAuthenticated]

    @extend_schema(
        operation_id="support_departments_list",
        tags=[TAG_SUPPORT_TAXONOMY],
        responses={200: DEPARTMENT_LIST_RESPONSE, 401: SUPPORT_ERROR_RESPONSE},
    )
    def get(self, request: Request) -> SuccessResponse:
        """Return active support departments."""
        return SuccessResponse(
            data=SupportDepartmentSerializer(selectors.get_active_departments(), many=True).data
        )


class SupportCategoryListView(APIView):
    """Authenticated users can browse active support category tree."""

    permission_classes = [IsAuthenticated]

    @extend_schema(
        operation_id="support_categories_list",
        tags=[TAG_SUPPORT_TAXONOMY],
        responses={200: CATEGORY_LIST_RESPONSE},
    )
    def get(self, request: Request) -> SuccessResponse:
        """Return active support categories."""
        return SuccessResponse(
            data=SupportCategorySerializer(selectors.get_active_category_tree(), many=True).data
        )


class SupportTicketTypeListView(APIView):
    """Authenticated users can browse dynamic ticket types."""

    permission_classes = [IsAuthenticated]

    @extend_schema(
        operation_id="support_ticket_types_list",
        tags=[TAG_SUPPORT_TAXONOMY],
        responses={200: TICKET_TYPE_LIST_RESPONSE},
    )
    def get(self, request: Request) -> SuccessResponse:
        """Return active support ticket types."""
        return SuccessResponse(
            data=SupportTicketTypeSerializer(selectors.get_active_ticket_types(), many=True).data
        )


class SupportTicketSuggestView(APIView):
    """Smart triage suggestion endpoint before creating a ticket."""

    permission_classes = [IsAuthenticated]
    throttle_classes = [SupportSuggestThrottle]

    @extend_schema(
        operation_id="support_user_tickets_suggest",
        tags=[TAG_SUPPORT_USER],
        request=SupportTicketSuggestSerializer,
        responses={200: TRIAGE_RESPONSE},
    )
    def post(self, request: Request) -> SuccessResponse:
        """Return smart triage suggestions and duplicate warning."""
        serializer = SupportTicketSuggestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        suggestion = services.suggest_ticket_triage(owner=request.user, **serializer.validated_data)
        return SuccessResponse(
            data=SupportTriageSuggestionSerializer(suggestion).data,
            message="پیشنهاد هوشمند تریاژ دریافت شد.",
        )

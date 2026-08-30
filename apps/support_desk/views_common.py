"""مشترکات views — constants/helpers که گروه‌های دامنه‌ای import می‌کنند.

با ابزار split_views در فاز ۱۱ از views.py جدا شد؛ منطق دست‌نخورده است(برشِ verbatim). facade در views.py همه را دوباره export می‌کند تا مسیرهایimport بیرونی (urls/tests) تغییر نکنند.
"""

from __future__ import annotations

from rest_framework import status
from rest_framework.request import Request

from apps.core.responses import ErrorResponse
from apps.core.schemas import (
    build_error_response_serializer,
    build_paginated_success_response_serializer,
    build_success_response_serializer,
)
from apps.support_desk import selectors, services
from apps.support_desk.serializers import (
    SupportAdminAnalyticsSerializer,
    SupportAdminTicketDetailSerializer,
    SupportAssignmentRecommendationSerializer,
    SupportCannedResponseSerializer,
    SupportCategorySerializer,
    SupportDepartmentSerializer,
    SupportDuplicateCandidateSerializer,
    SupportKnowledgeArticleSerializer,
    SupportKnowledgeArticleUseSerializer,
    SupportSLAPolicySerializer,
    SupportSmartReplyBundleSerializer,
    SupportTicketAttachmentSerializer,
    SupportTicketDetailSerializer,
    SupportTicketListSerializer,
    SupportTicketMessageSerializer,
    SupportTicketTypeSerializer,
    SupportTriageSuggestionSerializer,
)

TAG_SUPPORT_USER = "میز پشتیبانی — کاربر"
TAG_SUPPORT_TAXONOMY = "میز پشتیبانی — دسته‌بندی"
SUPPORT_ERROR_RESPONSE = build_error_response_serializer(name="SupportDeskErrorResponse")
DEPARTMENT_LIST_RESPONSE = build_success_response_serializer(
    name="SupportDepartmentListResponse", data_serializer=SupportDepartmentSerializer, many=True
)
CATEGORY_LIST_RESPONSE = build_success_response_serializer(
    name="SupportCategoryListResponse", data_serializer=SupportCategorySerializer, many=True
)
TICKET_TYPE_LIST_RESPONSE = build_success_response_serializer(
    name="SupportTicketTypeListResponse", data_serializer=SupportTicketTypeSerializer, many=True
)
TICKET_LIST_RESPONSE = build_paginated_success_response_serializer(
    name="SupportTicketListResponse", item_serializer=SupportTicketListSerializer
)
TICKET_DETAIL_RESPONSE = build_success_response_serializer(
    name="SupportTicketDetailResponse", data_serializer=SupportTicketDetailSerializer
)
KNOWLEDGE_ARTICLE_LIST_RESPONSE = build_paginated_success_response_serializer(
    name="SupportKnowledgeArticleListResponse", item_serializer=SupportKnowledgeArticleSerializer
)
KNOWLEDGE_ARTICLE_DETAIL_RESPONSE = build_success_response_serializer(
    name="SupportKnowledgeArticleDetailResponse", data_serializer=SupportKnowledgeArticleSerializer
)
KNOWLEDGE_ARTICLE_USE_RESPONSE = build_success_response_serializer(
    name="SupportKnowledgeArticleUseResponse", data_serializer=SupportKnowledgeArticleUseSerializer
)
MESSAGE_LIST_RESPONSE = build_success_response_serializer(
    name="SupportTicketTimelineResponse", data_serializer=SupportTicketMessageSerializer, many=True
)
ATTACHMENT_RESPONSE = build_success_response_serializer(
    name="SupportTicketAttachmentResponse", data_serializer=SupportTicketAttachmentSerializer
)
TRIAGE_RESPONSE = build_success_response_serializer(
    name="SupportTriageSuggestionResponse", data_serializer=SupportTriageSuggestionSerializer
)
ASSIGNMENT_RECOMMENDATION_RESPONSE = build_success_response_serializer(
    name="SupportAssignmentRecommendationResponse",
    data_serializer=SupportAssignmentRecommendationSerializer,
)
SMART_REPLY_BUNDLE_RESPONSE = build_success_response_serializer(
    name="SupportSmartReplyBundleResponse", data_serializer=SupportSmartReplyBundleSerializer
)


def _service_error_response(
    exc: Exception, *, status_code: int = status.HTTP_400_BAD_REQUEST
) -> ErrorResponse:
    """Convert service-layer exception to project error response."""
    return ErrorResponse(message=str(exc), status_code=status_code)


def _get_user_ticket_or_error(*, request: Request, ticket_number: str):
    """Return user ticket or a standardized 404 response."""
    ticket = selectors.get_user_ticket_by_number(
        user_id=request.user.pk, ticket_number=ticket_number
    )
    if ticket is None:
        return None, ErrorResponse(message="تیکت یافت نشد.", status_code=status.HTTP_404_NOT_FOUND)
    return ticket, None


ADMIN_TICKET_LIST_RESPONSE = build_paginated_success_response_serializer(
    name="SupportAdminTicketListResponse", item_serializer=SupportTicketListSerializer
)
ADMIN_TICKET_DETAIL_RESPONSE = build_success_response_serializer(
    name="SupportAdminTicketDetailResponse", data_serializer=SupportAdminTicketDetailSerializer
)
ADMIN_DEPARTMENT_RESPONSE = build_success_response_serializer(
    name="SupportAdminDepartmentResponse", data_serializer=SupportDepartmentSerializer
)
ADMIN_CATEGORY_RESPONSE = build_success_response_serializer(
    name="SupportAdminCategoryResponse", data_serializer=SupportCategorySerializer
)
ADMIN_TICKET_TYPE_RESPONSE = build_success_response_serializer(
    name="SupportAdminTicketTypeResponse", data_serializer=SupportTicketTypeSerializer
)
ADMIN_SLA_RESPONSE = build_success_response_serializer(
    name="SupportAdminSLAPolicyResponse", data_serializer=SupportSLAPolicySerializer
)
ADMIN_CANNED_RESPONSE = build_success_response_serializer(
    name="SupportAdminCannedResponseResponse", data_serializer=SupportCannedResponseSerializer
)
ADMIN_DUPLICATE_RESPONSE = build_success_response_serializer(
    name="SupportAdminDuplicateCandidateResponse",
    data_serializer=SupportDuplicateCandidateSerializer,
)


def _serialize_assignment_recommendation(
    recommendation: services.SupportAssignmentRecommendation,
) -> dict:
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
                "user_display_name": getattr(candidate.user, "full_name", "")
                or getattr(candidate.user, "email", "")
                or f"user#{candidate.user.pk}",
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


def _serialize_smart_reply_bundle(bundle: services.SupportSmartReplyBundle) -> dict:
    """Serialize smart reply dataclass bundle for API response."""
    return {
        "ticket_number": bundle.ticket.ticket_number,
        "policy_version": bundle.policy_version,
        "safety_notes": bundle.safety_notes,
        "suggestions": [
            {
                "title": suggestion.title,
                "body": suggestion.body,
                "source_type": suggestion.source_type,
                "source_id": suggestion.source_id,
                "confidence": suggestion.confidence,
                "reason_codes": suggestion.reason_codes,
            }
            for suggestion in bundle.suggestions
        ],
    }


ADMIN_ANALYTICS_RESPONSE = build_success_response_serializer(
    name="SupportAdminAnalyticsResponse", data_serializer=SupportAdminAnalyticsSerializer
)

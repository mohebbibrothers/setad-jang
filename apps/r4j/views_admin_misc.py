"""گروه دامنه‌ای `views_admin_misc` از views — فاز ۱۱ (تفکیک P3-16).

کلاس‌ها عیناً منتقل شده‌اند؛ مشترکات از views_common؛ نامِ عمومیِ این گروه‌ها را فقط از facade (apps.*.views) یا همین ماژول import کنید.
"""

from __future__ import annotations

from drf_spectacular.utils import (
    extend_schema,
    extend_schema_view,
)
from rest_framework import status
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
    R4JBountyUserFilter,
)
from .permissions import IsR4JAdminUser
from .serializers import (
    R4JEvidenceCustodyEventSerializer,
    R4JEvidenceCustodyReviewSerializer,
    R4JUserBountySerializer,
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
# User — Bounties
# ============================================================


@extend_schema_view(
    get=extend_schema(
        operation_id="r4j_user_my_bounties_list",
        tags=[TAG_R4J_BOUNTY],
        summary="لیست جوایز من",
        description="دریافت لیست تمام جوایزی که توسط کاربر جاری تعیین شده‌اند.",
        parameters=USER_BOUNTY_FILTER_PARAMS,
        responses={
            200: USER_BOUNTY_LIST_RESPONSE,
            401: GENERIC_ERROR_RESPONSE,
        },
    ),
)
class R4JUserMyBountiesListView(APIView):
    """لیست bountyهای کاربر جاری."""

    permission_classes = [IsAuthenticated]

    def get(self, request: Request) -> Response:
        queryset = selectors.get_user_bounties_queryset(user_id=request.user.pk)
        filterset = R4JBountyUserFilter(request.query_params, queryset=queryset)
        if filterset.is_valid():
            queryset = filterset.qs

        paginator = StandardPagination()
        page = paginator.paginate_queryset(queryset, request, view=self)

        if page is not None:
            serializer = R4JUserBountySerializer(page, many=True)
            return paginator.get_paginated_response(
                serializer.data,
                message="لیست جوایز با موفقیت دریافت شد.",
            )

        serializer = R4JUserBountySerializer(queryset, many=True)
        return SuccessResponse(
            data=serializer.data,
            message="لیست جوایز با موفقیت دریافت شد.",
        )


class R4JAdminEvidenceCustodyListView(APIView):
    """Admin list endpoint for evidence chain-of-custody events."""

    permission_classes = [IsR4JAdminUser]

    @extend_schema(
        operation_id="r4j_admin_evidence_custody_list",
        tags=[TAG_R4J_ADMIN],
        summary="لیست زنجیره نگهداری شواهد",
        responses={200: ADMIN_CUSTODY_EVENT_LIST_RESPONSE},
    )
    def get(self, request: Request) -> Response:
        queryset = selectors.get_admin_evidence_custody_events()
        event_type = request.query_params.get("event_type")
        if event_type:
            queryset = queryset.filter(event_type=event_type)
        file_hash = request.query_params.get("file_sha256")
        if file_hash:
            queryset = queryset.filter(file_sha256=file_hash)
        paginator = StandardPagination()
        page = paginator.paginate_queryset(queryset, request, view=self)
        serializer = R4JEvidenceCustodyEventSerializer(page, many=True)
        return paginator.get_paginated_response(
            serializer.data, message="زنجیره نگهداری شواهد دریافت شد."
        )


class R4JAdminEvidenceCustodyReviewView(APIView):
    """Admin endpoint to append a custody review/transfer/reject event."""

    permission_classes = [IsR4JAdminUser]

    @extend_schema(
        operation_id="r4j_admin_evidence_custody_review",
        tags=[TAG_R4J_ADMIN],
        request=R4JEvidenceCustodyReviewSerializer,
        responses={201: ADMIN_CUSTODY_EVENT_RESPONSE, 404: GENERIC_ERROR_RESPONSE},
    )
    def post(self, request: Request, event_id: int) -> Response:
        event = selectors.get_admin_evidence_custody_event_by_id(event_id=event_id)
        if event is None:
            return ErrorResponse(
                message="رویداد custody یافت نشد.", status_code=status.HTTP_404_NOT_FOUND
            )
        serializer = R4JEvidenceCustodyReviewSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        new_event = services.record_evidence_custody_review(
            event=event,
            actor=request.user,
            event_type=serializer.validated_data["event_type"],
            note=serializer.validated_data.get("note", ""),
        )
        log_action_async(
            user_id=request.user.pk,
            action=audit_actions.R4J_EVIDENCE_CUSTODY_REVIEWED,
            resource_type="r4j_evidence_custody_event",
            resource_id=str(new_event.pk),
            extra_data={"event_type": new_event.event_type, "file_sha256": new_event.file_sha256},
            **extract_audit_metadata(request),
        )
        return CreatedResponse(
            data=R4JEvidenceCustodyEventSerializer(new_event).data, message="رویداد custody ثبت شد."
        )

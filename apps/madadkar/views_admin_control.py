"""گروه دامنه‌ای `views_admin_control` از views — فاز ۱۱ (تفکیک P3-16).

کلاس‌ها عیناً منتقل شده‌اند؛ مشترکات از views_common؛ نامِ عمومیِ این گروه‌ها را فقط از facade (apps.*.views) یا همین ماژول import کنید.
"""

from __future__ import annotations

from drf_spectacular.utils import (
    OpenApiParameter,
    OpenApiTypes,
    extend_schema,
)
from rest_framework import status
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.audit_logs import actions as audit_actions
from apps.audit_logs.helpers import extract_audit_metadata
from apps.audit_logs.services import log_action
from apps.core.pagination import StandardPagination
from apps.core.responses import (
    CreatedResponse,
    ErrorResponse,
    SuccessResponse,
)

from . import selectors, services
from .permissions import (
    IsMadadkarAdminUser,
)
from .serializers import (
    CampaignFinancialControlSummarySerializer,
    MadadkarFinancialControlSnapshotSerializer,
)
from .views_common import (  # noqa: F401 — re-exportِ رایگان برای بدنه‌های منتقل‌شده
    ADMIN_ADJUSTMENT_DETAIL_RESPONSE,
    ADMIN_ADJUSTMENTS_LIST_RESPONSE,
    ADMIN_CAMPAIGN_ANALYTICS_RESPONSE,
    ADMIN_CAMPAIGN_DETAIL_RESPONSE,
    ADMIN_CAMPAIGN_FILTER_PARAMS,
    ADMIN_CAMPAIGN_IMAGE_LIST_RESPONSE,
    ADMIN_CAMPAIGN_IMAGE_RESPONSE,
    ADMIN_CAMPAIGN_INTELLIGENCE_RESPONSE,
    ADMIN_CAMPAIGN_LIST_RESPONSE,
    ADMIN_DISBURSABLE_SUMMARY_RESPONSE,
    ADMIN_DISBURSEMENT_DETAIL_RESPONSE,
    ADMIN_DISBURSEMENT_LIST_RESPONSE,
    ADMIN_FINANCIAL_CONTROL_RESPONSE,
    ADMIN_FINANCIAL_CONTROL_SNAPSHOT_DETAIL_RESPONSE,
    ADMIN_FINANCIAL_CONTROL_SNAPSHOT_LIST_RESPONSE,
    ADMIN_INTELLIGENCE_OVERVIEW_RESPONSE,
    ADMIN_LEADERBOARD_RESPONSE,
    ADMIN_PARTICIPANTS_LIST_RESPONSE,
    ADMIN_PAYMENTS_FILTER_PARAMS,
    ADMIN_PAYMENTS_LIST_RESPONSE,
    ADMIN_RECONCILIATION_BATCH_DETAIL_RESPONSE,
    ADMIN_RECONCILIATION_BATCH_LIST_RESPONSE,
    ADMIN_RECONCILIATION_ITEM_LIST_RESPONSE,
    ADMIN_REFUND_DETAIL_RESPONSE,
    ADMIN_REFUNDS_LIST_RESPONSE,
    ADMIN_RISK_SIGNAL_DETAIL_RESPONSE,
    ADMIN_RISK_SIGNALS_LIST_RESPONSE,
    ADMIN_SPONSOR_DETAIL_RESPONSE,
    ADMIN_SPONSOR_FILTER_PARAMS,
    ADMIN_SPONSOR_LIST_RESPONSE,
    EMPTY_SUCCESS_RESPONSE,
    GENERIC_ERROR_RESPONSE,
    LIST_PAGINATION_PARAMS,
    PARTICIPATION_INITIATED_RESPONSE,
    PAYMENT_VERIFY_RESPONSE,
    PUBLIC_CAMPAIGN_DETAIL_RESPONSE,
    PUBLIC_CAMPAIGN_FILTER_PARAMS,
    PUBLIC_CAMPAIGN_LIST_RESPONSE,
    PUBLIC_CAMPAIGN_TRANSPARENCY_RESPONSE,
    PUBLIC_RECEIPT_VERIFY_RESPONSE,
    PUBLIC_SPONSOR_DETAIL_RESPONSE,
    PUBLIC_SPONSOR_LIST_RESPONSE,
    TAG_MADADKAR_ADMIN_ANALYTICS,
    TAG_MADADKAR_ADMIN_CAMPAIGN,
    TAG_MADADKAR_ADMIN_SPONSOR,
    TAG_MADADKAR_PUBLIC,
    TAG_MADADKAR_USER,
    USER_PARTICIPATION_DETAIL_RESPONSE,
    USER_PARTICIPATION_FILTER_PARAMS,
    USER_PARTICIPATION_LIST_RESPONSE,
    USER_RECEIPT_DETAIL_RESPONSE,
    USER_RECEIPT_LIST_RESPONSE,
    _audit_disbursement_action,
    _build_callback_url,
    _build_receipt_verification_payload,
    _extract_mobile_email,
    _parse_int_query_param,
    _serialize_participation_detail,
    logger,
)


class MadadkarAdminCampaignFinancialControlView(APIView):
    """Campaign-level financial controls summary including refunds and adjustments."""

    permission_classes = [IsMadadkarAdminUser]

    @extend_schema(
        operation_id="madadkar_admin_campaign_financial_control",
        tags=[TAG_MADADKAR_ADMIN_ANALYTICS],
        summary="کنترل مالی حرکت — ادمین",
        responses={
            200: ADMIN_FINANCIAL_CONTROL_RESPONSE,
            403: GENERIC_ERROR_RESPONSE,
            404: GENERIC_ERROR_RESPONSE,
        },
    )
    def get(self, request: Request, campaign_id: int) -> Response:
        campaign = selectors.get_admin_campaign_by_id(campaign_id=campaign_id)
        if campaign is None:
            return ErrorResponse(
                message="حرکتی با این شناسه یافت نشد.", status_code=status.HTTP_404_NOT_FOUND
            )
        summary = selectors.get_campaign_financial_control_summary(campaign=campaign)
        return SuccessResponse(
            data=CampaignFinancialControlSummarySerializer(summary).data,
            message="گزارش کنترل مالی با موفقیت دریافت شد.",
        )


# ============================================================
# Admin — Financial Ops Controls
# ============================================================


class MadadkarAdminFinancialControlSnapshotListView(APIView):
    """List generated Madadkar financial control snapshots."""

    permission_classes = [IsMadadkarAdminUser]

    @extend_schema(
        operation_id="madadkar_admin_financial_control_snapshots_list",
        tags=[TAG_MADADKAR_ADMIN_ANALYTICS],
        summary="لیست snapshotهای کنترل مالی مددکار — ادمین",
        parameters=[
            OpenApiParameter(
                name="severity", type=OpenApiTypes.STR, location=OpenApiParameter.QUERY
            )
        ],
        responses={
            200: ADMIN_FINANCIAL_CONTROL_SNAPSHOT_LIST_RESPONSE,
            403: GENERIC_ERROR_RESPONSE,
        },
    )
    def get(self, request: Request) -> Response:
        queryset = selectors.get_admin_financial_control_snapshots_queryset()
        severity = request.query_params.get("severity")
        if severity:
            queryset = queryset.filter(severity=severity)
        paginator = StandardPagination()
        page = paginator.paginate_queryset(queryset, request, view=self)
        if page is not None:
            serializer = MadadkarFinancialControlSnapshotSerializer(page, many=True)
            return paginator.get_paginated_response(
                serializer.data, message="لیست کنترل‌های مالی با موفقیت دریافت شد."
            )
        serializer = MadadkarFinancialControlSnapshotSerializer(queryset, many=True)
        return SuccessResponse(
            data=serializer.data, message="لیست کنترل‌های مالی با موفقیت دریافت شد."
        )


class MadadkarAdminFinancialControlLatestView(APIView):
    """Return latest generated financial control snapshot."""

    permission_classes = [IsMadadkarAdminUser]

    @extend_schema(
        operation_id="madadkar_admin_financial_control_latest",
        tags=[TAG_MADADKAR_ADMIN_ANALYTICS],
        summary="آخرین snapshot کنترل مالی مددکار — ادمین",
        responses={
            200: ADMIN_FINANCIAL_CONTROL_SNAPSHOT_DETAIL_RESPONSE,
            403: GENERIC_ERROR_RESPONSE,
            404: GENERIC_ERROR_RESPONSE,
        },
    )
    def get(self, request: Request) -> Response:
        snapshot = selectors.get_latest_financial_control_snapshot()
        if snapshot is None:
            return ErrorResponse(
                message="هنوز snapshot کنترل مالی تولید نشده است.",
                status_code=status.HTTP_404_NOT_FOUND,
            )
        return SuccessResponse(
            data=MadadkarFinancialControlSnapshotSerializer(snapshot).data,
            message="آخرین snapshot کنترل مالی با موفقیت دریافت شد.",
        )


class MadadkarAdminFinancialControlGenerateView(APIView):
    """Generate financial control snapshot on demand for admins."""

    permission_classes = [IsMadadkarAdminUser]

    @extend_schema(
        operation_id="madadkar_admin_financial_control_generate",
        tags=[TAG_MADADKAR_ADMIN_ANALYTICS],
        summary="تولید snapshot کنترل مالی مددکار — ادمین",
        request=None,
        responses={
            201: ADMIN_FINANCIAL_CONTROL_SNAPSHOT_DETAIL_RESPONSE,
            403: GENERIC_ERROR_RESPONSE,
        },
    )
    def post(self, request: Request) -> Response:
        snapshot = services.generate_financial_control_snapshot()
        metadata = extract_audit_metadata(request)
        log_action(
            user_id=request.user.pk,
            action=audit_actions.MADADKAR_FINANCIAL_CONTROL_GENERATED,
            resource_type="madadkar_financial_control_snapshot",
            resource_id=str(snapshot.pk),
            extra_data={"severity": snapshot.severity, "summary": snapshot.summary},
            **metadata,
        )
        return CreatedResponse(
            data=MadadkarFinancialControlSnapshotSerializer(snapshot).data,
            message="Snapshot کنترل مالی با موفقیت تولید شد.",
        )

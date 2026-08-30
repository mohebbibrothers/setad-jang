"""گروه دامنه‌ای `views_admin_intel` از views — فاز ۱۱ (تفکیک P3-16).

کلاس‌ها عیناً منتقل شده‌اند؛ مشترکات از views_common؛ نامِ عمومیِ این گروه‌ها را فقط از facade (apps.*.views) یا همین ماژول import کنید.
"""

from __future__ import annotations

import contextlib

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
from apps.audit_logs.services import log_action_async
from apps.core.pagination import StandardPagination
from apps.core.responses import (
    ErrorResponse,
    SuccessResponse,
)

from . import selectors, services
from .permissions import (
    IsMadadkarAdminUser,
)
from .serializers import (
    CampaignIntelligenceSerializer,
    MadadkarIntelligenceOverviewSerializer,
    MadadkarRiskSignalReviewSerializer,
    MadadkarRiskSignalSerializer,
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

# ============================================================
# Admin — Campaign Intelligence
# ============================================================


class MadadkarAdminCampaignIntelligenceView(APIView):
    """Campaign-level decision intelligence for Madadkar admins."""

    permission_classes = [IsMadadkarAdminUser]

    @extend_schema(
        operation_id="madadkar_admin_campaign_intelligence",
        tags=[TAG_MADADKAR_ADMIN_ANALYTICS],
        summary="هوشمندی مالی و عملیاتی حرکت — ادمین",
        parameters=[
            OpenApiParameter(
                name="days",
                type=OpenApiTypes.INT,
                location=OpenApiParameter.QUERY,
                description="بازه تحلیل روزانه؛ پیش‌فرض ۳۰، حداکثر ۳۶۵.",
            ),
        ],
        responses={
            200: ADMIN_CAMPAIGN_INTELLIGENCE_RESPONSE,
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
        days = _parse_int_query_param(
            request=request, name="days", default=30, minimum=1, maximum=365
        )
        intelligence = selectors.get_campaign_intelligence(campaign=campaign, days=days)
        return SuccessResponse(
            data=CampaignIntelligenceSerializer(intelligence).data,
            message="هوشمندی حرکت با موفقیت دریافت شد.",
        )


class MadadkarAdminIntelligenceOverviewView(APIView):
    """Portfolio-level intelligence overview across Madadkar campaigns."""

    permission_classes = [IsMadadkarAdminUser]

    @extend_schema(
        operation_id="madadkar_admin_intelligence_overview",
        tags=[TAG_MADADKAR_ADMIN_ANALYTICS],
        summary="نمای کلی هوشمندی مددکار — ادمین",
        parameters=[
            OpenApiParameter(
                name="days",
                type=OpenApiTypes.INT,
                location=OpenApiParameter.QUERY,
                description="بازه تحلیل روزانه؛ پیش‌فرض ۳۰، حداکثر ۳۶۵.",
            ),
        ],
        responses={200: ADMIN_INTELLIGENCE_OVERVIEW_RESPONSE, 403: GENERIC_ERROR_RESPONSE},
    )
    def get(self, request: Request) -> Response:
        days = _parse_int_query_param(
            request=request, name="days", default=30, minimum=1, maximum=365
        )
        overview = selectors.get_madadkar_intelligence_overview(days=days)
        return SuccessResponse(
            data=MadadkarIntelligenceOverviewSerializer(overview).data,
            message="نمای هوشمندی مددکار با موفقیت دریافت شد.",
        )


# ============================================================
# Admin — Risk Signals
# ============================================================


class MadadkarAdminRiskSignalListView(APIView):
    """List Madadkar financial risk signals for admin review."""

    permission_classes = [IsMadadkarAdminUser]

    @extend_schema(
        operation_id="madadkar_admin_risk_signals_list",
        tags=[TAG_MADADKAR_ADMIN_ANALYTICS],
        summary="لیست سیگنال‌های ریسک مددکار — ادمین",
        parameters=[
            OpenApiParameter(name="status", type=OpenApiTypes.STR, location=OpenApiParameter.QUERY),
            OpenApiParameter(
                name="severity", type=OpenApiTypes.STR, location=OpenApiParameter.QUERY
            ),
            OpenApiParameter(name="user", type=OpenApiTypes.INT, location=OpenApiParameter.QUERY),
            OpenApiParameter(
                name="campaign", type=OpenApiTypes.INT, location=OpenApiParameter.QUERY
            ),
            OpenApiParameter(
                name="ip_address", type=OpenApiTypes.STR, location=OpenApiParameter.QUERY
            ),
        ],
        responses={200: ADMIN_RISK_SIGNALS_LIST_RESPONSE, 403: GENERIC_ERROR_RESPONSE},
    )
    def get(self, request: Request) -> Response:
        queryset = selectors.get_admin_risk_signals_queryset()
        for field in ("status", "severity", "ip_address"):
            value = request.query_params.get(field)
            if value:
                queryset = queryset.filter(**{field: value})
        for field in ("user", "campaign"):
            value = request.query_params.get(field)
            if value:
                with contextlib.suppress(TypeError, ValueError):
                    queryset = queryset.filter(**{f"{field}_id": int(value)})
        paginator = StandardPagination()
        page = paginator.paginate_queryset(queryset, request, view=self)
        if page is not None:
            serializer = MadadkarRiskSignalSerializer(page, many=True)
            return paginator.get_paginated_response(
                serializer.data, message="لیست سیگنال‌های ریسک با موفقیت دریافت شد."
            )
        serializer = MadadkarRiskSignalSerializer(queryset, many=True)
        return SuccessResponse(
            data=serializer.data, message="لیست سیگنال‌های ریسک با موفقیت دریافت شد."
        )


class MadadkarAdminRiskSignalReviewView(APIView):
    """Review, dismiss, or escalate Madadkar financial risk signals."""

    permission_classes = [IsMadadkarAdminUser]

    @extend_schema(
        operation_id="madadkar_admin_risk_signal_review",
        tags=[TAG_MADADKAR_ADMIN_ANALYTICS],
        summary="بررسی سیگنال ریسک مددکار — ادمین",
        request=MadadkarRiskSignalReviewSerializer,
        responses={
            200: ADMIN_RISK_SIGNAL_DETAIL_RESPONSE,
            400: GENERIC_ERROR_RESPONSE,
            403: GENERIC_ERROR_RESPONSE,
            404: GENERIC_ERROR_RESPONSE,
        },
    )
    def post(self, request: Request, signal_id: int) -> Response:
        signal = selectors.get_admin_risk_signal_by_id(signal_id=signal_id)
        if signal is None:
            return ErrorResponse(
                message="سیگنال ریسکی با این شناسه یافت نشد.", status_code=status.HTTP_404_NOT_FOUND
            )
        serializer = MadadkarRiskSignalReviewSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            reviewed = services.review_madadkar_risk_signal(
                signal=signal,
                reviewed_by=request.user,
                status=serializer.validated_data["status"],
                review_note=serializer.validated_data.get("review_note", ""),
            )
        except services.MadadkarServiceError as exc:
            return ErrorResponse(message=str(exc))
        metadata = extract_audit_metadata(request)
        log_action_async(
            user_id=request.user.pk,
            action=audit_actions.MADADKAR_RISK_SIGNAL_REVIEWED,
            resource_type="madadkar_risk_signal",
            resource_id=str(reviewed.pk),
            extra_data={
                "status": reviewed.status,
                "signal_type": reviewed.signal_type,
                "severity": reviewed.severity,
            },
            **metadata,
        )
        return SuccessResponse(
            data=MadadkarRiskSignalSerializer(reviewed).data,
            message="سیگنال ریسک با موفقیت بررسی شد.",
        )

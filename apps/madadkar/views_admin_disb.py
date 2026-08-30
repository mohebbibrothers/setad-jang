"""گروه دامنه‌ای `views_admin_disb` از views — فاز ۱۱ (تفکیک P3-16).

کلاس‌ها عیناً منتقل شده‌اند؛ مشترکات از views_common؛ نامِ عمومیِ این گروه‌ها را فقط از facade (apps.*.views) یا همین ماژول import کنید.
"""

from __future__ import annotations

import contextlib

from drf_spectacular.utils import (
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
    CreatedResponse,
    ErrorResponse,
    SuccessResponse,
)

from . import selectors, services
from .permissions import (
    IsMadadkarAdminUser,
)
from .serializers import (
    CampaignDisbursementCreateSerializer,
    CampaignDisbursementMarkPaidSerializer,
    CampaignDisbursementRejectSerializer,
    CampaignDisbursementSerializer,
)
from .services import (
    DisbursementWorkflowError,
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
# Admin — Disbursement / Allocation Ledger
# ============================================================


class MadadkarAdminDisbursementListCreateView(APIView):
    """List and request campaign fund disbursements — admin."""

    permission_classes = [IsMadadkarAdminUser]

    @extend_schema(
        operation_id="madadkar_admin_disbursements_list",
        tags=[TAG_MADADKAR_ADMIN_ANALYTICS],
        summary="لیست تخصیص‌های مالی مددکار — ادمین",
        responses={200: ADMIN_DISBURSEMENT_LIST_RESPONSE, 403: GENERIC_ERROR_RESPONSE},
    )
    def get(self, request: Request) -> Response:
        queryset = selectors.get_admin_disbursements_queryset()
        status_filter = request.query_params.get("status")
        if status_filter:
            queryset = queryset.filter(status=status_filter)
        campaign_filter = request.query_params.get("campaign")
        if campaign_filter:
            with contextlib.suppress(TypeError, ValueError):
                queryset = queryset.filter(campaign_id=int(campaign_filter))
        paginator = StandardPagination()
        page = paginator.paginate_queryset(queryset, request, view=self)
        if page is not None:
            serializer = CampaignDisbursementSerializer(page, many=True)
            return paginator.get_paginated_response(
                serializer.data, message="لیست تخصیص‌های مالی با موفقیت دریافت شد."
            )
        serializer = CampaignDisbursementSerializer(queryset, many=True)
        return SuccessResponse(
            data=serializer.data, message="لیست تخصیص‌های مالی با موفقیت دریافت شد."
        )

    @extend_schema(
        operation_id="madadkar_admin_disbursements_create",
        tags=[TAG_MADADKAR_ADMIN_ANALYTICS],
        summary="درخواست تخصیص مالی از حرکت — ادمین",
        request=CampaignDisbursementCreateSerializer,
        responses={
            201: ADMIN_DISBURSEMENT_DETAIL_RESPONSE,
            400: GENERIC_ERROR_RESPONSE,
            403: GENERIC_ERROR_RESPONSE,
            404: GENERIC_ERROR_RESPONSE,
        },
    )
    def post(self, request: Request) -> Response:
        serializer = CampaignDisbursementCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        campaign = selectors.get_admin_campaign_by_id(
            campaign_id=serializer.validated_data["campaign_id"]
        )
        if campaign is None:
            return ErrorResponse(
                message="حرکتی با این شناسه یافت نشد.", status_code=status.HTTP_404_NOT_FOUND
            )
        try:
            disbursement = services.request_campaign_disbursement(
                campaign=campaign,
                requested_by=request.user,
                amount=serializer.validated_data["amount"],
                recipient_name=serializer.validated_data["recipient_name"],
                recipient_identifier=serializer.validated_data.get("recipient_identifier", ""),
                recipient_bank_account=serializer.validated_data.get("recipient_bank_account", ""),
                purpose=serializer.validated_data["purpose"],
                note=serializer.validated_data.get("note", ""),
                supporting_document=serializer.validated_data.get("supporting_document") or {},
            )
        except DisbursementWorkflowError as exc:
            return ErrorResponse(message=str(exc))
        metadata = extract_audit_metadata(request)
        log_action_async(
            user_id=request.user.pk,
            action=audit_actions.MADADKAR_DISBURSEMENT_REQUESTED,
            resource_type="madadkar_disbursement",
            resource_id=str(disbursement.pk),
            extra_data={"campaign_id": campaign.pk, "amount": disbursement.amount},
            **metadata,
        )
        return CreatedResponse(
            data=CampaignDisbursementSerializer(disbursement).data,
            message="درخواست تخصیص مالی ثبت شد.",
        )


class MadadkarAdminDisbursementDetailView(APIView):
    """Retrieve one campaign fund disbursement workflow row — admin."""

    permission_classes = [IsMadadkarAdminUser]

    @extend_schema(
        operation_id="madadkar_admin_disbursement_retrieve",
        tags=[TAG_MADADKAR_ADMIN_ANALYTICS],
        summary="جزئیات تخصیص مالی — ادمین",
        responses={
            200: ADMIN_DISBURSEMENT_DETAIL_RESPONSE,
            403: GENERIC_ERROR_RESPONSE,
            404: GENERIC_ERROR_RESPONSE,
        },
    )
    def get(self, request: Request, disbursement_id: int) -> Response:
        disbursement = selectors.get_admin_disbursement_by_id(disbursement_id=disbursement_id)
        if disbursement is None:
            return ErrorResponse(
                message="تخصیص مالی با این شناسه یافت نشد.", status_code=status.HTTP_404_NOT_FOUND
            )
        return SuccessResponse(
            data=CampaignDisbursementSerializer(disbursement).data,
            message="جزئیات تخصیص مالی با موفقیت دریافت شد.",
        )


class MadadkarAdminDisbursementActionView(APIView):
    """Approve, reject, or mark disbursements as paid — admin."""

    permission_classes = [IsMadadkarAdminUser]

    @extend_schema(
        operation_id="madadkar_admin_disbursement_action",
        tags=[TAG_MADADKAR_ADMIN_ANALYTICS],
        summary="عملیات تخصیص مالی — ادمین",
        request=CampaignDisbursementMarkPaidSerializer,
        responses={
            200: ADMIN_DISBURSEMENT_DETAIL_RESPONSE,
            400: GENERIC_ERROR_RESPONSE,
            403: GENERIC_ERROR_RESPONSE,
            404: GENERIC_ERROR_RESPONSE,
        },
    )
    def post(self, request: Request, disbursement_id: int, action: str) -> Response:
        disbursement = selectors.get_admin_disbursement_by_id(disbursement_id=disbursement_id)
        if disbursement is None:
            return ErrorResponse(
                message="تخصیص مالی با این شناسه یافت نشد.", status_code=status.HTTP_404_NOT_FOUND
            )
        if action == "approve":
            return self._approve(request=request, disbursement=disbursement)
        if action == "reject":
            return self._reject(request=request, disbursement=disbursement)
        if action == "mark-paid":
            return self._mark_paid(request=request, disbursement=disbursement)
        return ErrorResponse(
            message="عملیات تخصیص مالی نامعتبر است.", status_code=status.HTTP_404_NOT_FOUND
        )

    def _approve(self, *, request: Request, disbursement) -> Response:
        """Approve requested disbursement and audit the action."""
        try:
            updated = services.approve_campaign_disbursement(
                disbursement=disbursement, reviewed_by=request.user
            )
        except DisbursementWorkflowError as exc:
            return ErrorResponse(message=str(exc))
        _audit_disbursement_action(
            request=request,
            disbursement=updated,
            action=audit_actions.MADADKAR_DISBURSEMENT_APPROVED,
        )
        return SuccessResponse(
            data=CampaignDisbursementSerializer(updated).data, message="تخصیص مالی تأیید شد."
        )

    def _reject(self, *, request: Request, disbursement) -> Response:
        """Reject requested disbursement and audit the action."""
        serializer = CampaignDisbursementRejectSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            updated = services.reject_campaign_disbursement(
                disbursement=disbursement,
                reviewed_by=request.user,
                rejection_reason=serializer.validated_data["rejection_reason"],
            )
        except DisbursementWorkflowError as exc:
            return ErrorResponse(message=str(exc))
        _audit_disbursement_action(
            request=request,
            disbursement=updated,
            action=audit_actions.MADADKAR_DISBURSEMENT_REJECTED,
        )
        return SuccessResponse(
            data=CampaignDisbursementSerializer(updated).data, message="تخصیص مالی رد شد."
        )

    def _mark_paid(self, *, request: Request, disbursement) -> Response:
        """Mark approved disbursement as paid and audit the action."""
        serializer = CampaignDisbursementMarkPaidSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            updated = services.mark_campaign_disbursement_paid(
                disbursement=disbursement,
                paid_by=request.user,
                bank_tracking_reference=serializer.validated_data["bank_tracking_reference"],
            )
        except DisbursementWorkflowError as exc:
            return ErrorResponse(message=str(exc))
        _audit_disbursement_action(
            request=request, disbursement=updated, action=audit_actions.MADADKAR_DISBURSEMENT_PAID
        )
        return SuccessResponse(
            data=CampaignDisbursementSerializer(updated).data, message="پرداخت تخصیص مالی ثبت شد."
        )

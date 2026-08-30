"""گروه دامنه‌ای `views_admin_recon` از views — فاز ۱۱ (تفکیک P3-16).

کلاس‌ها عیناً منتقل شده‌اند؛ مشترکات از views_common؛ نامِ عمومیِ این گروه‌ها را فقط از facade (apps.*.views) یا همین ماژول import کنید.
"""

from __future__ import annotations

from django.http import HttpResponse
from drf_spectacular.utils import (
    extend_schema,
)
from rest_framework import status
from rest_framework.parsers import FormParser, MultiPartParser
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
from .reconciliation import (
    ReconciliationImportError,
    build_reconciliation_discrepancy_csv,
    parse_settlement_report,
)
from .serializers import (
    PaymentReconciliationBatchSerializer,
    PaymentReconciliationImportSerializer,
    PaymentReconciliationItemSerializer,
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
# Admin — Reconciliation Import / Review / Export
# ============================================================


class MadadkarAdminReconciliationImportView(APIView):
    """Import provider settlement CSV/XLSX and create reconciliation batch."""

    permission_classes = [IsMadadkarAdminUser]
    parser_classes = [MultiPartParser, FormParser]

    @extend_schema(
        operation_id="madadkar_admin_reconciliation_import",
        tags=[TAG_MADADKAR_ADMIN_ANALYTICS],
        summary="Import گزارش تطبیق پرداخت — ادمین",
        request=PaymentReconciliationImportSerializer,
        responses={
            201: ADMIN_RECONCILIATION_BATCH_DETAIL_RESPONSE,
            400: GENERIC_ERROR_RESPONSE,
            403: GENERIC_ERROR_RESPONSE,
        },
    )
    def post(self, request: Request) -> Response:
        serializer = PaymentReconciliationImportSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        uploaded_file = serializer.validated_data["file"]
        try:
            rows = parse_settlement_report(
                filename=uploaded_file.name, content=uploaded_file.read()
            )
            batch = services.reconcile_provider_payments(
                provider_name=serializer.validated_data["provider_name"],
                rows=rows,
                source_name=serializer.validated_data.get("source_name") or uploaded_file.name,
            )
        except ReconciliationImportError as exc:
            return ErrorResponse(message=str(exc))
        metadata = extract_audit_metadata(request)
        log_action(
            user_id=request.user.pk,
            action=audit_actions.MADADKAR_RECONCILIATION_IMPORTED,
            resource_type="madadkar_reconciliation_batch",
            resource_id=str(batch.pk),
            extra_data={
                "provider_name": batch.provider_name,
                "source_name": batch.source_name,
                "total_rows": batch.total_rows,
                "mismatch_count": batch.mismatch_count,
            },
            **metadata,
        )
        return CreatedResponse(
            data=PaymentReconciliationBatchSerializer(batch).data,
            message="گزارش تطبیق پرداخت با موفقیت import شد.",
        )


class MadadkarAdminReconciliationBatchListView(APIView):
    """List reconciliation batches for finance/admin review."""

    permission_classes = [IsMadadkarAdminUser]

    @extend_schema(
        operation_id="madadkar_admin_reconciliation_batches_list",
        tags=[TAG_MADADKAR_ADMIN_ANALYTICS],
        summary="لیست batchهای تطبیق پرداخت — ادمین",
        responses={200: ADMIN_RECONCILIATION_BATCH_LIST_RESPONSE, 403: GENERIC_ERROR_RESPONSE},
    )
    def get(self, request: Request) -> Response:
        queryset = selectors.get_admin_reconciliation_batches_queryset()
        provider = request.query_params.get("provider_name")
        if provider:
            queryset = queryset.filter(provider_name=provider.strip().lower())
        status_filter = request.query_params.get("status")
        if status_filter:
            queryset = queryset.filter(status=status_filter)
        paginator = StandardPagination()
        page = paginator.paginate_queryset(queryset, request, view=self)
        if page is not None:
            serializer = PaymentReconciliationBatchSerializer(page, many=True)
            return paginator.get_paginated_response(
                serializer.data, message="لیست batchهای تطبیق با موفقیت دریافت شد."
            )
        serializer = PaymentReconciliationBatchSerializer(queryset, many=True)
        return SuccessResponse(
            data=serializer.data, message="لیست batchهای تطبیق با موفقیت دریافت شد."
        )


class MadadkarAdminReconciliationBatchDetailView(APIView):
    """Retrieve one reconciliation batch summary."""

    permission_classes = [IsMadadkarAdminUser]

    @extend_schema(
        operation_id="madadkar_admin_reconciliation_batch_retrieve",
        tags=[TAG_MADADKAR_ADMIN_ANALYTICS],
        summary="جزئیات batch تطبیق پرداخت — ادمین",
        responses={
            200: ADMIN_RECONCILIATION_BATCH_DETAIL_RESPONSE,
            403: GENERIC_ERROR_RESPONSE,
            404: GENERIC_ERROR_RESPONSE,
        },
    )
    def get(self, request: Request, batch_id: int) -> Response:
        batch = selectors.get_admin_reconciliation_batch_by_id(batch_id=batch_id)
        if batch is None:
            return ErrorResponse(
                message="Batch تطبیق با این شناسه یافت نشد.", status_code=status.HTTP_404_NOT_FOUND
            )
        return SuccessResponse(
            data=PaymentReconciliationBatchSerializer(batch).data,
            message="جزئیات batch تطبیق با موفقیت دریافت شد.",
        )


class MadadkarAdminReconciliationItemListView(APIView):
    """List reconciliation items for one batch with optional status filter."""

    permission_classes = [IsMadadkarAdminUser]

    @extend_schema(
        operation_id="madadkar_admin_reconciliation_items_list",
        tags=[TAG_MADADKAR_ADMIN_ANALYTICS],
        summary="لیست ردیف‌های batch تطبیق پرداخت — ادمین",
        responses={
            200: ADMIN_RECONCILIATION_ITEM_LIST_RESPONSE,
            403: GENERIC_ERROR_RESPONSE,
            404: GENERIC_ERROR_RESPONSE,
        },
    )
    def get(self, request: Request, batch_id: int) -> Response:
        batch = selectors.get_admin_reconciliation_batch_by_id(batch_id=batch_id)
        if batch is None:
            return ErrorResponse(
                message="Batch تطبیق با این شناسه یافت نشد.", status_code=status.HTTP_404_NOT_FOUND
            )
        queryset = selectors.get_admin_reconciliation_items_queryset(batch=batch)
        status_filter = request.query_params.get("status")
        if status_filter:
            queryset = queryset.filter(status=status_filter)
        paginator = StandardPagination()
        page = paginator.paginate_queryset(queryset, request, view=self)
        if page is not None:
            serializer = PaymentReconciliationItemSerializer(page, many=True)
            return paginator.get_paginated_response(
                serializer.data, message="لیست ردیف‌های تطبیق با موفقیت دریافت شد."
            )
        serializer = PaymentReconciliationItemSerializer(queryset, many=True)
        return SuccessResponse(
            data=serializer.data, message="لیست ردیف‌های تطبیق با موفقیت دریافت شد."
        )


class MadadkarAdminReconciliationDiscrepancyExportView(APIView):
    """Export non-matched reconciliation rows as finance-friendly CSV."""

    permission_classes = [IsMadadkarAdminUser]

    @extend_schema(
        operation_id="madadkar_admin_reconciliation_discrepancies_export",
        tags=[TAG_MADADKAR_ADMIN_ANALYTICS],
        summary="خروجی CSV اختلافات تطبیق — ادمین",
        responses={
            200: {"type": "string", "format": "binary"},
            403: GENERIC_ERROR_RESPONSE,
            404: GENERIC_ERROR_RESPONSE,
        },
    )
    def get(self, request: Request, batch_id: int) -> HttpResponse | ErrorResponse:
        batch = selectors.get_admin_reconciliation_batch_by_id(batch_id=batch_id)
        if batch is None:
            return ErrorResponse(
                message="Batch تطبیق با این شناسه یافت نشد.", status_code=status.HTTP_404_NOT_FOUND
            )
        content = build_reconciliation_discrepancy_csv(batch=batch)
        metadata = extract_audit_metadata(request)
        log_action(
            user_id=request.user.pk,
            action=audit_actions.MADADKAR_RECONCILIATION_EXPORTED,
            resource_type="madadkar_reconciliation_batch",
            resource_id=str(batch.pk),
            extra_data={
                "provider_name": batch.provider_name,
                "mismatch_count": batch.mismatch_count,
            },
            **metadata,
        )
        filename = f"madadkar-reconciliation-discrepancies-{batch.pk}.csv"
        response = HttpResponse(content, content_type="text/csv; charset=utf-8")
        response["Content-Disposition"] = f'attachment; filename="{filename}"'
        response["Content-Length"] = str(len(content))
        return response

"""گروه دامنه‌ای `views_admin_finance` از views — فاز ۱۱ (تفکیک P3-16).

کلاس‌ها عیناً منتقل شده‌اند؛ مشترکات از views_common؛ نامِ عمومیِ این گروه‌ها را فقط از facade (apps.*.views) یا همین ماژول import کنید.
"""

from __future__ import annotations

import contextlib

from drf_spectacular.utils import (
    extend_schema,
    extend_schema_view,
)
from rest_framework import status
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.audit_logs import actions as audit_actions
from apps.audit_logs.helpers import extract_audit_metadata
from apps.audit_logs.services import log_action, log_action_async
from apps.core.pagination import StandardPagination
from apps.core.responses import (
    CreatedResponse,
    DeletedResponse,
    ErrorResponse,
    SuccessResponse,
)

from . import selectors, services
from .filters import (
    SponsorAdminFilter,
)
from .permissions import (
    IsMadadkarAdminUser,
)
from .serializers import (
    DonationReceiptResendSerializer,
    DonationReceiptSerializer,
    FinancialAdjustmentCreateSerializer,
    FinancialAdjustmentRejectSerializer,
    FinancialAdjustmentSerializer,
    PaymentRefundCompleteSerializer,
    PaymentRefundRejectSerializer,
    PaymentRefundRequestSerializer,
    PaymentRefundSerializer,
    SponsorAdminSerializer,
    SponsorCreateSerializer,
    SponsorUpdateSerializer,
)
from .services import (
    FinancialAdjustmentWorkflowError,
    RefundWorkflowError,
    SponsorInUseError,
    SponsorInvalidDataError,
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


class MadadkarAdminReceiptResendView(APIView):
    """Record audited resend action for a donation receipt."""

    permission_classes = [IsMadadkarAdminUser]

    @extend_schema(
        operation_id="madadkar_admin_receipt_resend",
        tags=[TAG_MADADKAR_ADMIN_ANALYTICS],
        summary="ثبت ارسال مجدد رسید — ادمین",
        request=DonationReceiptResendSerializer,
        responses={
            200: USER_RECEIPT_DETAIL_RESPONSE,
            400: GENERIC_ERROR_RESPONSE,
            403: GENERIC_ERROR_RESPONSE,
            404: GENERIC_ERROR_RESPONSE,
        },
    )
    def post(self, request: Request, receipt_id: int) -> Response:
        receipt = selectors.get_admin_receipt_by_id(receipt_id=receipt_id)
        if receipt is None:
            return ErrorResponse(
                message="رسیدی با این شناسه یافت نشد.", status_code=status.HTTP_404_NOT_FOUND
            )
        serializer = DonationReceiptResendSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        receipt = services.record_receipt_resend(receipt=receipt)
        metadata = extract_audit_metadata(request)
        log_action_async(
            user_id=request.user.pk,
            action=audit_actions.MADADKAR_RECEIPT_RESENT,
            resource_type="madadkar_receipt",
            resource_id=str(receipt.pk),
            extra_data={
                "receipt_number": receipt.receipt_number,
                "delivery_channel": serializer.validated_data["delivery_channel"],
            },
            **metadata,
        )
        return SuccessResponse(
            data=DonationReceiptSerializer(receipt).data,
            message="ارسال مجدد رسید با موفقیت ثبت شد.",
        )


# ============================================================
# Admin — Sponsors CRUD
# ============================================================


@extend_schema_view(
    get=extend_schema(
        operation_id="madadkar_admin_sponsors_list",
        tags=[TAG_MADADKAR_ADMIN_SPONSOR],
        summary="لیست مددکاران — ادمین",
        parameters=ADMIN_SPONSOR_FILTER_PARAMS,
        responses={200: ADMIN_SPONSOR_LIST_RESPONSE, 403: GENERIC_ERROR_RESPONSE},
    ),
    post=extend_schema(
        operation_id="madadkar_admin_sponsors_create",
        tags=[TAG_MADADKAR_ADMIN_SPONSOR],
        summary="ساخت مددکار جدید — ادمین",
        request=SponsorCreateSerializer,
        responses={
            201: ADMIN_SPONSOR_DETAIL_RESPONSE,
            400: GENERIC_ERROR_RESPONSE,
            403: GENERIC_ERROR_RESPONSE,
        },
    ),
)
class MadadkarAdminSponsorListCreateView(APIView):
    """list + create sponsors — admin."""

    permission_classes = [IsMadadkarAdminUser]
    parser_classes = [MultiPartParser, FormParser, JSONParser]

    def get(self, request: Request) -> Response:
        queryset = selectors.get_admin_sponsors_queryset()
        filterset = SponsorAdminFilter(request.query_params, queryset=queryset)
        if filterset.is_valid():
            queryset = filterset.qs

        paginator = StandardPagination()
        page = paginator.paginate_queryset(queryset, request, view=self)

        if page is not None:
            serializer = SponsorAdminSerializer(page, many=True)
            return paginator.get_paginated_response(
                serializer.data,
                message="لیست مددکاران با موفقیت دریافت شد.",
            )

        serializer = SponsorAdminSerializer(queryset, many=True)
        return SuccessResponse(
            data=serializer.data,
            message="لیست مددکاران با موفقیت دریافت شد.",
        )

    def post(self, request: Request) -> Response:
        serializer = SponsorCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        try:
            sponsor = services.create_sponsor(**serializer.validated_data)
        except SponsorInvalidDataError as exc:
            return ErrorResponse(message=str(exc))

        metadata = extract_audit_metadata(request)
        log_action_async(
            user_id=request.user.pk,
            action=audit_actions.MADADKAR_SPONSOR_CREATED,
            resource_type="madadkar_sponsor",
            resource_id=str(sponsor.pk),
            extra_data={"name": sponsor.name},
            **metadata,
        )

        return CreatedResponse(
            data=SponsorAdminSerializer(sponsor).data,
            message="مددکار با موفقیت ساخته شد.",
        )


@extend_schema_view(
    get=extend_schema(
        operation_id="madadkar_admin_sponsor_retrieve",
        tags=[TAG_MADADKAR_ADMIN_SPONSOR],
        summary="جزئیات مددکار — ادمین",
        responses={
            200: ADMIN_SPONSOR_DETAIL_RESPONSE,
            403: GENERIC_ERROR_RESPONSE,
            404: GENERIC_ERROR_RESPONSE,
        },
    ),
    patch=extend_schema(
        operation_id="madadkar_admin_sponsor_update",
        tags=[TAG_MADADKAR_ADMIN_SPONSOR],
        summary="ویرایش مددکار — ادمین",
        request=SponsorUpdateSerializer,
        responses={
            200: ADMIN_SPONSOR_DETAIL_RESPONSE,
            400: GENERIC_ERROR_RESPONSE,
            403: GENERIC_ERROR_RESPONSE,
            404: GENERIC_ERROR_RESPONSE,
        },
    ),
    delete=extend_schema(
        operation_id="madadkar_admin_sponsor_delete",
        tags=[TAG_MADADKAR_ADMIN_SPONSOR],
        summary="حذف نرم مددکار — ادمین",
        responses={
            200: EMPTY_SUCCESS_RESPONSE,
            400: GENERIC_ERROR_RESPONSE,
            403: GENERIC_ERROR_RESPONSE,
            404: GENERIC_ERROR_RESPONSE,
        },
    ),
)
class MadadkarAdminSponsorDetailView(APIView):
    """retrieve + update + delete sponsor — admin."""

    permission_classes = [IsMadadkarAdminUser]
    parser_classes = [MultiPartParser, FormParser, JSONParser]

    def get(self, request: Request, sponsor_id: int) -> Response:
        sponsor = selectors.get_sponsor_by_id_admin(sponsor_id=sponsor_id)
        if sponsor is None:
            return ErrorResponse(
                message="مددکاری با این شناسه یافت نشد.",
                status_code=status.HTTP_404_NOT_FOUND,
            )
        return SuccessResponse(
            data=SponsorAdminSerializer(sponsor).data,
            message="جزئیات مددکار با موفقیت دریافت شد.",
        )

    def patch(self, request: Request, sponsor_id: int) -> Response:
        sponsor = selectors.get_sponsor_by_id_admin(sponsor_id=sponsor_id)
        if sponsor is None:
            return ErrorResponse(
                message="مددکاری با این شناسه یافت نشد.",
                status_code=status.HTTP_404_NOT_FOUND,
            )

        serializer = SponsorUpdateSerializer(data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)

        try:
            sponsor = services.update_sponsor(
                sponsor=sponsor,
                **serializer.validated_data,
            )
        except SponsorInvalidDataError as exc:
            return ErrorResponse(message=str(exc))

        metadata = extract_audit_metadata(request)
        log_action_async(
            user_id=request.user.pk,
            action=audit_actions.MADADKAR_SPONSOR_UPDATED,
            resource_type="madadkar_sponsor",
            resource_id=str(sponsor.pk),
            changes=dict(serializer.validated_data),
            **metadata,
        )

        return SuccessResponse(
            data=SponsorAdminSerializer(sponsor).data,
            message="مددکار با موفقیت بروزرسانی شد.",
        )

    def delete(self, request: Request, sponsor_id: int) -> Response:
        sponsor = selectors.get_sponsor_by_id_admin(sponsor_id=sponsor_id)
        if sponsor is None:
            return ErrorResponse(
                message="مددکاری با این شناسه یافت نشد.",
                status_code=status.HTTP_404_NOT_FOUND,
            )

        try:
            services.delete_sponsor(sponsor=sponsor)
        except SponsorInUseError as exc:
            return ErrorResponse(message=str(exc))

        metadata = extract_audit_metadata(request)
        log_action(
            user_id=request.user.pk,
            action=audit_actions.MADADKAR_SPONSOR_DELETED,
            resource_type="madadkar_sponsor",
            resource_id=str(sponsor_id),
            extra_data={"name": sponsor.name},
            **metadata,
        )

        return DeletedResponse(message="مددکار با موفقیت حذف شد.")


# ============================================================
# Admin — Refunds / Financial Adjustments
# ============================================================


class MadadkarAdminRefundListCreateView(APIView):
    """List and create reviewed payment refund requests — admin."""

    permission_classes = [IsMadadkarAdminUser]

    @extend_schema(
        operation_id="madadkar_admin_refunds_list",
        tags=[TAG_MADADKAR_ADMIN_ANALYTICS],
        summary="لیست بازپرداخت‌ها — ادمین",
        responses={200: ADMIN_REFUNDS_LIST_RESPONSE, 403: GENERIC_ERROR_RESPONSE},
    )
    def get(self, request: Request) -> Response:
        queryset = selectors.get_admin_refunds_queryset()
        status_filter = request.query_params.get("status")
        if status_filter:
            queryset = queryset.filter(status=status_filter)
        payment_filter = request.query_params.get("payment")
        if payment_filter:
            with contextlib.suppress(TypeError, ValueError):
                queryset = queryset.filter(payment_id=int(payment_filter))
        paginator = StandardPagination()
        page = paginator.paginate_queryset(queryset, request, view=self)
        if page is not None:
            serializer = PaymentRefundSerializer(page, many=True)
            return paginator.get_paginated_response(
                serializer.data, message="لیست بازپرداخت‌ها با موفقیت دریافت شد."
            )
        serializer = PaymentRefundSerializer(queryset, many=True)
        return SuccessResponse(
            data=serializer.data, message="لیست بازپرداخت‌ها با موفقیت دریافت شد."
        )

    @extend_schema(
        operation_id="madadkar_admin_refunds_create",
        tags=[TAG_MADADKAR_ADMIN_ANALYTICS],
        summary="ثبت درخواست بازپرداخت — ادمین",
        request=PaymentRefundRequestSerializer,
        responses={
            201: ADMIN_REFUND_DETAIL_RESPONSE,
            400: GENERIC_ERROR_RESPONSE,
            403: GENERIC_ERROR_RESPONSE,
            404: GENERIC_ERROR_RESPONSE,
        },
    )
    def post(self, request: Request) -> Response:
        serializer = PaymentRefundRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        payment = selectors.get_admin_payment_by_id(
            payment_id=serializer.validated_data["payment_id"]
        )
        if payment is None:
            return ErrorResponse(
                message="پرداختی با این شناسه یافت نشد.", status_code=status.HTTP_404_NOT_FOUND
            )
        try:
            refund = services.request_payment_refund(
                payment=payment,
                amount=serializer.validated_data["amount"],
                reason=serializer.validated_data["reason"],
                requested_by=request.user,
                note=serializer.validated_data.get("note", ""),
                idempotency_key=serializer.validated_data.get("idempotency_key") or None,
            )
        except RefundWorkflowError as exc:
            return ErrorResponse(message=str(exc))
        metadata = extract_audit_metadata(request)
        log_action_async(
            user_id=request.user.pk,
            action=audit_actions.MADADKAR_REFUND_REQUESTED,
            resource_type="madadkar_refund",
            resource_id=str(refund.pk),
            extra_data={"payment_id": payment.pk, "amount": refund.amount, "reason": refund.reason},
            **metadata,
        )
        return CreatedResponse(
            data=PaymentRefundSerializer(refund).data, message="درخواست بازپرداخت با موفقیت ثبت شد."
        )


class MadadkarAdminRefundActionView(APIView):
    """Approve, reject, and complete payment refund workflow rows — admin."""

    permission_classes = [IsMadadkarAdminUser]

    @extend_schema(
        operation_id="madadkar_admin_refund_approve",
        tags=[TAG_MADADKAR_ADMIN_ANALYTICS],
        summary="تأیید بازپرداخت — ادمین",
        request=None,
        responses={
            200: ADMIN_REFUND_DETAIL_RESPONSE,
            400: GENERIC_ERROR_RESPONSE,
            403: GENERIC_ERROR_RESPONSE,
            404: GENERIC_ERROR_RESPONSE,
        },
    )
    def post(self, request: Request, refund_id: int, action: str) -> Response:
        refund = selectors.get_admin_refund_by_id(refund_id=refund_id)
        if refund is None:
            return ErrorResponse(
                message="بازپرداختی با این شناسه یافت نشد.", status_code=status.HTTP_404_NOT_FOUND
            )
        if action == "approve":
            return self._approve(request=request, refund=refund)
        if action == "reject":
            return self._reject(request=request, refund=refund)
        if action == "complete":
            return self._complete(request=request, refund=refund)
        return ErrorResponse(
            message="عملیات بازپرداخت نامعتبر است.", status_code=status.HTTP_404_NOT_FOUND
        )

    def _approve(self, *, request: Request, refund) -> Response:
        """Approve refund and record audit evidence."""
        try:
            updated = services.approve_payment_refund(refund=refund, reviewed_by=request.user)
        except RefundWorkflowError as exc:
            return ErrorResponse(message=str(exc))
        metadata = extract_audit_metadata(request)
        log_action_async(
            user_id=request.user.pk,
            action=audit_actions.MADADKAR_REFUND_APPROVED,
            resource_type="madadkar_refund",
            resource_id=str(updated.pk),
            extra_data={"amount": updated.amount, "payment_id": updated.payment_id},
            **metadata,
        )
        return SuccessResponse(
            data=PaymentRefundSerializer(updated).data, message="بازپرداخت با موفقیت تأیید شد."
        )

    def _reject(self, *, request: Request, refund) -> Response:
        """Reject refund and record audit evidence."""
        serializer = PaymentRefundRejectSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            updated = services.reject_payment_refund(
                refund=refund,
                reviewed_by=request.user,
                rejection_reason=serializer.validated_data["rejection_reason"],
            )
        except RefundWorkflowError as exc:
            return ErrorResponse(message=str(exc))
        metadata = extract_audit_metadata(request)
        log_action_async(
            user_id=request.user.pk,
            action=audit_actions.MADADKAR_REFUND_REJECTED,
            resource_type="madadkar_refund",
            resource_id=str(updated.pk),
            extra_data={"reason": updated.rejection_reason, "payment_id": updated.payment_id},
            **metadata,
        )
        return SuccessResponse(
            data=PaymentRefundSerializer(updated).data, message="بازپرداخت رد شد."
        )

    def _complete(self, *, request: Request, refund) -> Response:
        """Complete approved refund and record audit evidence."""
        serializer = PaymentRefundCompleteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            updated = services.complete_payment_refund(
                refund=refund,
                provider_ref_id=serializer.validated_data.get("provider_ref_id", ""),
            )
        except RefundWorkflowError as exc:
            return ErrorResponse(message=str(exc))
        metadata = extract_audit_metadata(request)
        log_action_async(
            user_id=request.user.pk,
            action=audit_actions.MADADKAR_REFUND_COMPLETED,
            resource_type="madadkar_refund",
            resource_id=str(updated.pk),
            extra_data={
                "amount": updated.amount,
                "payment_id": updated.payment_id,
                "provider_ref_id": updated.provider_ref_id,
            },
            **metadata,
        )
        return SuccessResponse(
            data=PaymentRefundSerializer(updated).data, message="بازپرداخت با موفقیت تکمیل شد."
        )


class MadadkarAdminAdjustmentListCreateView(APIView):
    """List and create financial adjustment workflow rows — admin."""

    permission_classes = [IsMadadkarAdminUser]

    @extend_schema(
        operation_id="madadkar_admin_adjustments_list",
        tags=[TAG_MADADKAR_ADMIN_ANALYTICS],
        summary="لیست اصلاحات مالی — ادمین",
        responses={200: ADMIN_ADJUSTMENTS_LIST_RESPONSE, 403: GENERIC_ERROR_RESPONSE},
    )
    def get(self, request: Request) -> Response:
        queryset = selectors.get_admin_adjustments_queryset()
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
            serializer = FinancialAdjustmentSerializer(page, many=True)
            return paginator.get_paginated_response(
                serializer.data, message="لیست اصلاحات مالی با موفقیت دریافت شد."
            )
        serializer = FinancialAdjustmentSerializer(queryset, many=True)
        return SuccessResponse(
            data=serializer.data, message="لیست اصلاحات مالی با موفقیت دریافت شد."
        )

    @extend_schema(
        operation_id="madadkar_admin_adjustments_create",
        tags=[TAG_MADADKAR_ADMIN_ANALYTICS],
        summary="ثبت اصلاح مالی — ادمین",
        request=FinancialAdjustmentCreateSerializer,
        responses={
            201: ADMIN_ADJUSTMENT_DETAIL_RESPONSE,
            400: GENERIC_ERROR_RESPONSE,
            403: GENERIC_ERROR_RESPONSE,
            404: GENERIC_ERROR_RESPONSE,
        },
    )
    def post(self, request: Request) -> Response:
        serializer = FinancialAdjustmentCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        campaign = selectors.get_admin_campaign_by_id(
            campaign_id=serializer.validated_data["campaign_id"]
        )
        if campaign is None:
            return ErrorResponse(
                message="حرکتی با این شناسه یافت نشد.", status_code=status.HTTP_404_NOT_FOUND
            )
        payment = None
        if serializer.validated_data.get("payment_id"):
            payment = selectors.get_admin_payment_by_id(
                payment_id=serializer.validated_data["payment_id"]
            )
            if payment is None:
                return ErrorResponse(
                    message="پرداختی با این شناسه یافت نشد.", status_code=status.HTTP_404_NOT_FOUND
                )
        try:
            adjustment = services.create_financial_adjustment(
                campaign=campaign,
                payment=payment,
                requested_by=request.user,
                amount=serializer.validated_data["amount"],
                adjustment_type=serializer.validated_data["adjustment_type"],
                reason=serializer.validated_data["reason"],
                note=serializer.validated_data.get("note", ""),
            )
        except FinancialAdjustmentWorkflowError as exc:
            return ErrorResponse(message=str(exc))
        metadata = extract_audit_metadata(request)
        log_action_async(
            user_id=request.user.pk,
            action=audit_actions.MADADKAR_ADJUSTMENT_CREATED,
            resource_type="madadkar_financial_adjustment",
            resource_id=str(adjustment.pk),
            extra_data={
                "campaign_id": campaign.pk,
                "amount": adjustment.amount,
                "type": adjustment.adjustment_type,
            },
            **metadata,
        )
        return CreatedResponse(
            data=FinancialAdjustmentSerializer(adjustment).data,
            message="اصلاح مالی با موفقیت ثبت شد.",
        )


class MadadkarAdminAdjustmentActionView(APIView):
    """Approve, reject, and apply financial adjustments — admin."""

    permission_classes = [IsMadadkarAdminUser]

    @extend_schema(
        operation_id="madadkar_admin_adjustment_action",
        tags=[TAG_MADADKAR_ADMIN_ANALYTICS],
        summary="عملیات اصلاح مالی — ادمین",
        request=FinancialAdjustmentRejectSerializer,
        responses={
            200: ADMIN_ADJUSTMENT_DETAIL_RESPONSE,
            400: GENERIC_ERROR_RESPONSE,
            403: GENERIC_ERROR_RESPONSE,
            404: GENERIC_ERROR_RESPONSE,
        },
    )
    def post(self, request: Request, adjustment_id: int, action: str) -> Response:
        adjustment = selectors.get_admin_adjustment_by_id(adjustment_id=adjustment_id)
        if adjustment is None:
            return ErrorResponse(
                message="اصلاح مالی با این شناسه یافت نشد.", status_code=status.HTTP_404_NOT_FOUND
            )
        if action == "approve":
            return self._approve(request=request, adjustment=adjustment)
        if action == "reject":
            return self._reject(request=request, adjustment=adjustment)
        if action == "apply":
            return self._apply(request=request, adjustment=adjustment)
        return ErrorResponse(
            message="عملیات اصلاح مالی نامعتبر است.", status_code=status.HTTP_404_NOT_FOUND
        )

    def _approve(self, *, request: Request, adjustment) -> Response:
        """Approve financial adjustment and audit the sensitive action."""
        try:
            updated = services.approve_financial_adjustment(
                adjustment=adjustment, reviewed_by=request.user
            )
        except FinancialAdjustmentWorkflowError as exc:
            return ErrorResponse(message=str(exc))
        metadata = extract_audit_metadata(request)
        log_action_async(
            user_id=request.user.pk,
            action=audit_actions.MADADKAR_ADJUSTMENT_APPROVED,
            resource_type="madadkar_financial_adjustment",
            resource_id=str(updated.pk),
            extra_data={"amount": updated.amount, "type": updated.adjustment_type},
            **metadata,
        )
        return SuccessResponse(
            data=FinancialAdjustmentSerializer(updated).data, message="اصلاح مالی تأیید شد."
        )

    def _reject(self, *, request: Request, adjustment) -> Response:
        """Reject financial adjustment and audit the sensitive action."""
        serializer = FinancialAdjustmentRejectSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            updated = services.reject_financial_adjustment(
                adjustment=adjustment,
                reviewed_by=request.user,
                rejection_reason=serializer.validated_data["rejection_reason"],
            )
        except FinancialAdjustmentWorkflowError as exc:
            return ErrorResponse(message=str(exc))
        metadata = extract_audit_metadata(request)
        log_action_async(
            user_id=request.user.pk,
            action=audit_actions.MADADKAR_ADJUSTMENT_REJECTED,
            resource_type="madadkar_financial_adjustment",
            resource_id=str(updated.pk),
            extra_data={"reason": updated.rejection_reason},
            **metadata,
        )
        return SuccessResponse(
            data=FinancialAdjustmentSerializer(updated).data, message="اصلاح مالی رد شد."
        )

    def _apply(self, *, request: Request, adjustment) -> Response:
        """Apply financial adjustment and audit the sensitive action."""
        try:
            updated = services.apply_financial_adjustment(adjustment=adjustment)
        except FinancialAdjustmentWorkflowError as exc:
            return ErrorResponse(message=str(exc))
        metadata = extract_audit_metadata(request)
        log_action_async(
            user_id=request.user.pk,
            action=audit_actions.MADADKAR_ADJUSTMENT_APPLIED,
            resource_type="madadkar_financial_adjustment",
            resource_id=str(updated.pk),
            extra_data={
                "campaign_id": updated.campaign_id,
                "amount": updated.amount,
                "type": updated.adjustment_type,
            },
            **metadata,
        )
        return SuccessResponse(
            data=FinancialAdjustmentSerializer(updated).data, message="اصلاح مالی اعمال شد."
        )

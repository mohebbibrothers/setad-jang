"""گروه دامنه‌ای `views_admin_misc` از views — فاز ۱۱ (تفکیک P3-16).

کلاس‌ها عیناً منتقل شده‌اند؛ مشترکات از views_common؛ نامِ عمومیِ این گروه‌ها را فقط از facade (apps.*.views) یا همین ماژول import کنید.
"""

from __future__ import annotations

import contextlib

from drf_spectacular.utils import (
    OpenApiParameter,
    OpenApiTypes,
    extend_schema,
    extend_schema_view,
)
from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.audit_logs import actions as audit_actions
from apps.audit_logs.helpers import extract_audit_metadata
from apps.audit_logs.services import log_action, log_action_async
from apps.core.pagination import StandardPagination
from apps.core.responses import (
    ErrorResponse,
    SuccessResponse,
)

from . import selectors, services
from .choices import PaymentStatus
from .permissions import (
    IsMadadkarAdminUser,
)
from .serializers import (
    AdminPaymentListSerializer,
    PaymentVerifyCallbackSerializer,
)
from .services import (
    PaymentAmountMismatchError,
    PaymentGatewayError,
    PaymentNotFoundError,
)
from .throttles import (
    MadadkarPaymentVerifyThrottle,
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
# User — Payment Verify Callback
# ============================================================


class MadadkarPaymentVerifyView(APIView):
    """
    Callback تأیید پرداخت — GET/POST /api/v1/madadkar/payment/verify/

    نکته مهم: این endpoint از سمت **درگاه پرداخت** فراخوانی می‌شود
    (نه مستقیم از طرف کلاینت ما). در زمان فراخوانی session کاربر
    معمولاً موجود نیست.

    بنابراین:
    - permission: AllowAny (verify بر اساس authority انجام می‌شود)
    - throttle: مخصوص (مبتنی بر IP)
    - method: هم GET (Zarinpal) و هم POST (سایر درگاه‌ها) پشتیبانی می‌شوند.
    """

    permission_classes = [AllowAny]
    throttle_classes = [MadadkarPaymentVerifyThrottle]

    @extend_schema(
        operation_id="madadkar_payment_verify",
        tags=[TAG_MADADKAR_USER],
        summary="تأیید پرداخت — callback از سمت درگاه",
        description=(
            "این endpoint توسط درگاه پرداخت بعد از تکمیل تراکنش فراخوانی می‌شود.\n\n"
            "ورودی شامل `authority` (و گاهی `status`) است که توسط درگاه به‌صورت "
            "query string یا body ارسال می‌گردد.\n\n"
            "این endpoint **idempotent** است: فراخوانی دوباره با همان authority "
            "نتیجه قبلی را برمی‌گرداند بدون تماس مجدد با درگاه."
        ),
        parameters=[
            OpenApiParameter(
                name="authority",
                type=OpenApiTypes.STR,
                location=OpenApiParameter.QUERY,
                required=True,
            ),
            OpenApiParameter(
                name="status",
                type=OpenApiTypes.STR,
                location=OpenApiParameter.QUERY,
                required=False,
            ),
        ],
        responses={
            200: PAYMENT_VERIFY_RESPONSE,
            400: GENERIC_ERROR_RESPONSE,
            404: GENERIC_ERROR_RESPONSE,
            502: GENERIC_ERROR_RESPONSE,
        },
    )
    def get(self, request: Request) -> Response:
        return self._verify(request, source=request.query_params)

    @extend_schema(
        operation_id="madadkar_payment_verify_post",
        tags=[TAG_MADADKAR_USER],
        summary="تأیید پرداخت — POST callback (درگاه‌های POST-based)",
        request=PaymentVerifyCallbackSerializer,
        responses={
            200: PAYMENT_VERIFY_RESPONSE,
            400: GENERIC_ERROR_RESPONSE,
            404: GENERIC_ERROR_RESPONSE,
            502: GENERIC_ERROR_RESPONSE,
        },
    )
    def post(self, request: Request) -> Response:
        return self._verify(request, source=request.data)

    def _verify(self, request: Request, source) -> Response:
        """منطق مشترک verify برای هر دو متد GET و POST."""
        serializer = PaymentVerifyCallbackSerializer(data=source)
        serializer.is_valid(raise_exception=True)
        authority = serializer.validated_data["authority"]

        try:
            payment = services.verify_payment(authority=authority)
        except PaymentNotFoundError as exc:
            return ErrorResponse(
                message=str(exc),
                status_code=status.HTTP_404_NOT_FOUND,
            )
        except PaymentAmountMismatchError as exc:
            metadata = extract_audit_metadata(request)
            log_action(
                user_id=None,
                action=audit_actions.MADADKAR_PAYMENT_FAILED,
                resource_type="madadkar_payment",
                resource_id=authority,
                extra_data={"reason": "amount_mismatch"},
                **metadata,
            )
            return ErrorResponse(message=str(exc))
        except PaymentGatewayError as exc:
            return ErrorResponse(
                message=str(exc),
                status_code=status.HTTP_502_BAD_GATEWAY,
            )

        metadata = extract_audit_metadata(request)
        is_success = payment.status == PaymentStatus.SUCCESS

        log_action_async(
            user_id=payment.user_id,
            action=(
                audit_actions.MADADKAR_PAYMENT_SUCCESS
                if is_success
                else audit_actions.MADADKAR_PAYMENT_FAILED
            ),
            resource_type="madadkar_payment",
            resource_id=str(payment.pk),
            extra_data={
                "authority": authority,
                "amount": payment.amount,
                "participation_id": payment.participation_id,
            },
            **metadata,
        )

        participation_data = _serialize_participation_detail(payment.participation)

        result_payload = {
            "payment_status": payment.status,
            "payment_status_display": payment.get_status_display(),
            "participation": participation_data,
            "is_verified": is_success,
            "message": (
                "پرداخت با موفقیت تأیید شد." if is_success else "پرداخت تأیید نشد یا ناموفق بود."
            ),
        }

        return SuccessResponse(
            data=result_payload,
            message=result_payload["message"],
        )


# ============================================================
# Admin — All Payments
# ============================================================


@extend_schema_view(
    get=extend_schema(
        operation_id="madadkar_admin_payments_list",
        tags=[TAG_MADADKAR_ADMIN_ANALYTICS],
        summary="لیست تمام پرداخت‌ها — ادمین",
        description=(
            "دریافت لیست تمام پرداخت‌ها در کل سامانه با امکان فیلتر.\n\n"
            "Query params:\n"
            "- `status`: فیلتر بر اساس وضعیت (pending/success/failed)\n"
            "- `gateway_name`: فیلتر بر اساس درگاه (sandbox/zarinpal/...)\n"
            "- `campaign`: فیلتر بر اساس شناسه حرکت\n"
            "- `user`: فیلتر بر اساس شناسه کاربر"
        ),
        parameters=ADMIN_PAYMENTS_FILTER_PARAMS,
        responses={
            200: ADMIN_PAYMENTS_LIST_RESPONSE,
            403: GENERIC_ERROR_RESPONSE,
        },
    ),
)
class MadadkarAdminPaymentListView(APIView):
    """لیست تمام پرداخت‌های سامانه — admin."""

    permission_classes = [IsMadadkarAdminUser]

    def get(self, request: Request) -> Response:
        queryset = selectors.get_admin_payments_queryset()

        # Optional filters
        status_filter = request.query_params.get("status")
        if status_filter:
            queryset = queryset.filter(status=status_filter)

        gateway_filter = request.query_params.get("gateway_name")
        if gateway_filter:
            queryset = queryset.filter(gateway_name=gateway_filter)

        campaign_filter = request.query_params.get("campaign")
        if campaign_filter:
            with contextlib.suppress(TypeError, ValueError):
                queryset = queryset.filter(
                    participation__campaign_id=int(campaign_filter),
                )

        user_filter = request.query_params.get("user")
        if user_filter:
            with contextlib.suppress(TypeError, ValueError):
                queryset = queryset.filter(user_id=int(user_filter))

        paginator = StandardPagination()
        page = paginator.paginate_queryset(queryset, request, view=self)

        if page is not None:
            serializer = AdminPaymentListSerializer(page, many=True)
            return paginator.get_paginated_response(
                serializer.data,
                message="لیست پرداخت‌ها با موفقیت دریافت شد.",
            )

        serializer = AdminPaymentListSerializer(queryset, many=True)
        return SuccessResponse(
            data=serializer.data,
            message="لیست پرداخت‌ها با موفقیت دریافت شد.",
        )

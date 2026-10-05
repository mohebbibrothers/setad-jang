"""گروه دامنه‌ای `views_admin_misc` از views — فاز ۱۱ (تفکیک P3-16).

کلاس‌ها عیناً منتقل شده‌اند؛ مشترکات از views_common؛ نامِ عمومیِ این گروه‌ها را فقط از facade (apps.*.views) یا همین ماژول import کنید.
"""

from __future__ import annotations

import contextlib

from django.http import HttpResponseRedirect
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
    _build_payment_result_url,
    _build_receipt_verification_payload,
    _extract_mobile_email,
    _normalized_callback_params,
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

    این endpoint دو مخاطب متفاوت دارد و برای هر کدام رفتار متفاوتی دارد:

    - **GET (مرورگر کاربر، برگشت از صفحهٔ درگاه — مثل Zarinpal):**
      تراکنش verify (یا در صورت ‎Status=NOK لغو-آزادسازی) می‌شود و کاربر
      با **302** به صفحهٔ نتیجهٔ فرانت می‌رود تا هرگز JSON خام نبیند:
        {MADADKAR_PAYMENT_RESULT_BASE_URL}/madadkar/paydone/?authority=…&result=…

    - **POST (مصرف برنامه‌ای — خودِ صفحهٔ نتیجهٔ فرانت و درگاه‌های POST-based):**
      همان منطق، ولی پاسخ JSON کامل (paid/failed/canceled + جزئیات مشارکت).
      صفحهٔ فرانت خودِ URL parameters را «منبع حقیقت» حساب نمی‌کند و با
      همین POST، نتیجهٔ قطعی را (idempotent) بازیابی می‌کند.

    قواعد مشترک:
    - permission: AllowAny (verify بر اساس authority انجام می‌شود؛ زمان
      فراخوانیِ درگاه session کاربر معمولاً موجود نیست).
    - throttle مخصوص (مبتنی بر IP).
    - نام پارامترها case-insensitive نرمال می‌شود — زرین‌پال v4 با
      `Authority`/`Status` برمی‌گردد (yafteh ممیزی: بدون نرمال‌سازی، تمام
      callbackهای واقعی درگاه 400 می‌گرفتند و کاربر فقط JSON خطا می‌دید).
    - **idempotent**: فراخوانی دوباره با همان authority نتیجه قبلی را
      برمی‌گرداند بدون تماس مجدد با درگاه.
    - ‎Status=NOK (لغوی کاربر روی صفحهٔ درگاه) با درگاه تماس نمی‌گیرد؛ مستقیم
      FAILED+آزادسازی می‌شود — verify API زرین‌پال در این حالت کد ‎-21
      می‌دهد و مسیر قدیمی به 502 می‌خورد.
    """

    permission_classes = [AllowAny]
    throttle_classes = [MadadkarPaymentVerifyThrottle]

    @extend_schema(
        operation_id="madadkar_payment_verify",
        tags=[TAG_MADADKAR_USER],
        summary="تأیید پرداخت — callback مرورگر از سمت درگاه (302 به فرانت)",
        description=(
            "درگاه پرداخت مرورگر کاربر را بعد از پایان تراکنش به این آدرس "
            "می‌فرستد (با `Authority` و `Status` در query — case-insensitive پذیرفته می‌شود).\n\n"
            "پاسخ همیشه **302** به صفحهٔ نتیجهٔ فرانت است "
            "(`{base}/madadkar/paydone/?authority=…&result=success|failed|canceled|pending|error`)"
            " تا کاربر هرگز JSON خام نبیند. استثنا: نبودِ کد رهگیری (درخواست نامعتبر) 400 می‌ماند.\n\n"
            "مصرف برنامه‌ای (JSON) را از متد POST همین endpoint استفاده کنید.\n\n"
            "این endpoint **idempotent** است."
        ),
        parameters=[
            OpenApiParameter(
                name="authority",
                type=OpenApiTypes.STR,
                location=OpenApiParameter.QUERY,
                required=True,
                description="کد رهگیری (نام‌های Authority/AUTHORITY هم پذیرفته می‌شوند).",
            ),
            OpenApiParameter(
                name="status",
                type=OpenApiTypes.STR,
                location=OpenApiParameter.QUERY,
                required=False,
                description="وضعیت اولیه درگاه (OK/NOK — قابل اعتماد نیست؛ NOK → آزادسازی فوری).",
            ),
        ],
        responses={
            302: None,
            400: GENERIC_ERROR_RESPONSE,
        },
    )
    def get(self, request: Request):
        # ── GET = مسیر مرورگر. خروجی نهایی همیشه ریدایرکت به فرانت است.
        params = _normalized_callback_params(request.query_params)
        serializer = PaymentVerifyCallbackSerializer(data=params)
        serializer.is_valid(raise_exception=True)
        authority = serializer.validated_data["authority"]
        gateway_status = (serializer.validated_data.get("status") or "").strip().upper()

        def redirect_with(result: str):
            return HttpResponseRedirect(
                _build_payment_result_url(authority=authority, result=result),
            )

        if gateway_status == "NOK":
            try:
                payment = services.cancel_pending_payment(authority=authority)
            except PaymentNotFoundError:
                return redirect_with("error")
            self._audit_result(request, payment, authority)
            if payment.status == PaymentStatus.SUCCESS:
                # race: ورودی درگاه NOK بود ولی تراکنش قبلاً قطعی verify شده
                return redirect_with("success")
            return redirect_with("canceled")

        try:
            payment = services.verify_payment(authority=authority)
        except PaymentNotFoundError:
            return redirect_with("error")
        except PaymentAmountMismatchError:
            self._audit_amount_mismatch(request, authority)
            return redirect_with("error")
        except PaymentGatewayError:
            # قطعی نشد — رزرو هنوز برقرار است تا مهاجرتِ ttl آزاد کند؛
            # صفحهٔ نتیجه با «نامشخص + تلاش مجدد» روبه‌رو می‌شود.
            return redirect_with("pending")

        self._audit_result(request, payment, authority)
        return redirect_with("success" if payment.status == PaymentStatus.SUCCESS else "failed")

    @extend_schema(
        operation_id="madadkar_payment_verify_post",
        tags=[TAG_MADADKAR_USER],
        summary="تأیید پرداخت — POST (مصرف برنامه‌ای: صفحهٔ نتیجهٔ فرانت و درگاه‌های POST-based)",
        description=(
            "همان منطق GET ولی با پاسخ JSON کامل. صفحهٔ نتیجهٔ فرانت پس از "
            "فرود، با همین POST نتیجهٔ قطعی تراکنش را (idempotent) بازیابی می‌کند.\n\n"
            "نام پارامترها case-insensitive است."
        ),
        request=PaymentVerifyCallbackSerializer,
        responses={
            200: PAYMENT_VERIFY_RESPONSE,
            400: GENERIC_ERROR_RESPONSE,
            404: GENERIC_ERROR_RESPONSE,
            502: GENERIC_ERROR_RESPONSE,
        },
    )
    def post(self, request: Request) -> Response:
        params = _normalized_callback_params(request.data)
        serializer = PaymentVerifyCallbackSerializer(data=params)
        serializer.is_valid(raise_exception=True)
        authority = serializer.validated_data["authority"]
        gateway_status = (serializer.validated_data.get("status") or "").strip().upper()

        try:
            if gateway_status == "NOK":
                payment = services.cancel_pending_payment(authority=authority)
            else:
                payment = services.verify_payment(authority=authority)
        except PaymentNotFoundError as exc:
            return ErrorResponse(
                message=str(exc),
                status_code=status.HTTP_404_NOT_FOUND,
            )
        except PaymentAmountMismatchError as exc:
            self._audit_amount_mismatch(request, authority)
            return ErrorResponse(message=str(exc))
        except PaymentGatewayError as exc:
            return ErrorResponse(
                message=str(exc),
                status_code=status.HTTP_502_BAD_GATEWAY,
            )

        self._audit_result(request, payment, authority)

        participation_data = _serialize_participation_detail(payment.participation)
        is_success = payment.status == PaymentStatus.SUCCESS

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

    def _audit_result(self, request: Request, payment, authority: str) -> None:
        """ثبت async رویداد نهایی (SUCCESS/FAILED) — یکجا برای همهٔ شاخه‌ها."""
        is_success = payment.status == PaymentStatus.SUCCESS
        metadata = extract_audit_metadata(request)
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

    def _audit_amount_mismatch(self, request: Request, authority: str) -> None:
        """ثبت sync فاجعهٔ امنیتی — مثل رفتار قبلی، بدون تغییر semantics."""
        metadata = extract_audit_metadata(request)
        log_action(
            user_id=None,
            action=audit_actions.MADADKAR_PAYMENT_FAILED,
            resource_type="madadkar_payment",
            resource_id=authority,
            extra_data={"reason": "amount_mismatch"},
            **metadata,
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

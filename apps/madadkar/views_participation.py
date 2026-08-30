"""گروه دامنه‌ای `views_participation` از views — فاز ۱۱ (تفکیک P3-16).

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
from apps.audit_logs.services import log_action_async
from apps.core.pagination import StandardPagination
from apps.core.responses import (
    CreatedResponse,
    ErrorResponse,
    SuccessResponse,
)

from . import selectors, services
from .permissions import (
    IsAuthenticatedBasic,
    IsParticipationOwner,
)
from .serializers import (
    DonationReceiptSerializer,
    ParticipationInitiateSerializer,
    ParticipationUserDetailSerializer,
    ParticipationUserListSerializer,
)
from .services import (
    CampaignNotAcceptingSharesError,
    InsufficientSharesError,
    InvalidShareCountError,
    PaymentGatewayError,
)
from .throttles import (
    MadadkarParticipateThrottle,
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
# User — Participation (Initiate)
# ============================================================


class MadadkarUserParticipateView(APIView):
    """
    شروع مشارکت کاربر در یک حرکت — POST /api/v1/madadkar/campaigns/{slug}/participate/

    گام‌های اجرا:
    1. اعتبارسنجی share_count و فیلدهای اختیاری.
    2. یافتن campaign از طریق slug (در selector عمومی).
    3. فراخوانی service.initiate_participation که:
       - select_for_update روی campaign می‌گذارد
       - share_count را با remaining_shares مقایسه می‌کند
       - Participation و Payment می‌سازد
       - با درگاه تماس می‌گیرد و authority + gateway_url می‌گیرد
    4. ثبت audit log.
    5. برگشت Participation + gateway_url + authority.
    """

    permission_classes = [IsAuthenticatedBasic]
    throttle_classes = [MadadkarParticipateThrottle]
    parser_classes = [JSONParser, MultiPartParser, FormParser]

    @extend_schema(
        operation_id="madadkar_user_participate",
        tags=[TAG_MADADKAR_USER],
        summary="شروع مشارکت در حرکت",
        description=(
            "کاربر لاگین‌کرده می‌تواند با وارد کردن تعداد سهم، فرآیند پرداخت "
            "را آغاز کند.\n\n"
            "**گام‌ها در سمت کلاینت:**\n"
            "1. این endpoint را با share_count فراخوانی کنید.\n"
            "2. به `gateway_url` ریدایرکت کنید.\n"
            "3. پس از بازگشت از درگاه، endpoint verify خودکار صدا زده می‌شود.\n\n"
            "**نکات امنیتی:**\n"
            "- سهم‌ها به محض initiate رزرو می‌شوند (تا 15 دقیقه).\n"
            "- اگر پرداخت موفق نشود، سهم‌ها خودکار آزاد می‌شوند.\n"
            "- قیمت سهم در لحظه ایجاد ثبت می‌شود (snapshot)."
        ),
        request=ParticipationInitiateSerializer,
        responses={
            201: PARTICIPATION_INITIATED_RESPONSE,
            400: GENERIC_ERROR_RESPONSE,
            401: GENERIC_ERROR_RESPONSE,
            404: GENERIC_ERROR_RESPONSE,
        },
    )
    def post(self, request: Request, slug: str) -> Response:
        # ── یافتن campaign از مسیر public (فقط visible)
        campaign = selectors.get_public_campaign_by_slug(slug=slug)
        if campaign is None:
            return ErrorResponse(
                message="حرکتی با این مشخصات یافت نشد.",
                status_code=status.HTTP_404_NOT_FOUND,
            )

        serializer = ParticipationInitiateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        mobile, email = _extract_mobile_email(
            user=request.user,
            fallback_mobile=data.get("mobile", ""),
            fallback_email=data.get("email", ""),
        )

        metadata = extract_audit_metadata(request)
        ip_address = metadata.get("ip_address")
        user_agent = request.META.get("HTTP_USER_AGENT", "")

        try:
            participation, payment, gateway_url = services.initiate_participation(
                campaign=campaign,
                user=request.user,
                share_count=data["share_count"],
                callback_url=_build_callback_url(),
                ip_address=ip_address,
                user_agent=user_agent,
                mobile=mobile,
                email=email,
            )
        except (
            InvalidShareCountError,
            CampaignNotAcceptingSharesError,
            InsufficientSharesError,
        ) as exc:
            return ErrorResponse(message=str(exc))
        except PaymentGatewayError as exc:
            return ErrorResponse(
                message=str(exc),
                status_code=status.HTTP_502_BAD_GATEWAY,
            )

        log_action_async(
            user_id=request.user.pk,
            action=audit_actions.MADADKAR_PARTICIPATION_INITIATED,
            resource_type="madadkar_participation",
            resource_id=str(participation.pk),
            extra_data={
                "campaign_id": campaign.pk,
                "share_count": participation.share_count,
                "amount": participation.total_amount,
                "authority": payment.authority,
            },
            **metadata,
        )

        response_data = {
            "participation": _serialize_participation_detail(participation),
            "gateway_url": gateway_url,
            "authority": payment.authority,
        }

        return CreatedResponse(
            data=response_data,
            message="پرداخت آغاز شد. لطفاً به درگاه ریدایرکت شوید.",
        )


# ============================================================
# User — My Participations
# ============================================================


@extend_schema_view(
    get=extend_schema(
        operation_id="madadkar_user_my_participations_list",
        tags=[TAG_MADADKAR_USER],
        summary="لیست مشارکت‌های من",
        description="دریافت لیست تمام مشارکت‌های کاربر جاری.",
        parameters=USER_PARTICIPATION_FILTER_PARAMS,
        responses={
            200: USER_PARTICIPATION_LIST_RESPONSE,
            401: GENERIC_ERROR_RESPONSE,
        },
    ),
)
class MadadkarUserMyParticipationsListView(APIView):
    """لیست مشارکت‌های کاربر جاری."""

    permission_classes = [IsAuthenticatedBasic]

    def get(self, request: Request) -> Response:
        queryset = selectors.get_user_participations_queryset(user_id=request.user.pk)

        # فیلتر اختیاری
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
            serializer = ParticipationUserListSerializer(page, many=True)
            return paginator.get_paginated_response(
                serializer.data,
                message="لیست مشارکت‌های شما با موفقیت دریافت شد.",
            )

        serializer = ParticipationUserListSerializer(queryset, many=True)
        return SuccessResponse(
            data=serializer.data,
            message="لیست مشارکت‌های شما با موفقیت دریافت شد.",
        )


class MadadkarUserMyParticipationDetailView(APIView):
    """جزئیات یک مشارکت من — IDOR-safe."""

    permission_classes = [IsAuthenticatedBasic, IsParticipationOwner]

    @extend_schema(
        operation_id="madadkar_user_my_participation_retrieve",
        tags=[TAG_MADADKAR_USER],
        summary="جزئیات یک مشارکت من",
        responses={
            200: USER_PARTICIPATION_DETAIL_RESPONSE,
            401: GENERIC_ERROR_RESPONSE,
            403: GENERIC_ERROR_RESPONSE,
            404: GENERIC_ERROR_RESPONSE,
        },
    )
    def get(self, request: Request, participation_id: int) -> Response:
        participation = selectors.get_user_participation_by_id(
            user_id=request.user.pk,
            participation_id=participation_id,
        )
        if participation is None:
            return ErrorResponse(
                message="مشارکتی با این شناسه یافت نشد.",
                status_code=status.HTTP_404_NOT_FOUND,
            )

        # IDOR check (defensive — selector هم چک کرده)
        self.check_object_permissions(request, participation)

        return SuccessResponse(
            data=ParticipationUserDetailSerializer(participation).data,
            message="جزئیات مشارکت با موفقیت دریافت شد.",
        )


# ============================================================
# User/Public/Admin — Donation Receipts
# ============================================================


class MadadkarUserReceiptListView(APIView):
    """List verifiable donation receipts owned by current user."""

    permission_classes = [IsAuthenticatedBasic]

    @extend_schema(
        operation_id="madadkar_user_receipts_list",
        tags=[TAG_MADADKAR_USER],
        summary="لیست رسیدهای مشارکت من",
        responses={200: USER_RECEIPT_LIST_RESPONSE, 401: GENERIC_ERROR_RESPONSE},
    )
    def get(self, request: Request) -> Response:
        queryset = selectors.get_user_receipts_queryset(user_id=request.user.pk)
        paginator = StandardPagination()
        page = paginator.paginate_queryset(queryset, request, view=self)
        if page is not None:
            serializer = DonationReceiptSerializer(page, many=True)
            return paginator.get_paginated_response(
                serializer.data, message="لیست رسیدها با موفقیت دریافت شد."
            )
        serializer = DonationReceiptSerializer(queryset, many=True)
        return SuccessResponse(data=serializer.data, message="لیست رسیدها با موفقیت دریافت شد.")


class MadadkarUserReceiptDetailView(APIView):
    """Retrieve one user-owned donation receipt and audit access."""

    permission_classes = [IsAuthenticatedBasic]

    @extend_schema(
        operation_id="madadkar_user_receipt_retrieve",
        tags=[TAG_MADADKAR_USER],
        summary="جزئیات رسید مشارکت من",
        responses={
            200: USER_RECEIPT_DETAIL_RESPONSE,
            401: GENERIC_ERROR_RESPONSE,
            404: GENERIC_ERROR_RESPONSE,
        },
    )
    def get(self, request: Request, receipt_id: int) -> Response:
        receipt = selectors.get_user_receipt_by_id(user_id=request.user.pk, receipt_id=receipt_id)
        if receipt is None:
            return ErrorResponse(
                message="رسیدی با این شناسه یافت نشد.", status_code=status.HTTP_404_NOT_FOUND
            )
        metadata = extract_audit_metadata(request)
        log_action_async(
            user_id=request.user.pk,
            action=audit_actions.MADADKAR_RECEIPT_ACCESSED,
            resource_type="madadkar_receipt",
            resource_id=str(receipt.pk),
            extra_data={"receipt_number": receipt.receipt_number},
            **metadata,
        )
        return SuccessResponse(
            data=DonationReceiptSerializer(receipt).data, message="جزئیات رسید با موفقیت دریافت شد."
        )

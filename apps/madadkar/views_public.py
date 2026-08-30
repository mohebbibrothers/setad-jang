"""گروه دامنه‌ای `views_public` از views — فاز ۱۱ (تفکیک P3-16).

کلاس‌ها عیناً منتقل شده‌اند؛ مشترکات از views_common؛ نامِ عمومیِ این گروه‌ها را فقط از facade (apps.*.views) یا همین ماژول import کنید.
"""

from __future__ import annotations

from drf_spectacular.utils import (
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
from apps.audit_logs.services import log_action_async
from apps.core.api_cache import build_cache_variant, cached_public_payload
from apps.core.pagination import StandardPagination
from apps.core.responses import (
    ErrorResponse,
    SuccessResponse,
)

from . import selectors, services
from .filters import (
    CampaignPublicFilter,
)
from .serializers import (
    CampaignPublicDetailSerializer,
    CampaignPublicListSerializer,
    CampaignTransparencySerializer,
    DonationReceiptPublicVerifySerializer,
    SponsorPublicSerializer,
)
from .throttles import (
    MadadkarBrowseAnonThrottle,
    MadadkarBrowseUserThrottle,
    MadadkarReceiptVerifyThrottle,
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
# Public — Sponsors
# ============================================================


@extend_schema_view(
    get=extend_schema(
        operation_id="madadkar_public_sponsors_list",
        tags=[TAG_MADADKAR_PUBLIC],
        summary="لیست مددکاران",
        description=(
            "دریافت لیست تمام مددکارانی که حداقل یک حرکت قابل نمایش دارند.\n\n"
            "این endpoint بدون نیاز به لاگین قابل دسترس است."
        ),
        parameters=LIST_PAGINATION_PARAMS,
        responses={200: PUBLIC_SPONSOR_LIST_RESPONSE},
    ),
)
class MadadkarPublicSponsorListView(APIView):
    """لیست مددکاران — public."""

    permission_classes = [AllowAny]
    throttle_classes = [MadadkarBrowseAnonThrottle, MadadkarBrowseUserThrottle]

    def get(self, request: Request) -> Response:
        def build_payload() -> dict:
            queryset = selectors.get_public_sponsors_queryset()
            paginator = StandardPagination()
            page = paginator.paginate_queryset(queryset, request, view=self)

            if page is not None:
                serializer = SponsorPublicSerializer(page, many=True)
                response = paginator.get_paginated_response(
                    serializer.data,
                    message="لیست مددکاران با موفقیت دریافت شد.",
                )
                return response.data["data"]

            serializer = SponsorPublicSerializer(queryset, many=True)
            return {"results": serializer.data}

        payload = cached_public_payload(
            domain="madadkar",
            namespace="madadkar:public_list",
            parts=(
                "sponsors",
                request.query_params.get("page", "1"),
                request.query_params.get("page_size", str(StandardPagination.page_size)),
            ),
            factory=build_payload,
        )
        return SuccessResponse(data=payload, message="لیست مددکاران با موفقیت دریافت شد.")


@extend_schema_view(
    get=extend_schema(
        operation_id="madadkar_public_sponsor_retrieve",
        tags=[TAG_MADADKAR_PUBLIC],
        summary="جزئیات یک مددکار",
        description="دریافت جزئیات یک مددکار با slug.",
        responses={
            200: PUBLIC_SPONSOR_DETAIL_RESPONSE,
            404: GENERIC_ERROR_RESPONSE,
        },
    ),
)
class MadadkarPublicSponsorDetailView(APIView):
    """جزئیات مددکار — public."""

    permission_classes = [AllowAny]
    throttle_classes = [MadadkarBrowseAnonThrottle, MadadkarBrowseUserThrottle]

    def get(self, request: Request, slug: str) -> Response:
        def build_payload() -> dict | None:
            sponsor = selectors.get_sponsor_by_slug_public(slug=slug)
            if sponsor is None:
                return None
            return SponsorPublicSerializer(sponsor).data

        payload = cached_public_payload(
            domain="madadkar",
            namespace="madadkar:public_detail",
            parts=("sponsor", slug),
            factory=build_payload,
        )
        if payload is None:
            return ErrorResponse(
                message="مددکاری با این مشخصات یافت نشد.",
                status_code=status.HTTP_404_NOT_FOUND,
            )
        return SuccessResponse(data=payload, message="جزئیات مددکار با موفقیت دریافت شد.")


# ============================================================
# Public — Campaigns
# ============================================================


@extend_schema_view(
    get=extend_schema(
        operation_id="madadkar_public_campaigns_list",
        tags=[TAG_MADADKAR_PUBLIC],
        summary="لیست حرکت‌های خیریه",
        description=(
            "دریافت لیست حرکت‌های قابل نمایش (PUBLISHED, COMPLETED, CLOSED).\n\n"
            "حرکت‌های DRAFT و is_visible=False در این لیست نمایش داده نمی‌شوند.\n\n"
            "نتایج paginated و قابل فیلتر می‌باشند."
        ),
        parameters=PUBLIC_CAMPAIGN_FILTER_PARAMS,
        responses={200: PUBLIC_CAMPAIGN_LIST_RESPONSE},
    ),
)
class MadadkarPublicCampaignListView(APIView):
    """لیست حرکت‌ها — public."""

    permission_classes = [AllowAny]
    throttle_classes = [MadadkarBrowseAnonThrottle, MadadkarBrowseUserThrottle]

    def get(self, request: Request) -> Response:
        base_queryset = selectors.get_public_campaigns_queryset()
        filterset = CampaignPublicFilter(request.query_params, queryset=base_queryset)

        def build_payload() -> dict:
            queryset = filterset.qs if filterset.is_valid() else base_queryset

            paginator = StandardPagination()
            page = paginator.paginate_queryset(queryset, request, view=self)

            if page is not None:
                serializer = CampaignPublicListSerializer(
                    page,
                    many=True,
                    context={"request": request},
                )
                response = paginator.get_paginated_response(
                    serializer.data,
                    message="لیست حرکت‌ها با موفقیت دریافت شد.",
                )
                return response.data["data"]

            serializer = CampaignPublicListSerializer(
                queryset,
                many=True,
                context={"request": request},
            )
            return {"results": serializer.data}

        payload = cached_public_payload(
            domain="madadkar",
            namespace="madadkar:public_list",
            parts=(
                "campaigns",
                *build_cache_variant(
                    request, filterset=filterset, pagination_class=StandardPagination
                ),
            ),
            factory=build_payload,
        )
        return SuccessResponse(data=payload, message="لیست حرکت‌ها با موفقیت دریافت شد.")


@extend_schema_view(
    get=extend_schema(
        operation_id="madadkar_public_campaign_retrieve",
        tags=[TAG_MADADKAR_PUBLIC],
        summary="جزئیات یک حرکت خیریه",
        description=(
            "دریافت جزئیات کامل یک حرکت با slug.\n\n"
            "شامل گالری تصاویر، اطلاعات مددکار، پیشرفت سهم و توضیحات کامل."
        ),
        responses={
            200: PUBLIC_CAMPAIGN_DETAIL_RESPONSE,
            404: GENERIC_ERROR_RESPONSE,
        },
    ),
)
class MadadkarPublicCampaignDetailView(APIView):
    """جزئیات حرکت — public."""

    permission_classes = [AllowAny]
    throttle_classes = [MadadkarBrowseAnonThrottle, MadadkarBrowseUserThrottle]

    def get(self, request: Request, slug: str) -> Response:
        def build_payload() -> dict | None:
            campaign = selectors.get_public_campaign_by_slug(slug=slug)
            if campaign is None:
                return None
            return CampaignPublicDetailSerializer(campaign, context={"request": request}).data

        payload = cached_public_payload(
            domain="madadkar",
            namespace="madadkar:public_detail",
            parts=("campaign", slug),
            factory=build_payload,
        )
        if payload is None:
            return ErrorResponse(
                message="حرکتی با این مشخصات یافت نشد.",
                status_code=status.HTTP_404_NOT_FOUND,
            )
        return SuccessResponse(data=payload, message="جزئیات حرکت با موفقیت دریافت شد.")


class MadadkarPublicCampaignTransparencyView(APIView):
    """Public-safe financial transparency snapshot for one campaign."""

    permission_classes = [AllowAny]
    throttle_classes = [MadadkarBrowseAnonThrottle, MadadkarBrowseUserThrottle]

    @extend_schema(
        operation_id="madadkar_public_campaign_transparency",
        tags=[TAG_MADADKAR_PUBLIC],
        summary="شفافیت مالی عمومی حرکت",
        description=(
            "نمای عمومی و بدون اطلاعات خصوصی از وضعیت مالی حرکت: مبالغ جمع‌آوری‌شده، "
            "بازپرداخت‌ها، اصلاحات مالی، تخصیص‌های پرداخت‌شده و مانده قابل تخصیص."
        ),
        responses={
            200: PUBLIC_CAMPAIGN_TRANSPARENCY_RESPONSE,
            404: GENERIC_ERROR_RESPONSE,
        },
    )
    def get(self, request: Request, slug: str) -> Response:
        campaign = selectors.get_public_campaign_by_slug(slug=slug)
        if campaign is None:
            return ErrorResponse(
                message="حرکتی با این مشخصات یافت نشد.",
                status_code=status.HTTP_404_NOT_FOUND,
            )
        transparency = selectors.get_public_campaign_transparency(campaign=campaign)
        return SuccessResponse(
            data=CampaignTransparencySerializer(transparency).data,
            message="گزارش شفافیت مالی حرکت با موفقیت دریافت شد.",
        )


class MadadkarPublicReceiptVerifyView(APIView):
    """Public verification for receipt number/hash pairs without exposing donor PII."""

    permission_classes = [AllowAny]
    # یافتهٔ ممیزی ۵.۱: اوراکل شمارش رسید — throttle اختصاصی per-IP.
    throttle_classes = [MadadkarReceiptVerifyThrottle]

    @extend_schema(
        operation_id="madadkar_public_receipt_verify",
        tags=[TAG_MADADKAR_PUBLIC],
        summary="اعتبارسنجی عمومی رسید مشارکت",
        request=DonationReceiptPublicVerifySerializer,
        responses={200: PUBLIC_RECEIPT_VERIFY_RESPONSE, 400: GENERIC_ERROR_RESPONSE},
    )
    def post(self, request: Request) -> Response:
        serializer = DonationReceiptPublicVerifySerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        is_valid, receipt = services.verify_donation_receipt(**serializer.validated_data)
        payload = _build_receipt_verification_payload(is_valid=is_valid, receipt=receipt)
        metadata = extract_audit_metadata(request)
        log_action_async(
            user_id=None,
            action=audit_actions.MADADKAR_RECEIPT_VERIFIED,
            resource_type="madadkar_receipt",
            resource_id=str(receipt.pk) if receipt else serializer.validated_data["receipt_number"],
            extra_data={
                "is_valid": is_valid,
                "receipt_number": serializer.validated_data["receipt_number"],
            },
            **metadata,
        )
        return SuccessResponse(data=payload, message="نتیجه اعتبارسنجی رسید با موفقیت دریافت شد.")

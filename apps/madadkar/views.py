"""
Views اپ مددکار — Sponsors + Campaigns + Participation + Payment + Analytics.

ساختار:
- Public: لیست/جزئیات مددکاران، لیست/جزئیات حرکت‌ها
- User: شروع مشارکت، callback verify، لیست/جزئیات مشارکت‌های من
- Admin Sponsors: CRUD کامل
- Admin Campaigns: CRUD کامل + publish/close + gallery management
- Admin Analytics: لیست participants، leaderboard، آمار تجمیعی، Excel export
- Admin Payments: لیست تمام پرداخت‌های سامانه با فیلتر

اصول طراحی:
- View هیچ business logic مستقیمی ندارد — همه از طریق service layer.
- Audit log برای تمام mutationهای مهم ثبت می‌شود (شامل export که یک read
  حساس محسوب می‌شود).
- response envelope و استانداردهای Swagger پروژه به‌طور کامل رعایت می‌شوند.
- IDOR در selector و permission layer هندل می‌شود.
- تمام exceptionهای دامنه catch می‌شوند و به ErrorResponse 400 تبدیل می‌شوند.
- callback verify در محیط test ممکن است بدون احراز هویت فراخوانی شود
  (چون session درگاه به سمت ما برمی‌گردد) — پس AllowAny و throttle مخصوص.
- Excel export به‌صورت binary stream با Content-Disposition برگشت داده می‌شود
  (نه envelope) چون فرمت پاسخ binary است.
"""

from __future__ import annotations

import contextlib
import logging

from django.conf import settings
from django.http import HttpResponse
from drf_spectacular.utils import (
    OpenApiParameter,
    OpenApiTypes,
    extend_schema,
    extend_schema_view,
)
from rest_framework import status
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.permissions import AllowAny
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.audit_logs import actions as audit_actions
from apps.audit_logs.helpers import extract_audit_metadata
from apps.audit_logs.services import log_action, log_action_async
from apps.core.api_cache import build_cache_variant, cached_public_payload
from apps.core.pagination import StandardPagination
from apps.core.responses import (
    CreatedResponse,
    DeletedResponse,
    ErrorResponse,
    SuccessResponse,
)
from apps.core.schemas import (
    build_error_response_serializer,
    build_paginated_success_response_serializer,
    build_success_response_serializer,
)

from . import selectors, services
from .choices import PaymentStatus
from .export import build_excel_filename, generate_campaign_participants_excel
from .filters import (
    CampaignAdminFilter,
    CampaignPublicFilter,
    SponsorAdminFilter,
)
from .models import Participation, Sponsor
from .permissions import (
    IsAuthenticatedBasic,
    IsMadadkarAdminUser,
    IsParticipationOwner,
)
from .reconciliation import (
    ReconciliationImportError,
    build_reconciliation_discrepancy_csv,
    parse_settlement_report,
)
from .serializers import (
    AdminCampaignAnalyticsSerializer,
    AdminLeaderboardEntrySerializer,
    AdminParticipantDetailSerializer,
    AdminPaymentListSerializer,
    CampaignAdminCreateSerializer,
    CampaignAdminDetailSerializer,
    CampaignAdminListSerializer,
    CampaignAdminUpdateSerializer,
    CampaignDisbursableSummarySerializer,
    CampaignDisbursementCreateSerializer,
    CampaignDisbursementMarkPaidSerializer,
    CampaignDisbursementRejectSerializer,
    CampaignDisbursementSerializer,
    CampaignFinancialControlSummarySerializer,
    CampaignImageCreateSerializer,
    CampaignImageReadSerializer,
    CampaignIntelligenceSerializer,
    CampaignPublicDetailSerializer,
    CampaignPublicListSerializer,
    CampaignTransparencySerializer,
    DonationReceiptPublicVerifySerializer,
    DonationReceiptResendSerializer,
    DonationReceiptSerializer,
    DonationReceiptVerificationResultSerializer,
    FinancialAdjustmentCreateSerializer,
    FinancialAdjustmentRejectSerializer,
    FinancialAdjustmentSerializer,
    MadadkarFinancialControlSnapshotSerializer,
    MadadkarIntelligenceOverviewSerializer,
    MadadkarRiskSignalReviewSerializer,
    MadadkarRiskSignalSerializer,
    ParticipationInitiatedResponseSerializer,
    ParticipationInitiateSerializer,
    ParticipationUserDetailSerializer,
    ParticipationUserListSerializer,
    PaymentReconciliationBatchSerializer,
    PaymentReconciliationImportSerializer,
    PaymentReconciliationItemSerializer,
    PaymentRefundCompleteSerializer,
    PaymentRefundRejectSerializer,
    PaymentRefundRequestSerializer,
    PaymentRefundSerializer,
    PaymentVerifyCallbackSerializer,
    PaymentVerifyResultSerializer,
    SponsorAdminSerializer,
    SponsorCreateSerializer,
    SponsorPublicSerializer,
    SponsorUpdateSerializer,
)
from .services import (
    CampaignFieldLockedError,
    CampaignInvalidDataError,
    CampaignInvalidStateError,
    CampaignNotAcceptingSharesError,
    DisbursementWorkflowError,
    FinancialAdjustmentWorkflowError,
    InsufficientSharesError,
    InvalidShareCountError,
    PaymentAmountMismatchError,
    PaymentGatewayError,
    PaymentNotFoundError,
    RefundWorkflowError,
    SponsorInUseError,
    SponsorInvalidDataError,
)
from .throttles import (
    MadadkarBrowseAnonThrottle,
    MadadkarBrowseUserThrottle,
    MadadkarParticipateThrottle,
    MadadkarPaymentVerifyThrottle,
    MadadkarReceiptVerifyThrottle,
)

logger = logging.getLogger("apps.madadkar")

# ============================================================
# Tag Constants
# ============================================================

TAG_MADADKAR_PUBLIC = "مددکار — عمومی"
TAG_MADADKAR_USER = "مددکار — کاربر"
TAG_MADADKAR_ADMIN_SPONSOR = "مددکار — مدیریت (مددکاران)"
TAG_MADADKAR_ADMIN_CAMPAIGN = "مددکار — مدیریت (حرکت‌ها)"
TAG_MADADKAR_ADMIN_ANALYTICS = "مددکار — مدیریت (تحلیل و گزارش)"

# ============================================================
# Swagger Response Schemas
# ============================================================

GENERIC_ERROR_RESPONSE = build_error_response_serializer(
    name="MadadkarGenericErrorResponse",
)
EMPTY_SUCCESS_RESPONSE = build_success_response_serializer(
    name="MadadkarEmptySuccessResponse",
)

PUBLIC_SPONSOR_LIST_RESPONSE = build_paginated_success_response_serializer(
    name="MadadkarPublicSponsorListResponse",
    item_serializer=SponsorPublicSerializer,
)
PUBLIC_SPONSOR_DETAIL_RESPONSE = build_success_response_serializer(
    name="MadadkarPublicSponsorDetailResponse",
    data_serializer=SponsorPublicSerializer,
)
ADMIN_SPONSOR_LIST_RESPONSE = build_paginated_success_response_serializer(
    name="MadadkarAdminSponsorListResponse",
    item_serializer=SponsorAdminSerializer,
)
ADMIN_SPONSOR_DETAIL_RESPONSE = build_success_response_serializer(
    name="MadadkarAdminSponsorDetailResponse",
    data_serializer=SponsorAdminSerializer,
)
PUBLIC_CAMPAIGN_LIST_RESPONSE = build_paginated_success_response_serializer(
    name="MadadkarPublicCampaignListResponse",
    item_serializer=CampaignPublicListSerializer,
)
PUBLIC_CAMPAIGN_DETAIL_RESPONSE = build_success_response_serializer(
    name="MadadkarPublicCampaignDetailResponse",
    data_serializer=CampaignPublicDetailSerializer,
)
PUBLIC_CAMPAIGN_TRANSPARENCY_RESPONSE = build_success_response_serializer(
    name="MadadkarPublicCampaignTransparencyResponse",
    data_serializer=CampaignTransparencySerializer,
)
ADMIN_CAMPAIGN_LIST_RESPONSE = build_paginated_success_response_serializer(
    name="MadadkarAdminCampaignListResponse",
    item_serializer=CampaignAdminListSerializer,
)
ADMIN_CAMPAIGN_DETAIL_RESPONSE = build_success_response_serializer(
    name="MadadkarAdminCampaignDetailResponse",
    data_serializer=CampaignAdminDetailSerializer,
)
ADMIN_CAMPAIGN_IMAGE_RESPONSE = build_success_response_serializer(
    name="MadadkarAdminCampaignImageResponse",
    data_serializer=CampaignImageReadSerializer,
)
ADMIN_CAMPAIGN_IMAGE_LIST_RESPONSE = build_success_response_serializer(
    name="MadadkarAdminCampaignImageListResponse",
    data_serializer=CampaignImageReadSerializer,
    many=True,
)

# ── Participation / Payment responses
PARTICIPATION_INITIATED_RESPONSE = build_success_response_serializer(
    name="MadadkarParticipationInitiatedResponse",
    data_serializer=ParticipationInitiatedResponseSerializer,
)
USER_PARTICIPATION_LIST_RESPONSE = build_paginated_success_response_serializer(
    name="MadadkarUserParticipationListResponse",
    item_serializer=ParticipationUserListSerializer,
)
USER_PARTICIPATION_DETAIL_RESPONSE = build_success_response_serializer(
    name="MadadkarUserParticipationDetailResponse",
    data_serializer=ParticipationUserDetailSerializer,
)
PAYMENT_VERIFY_RESPONSE = build_success_response_serializer(
    name="MadadkarPaymentVerifyResponse",
    data_serializer=PaymentVerifyResultSerializer,
)

# ── Admin Analytics responses
ADMIN_PARTICIPANTS_LIST_RESPONSE = build_paginated_success_response_serializer(
    name="MadadkarAdminParticipantsListResponse",
    item_serializer=AdminParticipantDetailSerializer,
)
ADMIN_LEADERBOARD_RESPONSE = build_success_response_serializer(
    name="MadadkarAdminLeaderboardResponse",
    data_serializer=AdminLeaderboardEntrySerializer,
    many=True,
)
ADMIN_CAMPAIGN_ANALYTICS_RESPONSE = build_success_response_serializer(
    name="MadadkarAdminCampaignAnalyticsResponse",
    data_serializer=AdminCampaignAnalyticsSerializer,
)
ADMIN_PAYMENTS_LIST_RESPONSE = build_paginated_success_response_serializer(
    name="MadadkarAdminPaymentsListResponse",
    item_serializer=AdminPaymentListSerializer,
)
ADMIN_REFUNDS_LIST_RESPONSE = build_paginated_success_response_serializer(
    name="MadadkarAdminRefundsListResponse",
    item_serializer=PaymentRefundSerializer,
)
ADMIN_REFUND_DETAIL_RESPONSE = build_success_response_serializer(
    name="MadadkarAdminRefundDetailResponse",
    data_serializer=PaymentRefundSerializer,
)
ADMIN_ADJUSTMENTS_LIST_RESPONSE = build_paginated_success_response_serializer(
    name="MadadkarAdminAdjustmentsListResponse",
    item_serializer=FinancialAdjustmentSerializer,
)
ADMIN_ADJUSTMENT_DETAIL_RESPONSE = build_success_response_serializer(
    name="MadadkarAdminAdjustmentDetailResponse",
    data_serializer=FinancialAdjustmentSerializer,
)
ADMIN_FINANCIAL_CONTROL_RESPONSE = build_success_response_serializer(
    name="MadadkarAdminFinancialControlResponse",
    data_serializer=CampaignFinancialControlSummarySerializer,
)
ADMIN_RISK_SIGNALS_LIST_RESPONSE = build_paginated_success_response_serializer(
    name="MadadkarAdminRiskSignalsListResponse",
    item_serializer=MadadkarRiskSignalSerializer,
)
ADMIN_RISK_SIGNAL_DETAIL_RESPONSE = build_success_response_serializer(
    name="MadadkarAdminRiskSignalDetailResponse",
    data_serializer=MadadkarRiskSignalSerializer,
)
ADMIN_CAMPAIGN_INTELLIGENCE_RESPONSE = build_success_response_serializer(
    name="MadadkarAdminCampaignIntelligenceResponse",
    data_serializer=CampaignIntelligenceSerializer,
)
ADMIN_INTELLIGENCE_OVERVIEW_RESPONSE = build_success_response_serializer(
    name="MadadkarAdminIntelligenceOverviewResponse",
    data_serializer=MadadkarIntelligenceOverviewSerializer,
)
USER_RECEIPT_LIST_RESPONSE = build_paginated_success_response_serializer(
    name="MadadkarUserReceiptListResponse",
    item_serializer=DonationReceiptSerializer,
)
USER_RECEIPT_DETAIL_RESPONSE = build_success_response_serializer(
    name="MadadkarUserReceiptDetailResponse",
    data_serializer=DonationReceiptSerializer,
)
PUBLIC_RECEIPT_VERIFY_RESPONSE = build_success_response_serializer(
    name="MadadkarPublicReceiptVerifyResponse",
    data_serializer=DonationReceiptVerificationResultSerializer,
)
ADMIN_RECONCILIATION_BATCH_LIST_RESPONSE = build_paginated_success_response_serializer(
    name="MadadkarAdminReconciliationBatchListResponse",
    item_serializer=PaymentReconciliationBatchSerializer,
)
ADMIN_RECONCILIATION_BATCH_DETAIL_RESPONSE = build_success_response_serializer(
    name="MadadkarAdminReconciliationBatchDetailResponse",
    data_serializer=PaymentReconciliationBatchSerializer,
)
ADMIN_RECONCILIATION_ITEM_LIST_RESPONSE = build_paginated_success_response_serializer(
    name="MadadkarAdminReconciliationItemListResponse",
    item_serializer=PaymentReconciliationItemSerializer,
)
ADMIN_DISBURSEMENT_LIST_RESPONSE = build_paginated_success_response_serializer(
    name="MadadkarAdminDisbursementListResponse",
    item_serializer=CampaignDisbursementSerializer,
)
ADMIN_DISBURSEMENT_DETAIL_RESPONSE = build_success_response_serializer(
    name="MadadkarAdminDisbursementDetailResponse",
    data_serializer=CampaignDisbursementSerializer,
)
ADMIN_DISBURSABLE_SUMMARY_RESPONSE = build_success_response_serializer(
    name="MadadkarAdminDisbursableSummaryResponse",
    data_serializer=CampaignDisbursableSummarySerializer,
)
ADMIN_FINANCIAL_CONTROL_SNAPSHOT_LIST_RESPONSE = build_paginated_success_response_serializer(
    name="MadadkarAdminFinancialControlSnapshotListResponse",
    item_serializer=MadadkarFinancialControlSnapshotSerializer,
)
ADMIN_FINANCIAL_CONTROL_SNAPSHOT_DETAIL_RESPONSE = build_success_response_serializer(
    name="MadadkarAdminFinancialControlSnapshotDetailResponse",
    data_serializer=MadadkarFinancialControlSnapshotSerializer,
)


# ============================================================
# Common Query Parameters
# ============================================================

LIST_PAGINATION_PARAMS = [
    OpenApiParameter(
        name="page",
        type=OpenApiTypes.INT,
        location=OpenApiParameter.QUERY,
        description="شماره صفحه",
    ),
    OpenApiParameter(
        name="page_size",
        type=OpenApiTypes.INT,
        location=OpenApiParameter.QUERY,
        description="تعداد آیتم در هر صفحه (حداکثر ۱۰۰)",
    ),
]

PUBLIC_CAMPAIGN_FILTER_PARAMS = [
    *LIST_PAGINATION_PARAMS,
    OpenApiParameter(
        name="sponsor",
        type=OpenApiTypes.INT,
        location=OpenApiParameter.QUERY,
        description="فیلتر بر اساس شناسه مددکار",
    ),
    OpenApiParameter(
        name="sponsor_slug",
        type=OpenApiTypes.STR,
        location=OpenApiParameter.QUERY,
        description="فیلتر بر اساس slug مددکار",
    ),
    OpenApiParameter(
        name="status",
        type=OpenApiTypes.STR,
        location=OpenApiParameter.QUERY,
        enum=["published", "completed", "closed"],
        description="فیلتر بر اساس وضعیت حرکت",
    ),
    OpenApiParameter(
        name="has_deadline",
        type=OpenApiTypes.BOOL,
        location=OpenApiParameter.QUERY,
        description="فیلتر بر اساس داشتن مهلت زمانی",
    ),
    OpenApiParameter(
        name="is_fully_funded",
        type=OpenApiTypes.BOOL,
        location=OpenApiParameter.QUERY,
        description="فیلتر بر اساس تکمیل ۱۰۰٪ سهم‌ها",
    ),
    OpenApiParameter(
        name="search",
        type=OpenApiTypes.STR,
        location=OpenApiParameter.QUERY,
        description="جستجو در عنوان و توضیحات",
    ),
    OpenApiParameter(
        name="ordering",
        type=OpenApiTypes.STR,
        location=OpenApiParameter.QUERY,
        description="ترتیب: published_at, created_at, progress, deadline (با - برای descending)",
    ),
]

ADMIN_CAMPAIGN_FILTER_PARAMS = [
    *LIST_PAGINATION_PARAMS,
    OpenApiParameter(
        name="sponsor",
        type=OpenApiTypes.INT,
        location=OpenApiParameter.QUERY,
        description="شناسه مددکار",
    ),
    OpenApiParameter(
        name="status",
        type=OpenApiTypes.STR,
        location=OpenApiParameter.QUERY,
        enum=["draft", "published", "completed", "closed"],
        description="وضعیت حرکت",
    ),
    OpenApiParameter(name="is_visible", type=OpenApiTypes.BOOL, location=OpenApiParameter.QUERY),
    OpenApiParameter(name="is_active", type=OpenApiTypes.BOOL, location=OpenApiParameter.QUERY),
    OpenApiParameter(
        name="created_after", type=OpenApiTypes.DATETIME, location=OpenApiParameter.QUERY
    ),
    OpenApiParameter(
        name="created_before", type=OpenApiTypes.DATETIME, location=OpenApiParameter.QUERY
    ),
    OpenApiParameter(
        name="min_total_amount", type=OpenApiTypes.INT, location=OpenApiParameter.QUERY
    ),
    OpenApiParameter(
        name="max_total_amount", type=OpenApiTypes.INT, location=OpenApiParameter.QUERY
    ),
    OpenApiParameter(name="search", type=OpenApiTypes.STR, location=OpenApiParameter.QUERY),
]

ADMIN_SPONSOR_FILTER_PARAMS = [
    *LIST_PAGINATION_PARAMS,
    OpenApiParameter(name="is_active", type=OpenApiTypes.BOOL, location=OpenApiParameter.QUERY),
    OpenApiParameter(name="search", type=OpenApiTypes.STR, location=OpenApiParameter.QUERY),
]

USER_PARTICIPATION_FILTER_PARAMS = [
    *LIST_PAGINATION_PARAMS,
    OpenApiParameter(
        name="status",
        type=OpenApiTypes.STR,
        location=OpenApiParameter.QUERY,
        enum=["pending_payment", "paid", "failed", "expired"],
        description="فیلتر بر اساس وضعیت مشارکت",
    ),
    OpenApiParameter(
        name="campaign",
        type=OpenApiTypes.INT,
        location=OpenApiParameter.QUERY,
        description="فیلتر بر اساس شناسه حرکت",
    ),
]

ADMIN_PAYMENTS_FILTER_PARAMS = [
    *LIST_PAGINATION_PARAMS,
    OpenApiParameter(
        name="status",
        type=OpenApiTypes.STR,
        location=OpenApiParameter.QUERY,
        enum=["pending", "success", "failed"],
        description="فیلتر بر اساس وضعیت پرداخت",
    ),
    OpenApiParameter(
        name="gateway_name",
        type=OpenApiTypes.STR,
        location=OpenApiParameter.QUERY,
        description="فیلتر بر اساس نام درگاه (sandbox, zarinpal, ...)",
    ),
    OpenApiParameter(
        name="campaign",
        type=OpenApiTypes.INT,
        location=OpenApiParameter.QUERY,
        description="فیلتر بر اساس شناسه حرکت",
    ),
    OpenApiParameter(
        name="user",
        type=OpenApiTypes.INT,
        location=OpenApiParameter.QUERY,
        description="فیلتر بر اساس شناسه کاربر",
    ),
]


# ============================================================
# Helpers
# ============================================================


def _build_callback_url() -> str:
    """ساخت URL کامل برای callback verify بر اساس settings."""
    base = settings.MADADKAR_PAYMENT_CALLBACK_BASE_URL.rstrip("/")
    return f"{base}/api/v1/madadkar/payment/verify/"


def _extract_mobile_email(user, fallback_mobile: str, fallback_email: str) -> tuple[str, str]:
    """
    استخراج mobile/email از پروفایل کاربر در صورت ارسال نشدن از سمت client.

    این تابع defensive است و اگر attribute نباشد، fallback را برمی‌گرداند.
    """
    mobile = fallback_mobile
    email = fallback_email

    if not mobile:
        # User model attributes — defensive lookup
        mobile = getattr(user, "phone_number", "") or getattr(user, "mobile", "") or ""

    if not email:
        email = getattr(user, "email", "") or ""

    return mobile, email


def _serialize_participation_detail(participation: Participation) -> dict:
    """سریالایز کردن participation با eager-loading رابطه‌های لازم."""
    # eager load با selector
    fresh = selectors.get_user_participation_by_id(
        user_id=participation.user_id,
        participation_id=participation.pk,
    )
    return ParticipationUserDetailSerializer(fresh or participation).data


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


def _build_receipt_verification_payload(*, is_valid: bool, receipt) -> dict:
    """Build public-safe receipt verification response payload."""
    if receipt is None:
        return {
            "is_valid": False,
            "receipt_number": "",
            "amount": None,
            "issued_at": None,
            "campaign_title": "",
            "sponsor_name": "",
            "hash_version": None,
        }
    return {
        "is_valid": is_valid,
        "receipt_number": receipt.receipt_number,
        "amount": receipt.amount if is_valid else None,
        "issued_at": receipt.issued_at if is_valid else None,
        "campaign_title": receipt.campaign_snapshot.get("title", "") if is_valid else "",
        "sponsor_name": receipt.campaign_snapshot.get("sponsor_name", "") if is_valid else "",
        "hash_version": receipt.hash_version if is_valid else None,
    }


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
# Admin — Campaigns CRUD
# ============================================================


@extend_schema_view(
    get=extend_schema(
        operation_id="madadkar_admin_campaigns_list",
        tags=[TAG_MADADKAR_ADMIN_CAMPAIGN],
        summary="لیست حرکت‌ها — ادمین",
        parameters=ADMIN_CAMPAIGN_FILTER_PARAMS,
        responses={200: ADMIN_CAMPAIGN_LIST_RESPONSE, 403: GENERIC_ERROR_RESPONSE},
    ),
    post=extend_schema(
        operation_id="madadkar_admin_campaigns_create",
        tags=[TAG_MADADKAR_ADMIN_CAMPAIGN],
        summary="ساخت حرکت جدید — ادمین",
        request=CampaignAdminCreateSerializer,
        responses={
            201: ADMIN_CAMPAIGN_DETAIL_RESPONSE,
            400: GENERIC_ERROR_RESPONSE,
            403: GENERIC_ERROR_RESPONSE,
            404: GENERIC_ERROR_RESPONSE,
        },
    ),
)
class MadadkarAdminCampaignListCreateView(APIView):
    """list + create campaigns — admin."""

    permission_classes = [IsMadadkarAdminUser]
    parser_classes = [MultiPartParser, FormParser, JSONParser]

    def get(self, request: Request) -> Response:
        queryset = selectors.get_admin_campaigns_queryset()
        filterset = CampaignAdminFilter(request.query_params, queryset=queryset)
        if filterset.is_valid():
            queryset = filterset.qs

        paginator = StandardPagination()
        page = paginator.paginate_queryset(queryset, request, view=self)

        if page is not None:
            serializer = CampaignAdminListSerializer(page, many=True)
            return paginator.get_paginated_response(
                serializer.data,
                message="لیست حرکت‌ها با موفقیت دریافت شد.",
            )

        serializer = CampaignAdminListSerializer(queryset, many=True)
        return SuccessResponse(
            data=serializer.data,
            message="لیست حرکت‌ها با موفقیت دریافت شد.",
        )

    def post(self, request: Request) -> Response:
        serializer = CampaignAdminCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        data = dict(serializer.validated_data)
        sponsor_id = data.pop("sponsor_id")

        sponsor = Sponsor.objects.filter(pk=sponsor_id).first()
        if sponsor is None:
            return ErrorResponse(
                message="مددکاری با این شناسه یافت نشد.",
                status_code=status.HTTP_404_NOT_FOUND,
            )

        try:
            campaign = services.create_campaign(sponsor=sponsor, **data)
        except CampaignInvalidDataError as exc:
            return ErrorResponse(message=str(exc))

        metadata = extract_audit_metadata(request)
        log_action_async(
            user_id=request.user.pk,
            action=audit_actions.MADADKAR_CAMPAIGN_CREATED,
            resource_type="madadkar_campaign",
            resource_id=str(campaign.pk),
            extra_data={
                "sponsor_id": sponsor.pk,
                "total_amount": campaign.total_amount,
                "total_shares": campaign.total_shares,
            },
            **metadata,
        )

        return CreatedResponse(
            data=CampaignAdminDetailSerializer(campaign).data,
            message="حرکت با موفقیت ساخته شد.",
        )


@extend_schema_view(
    get=extend_schema(
        operation_id="madadkar_admin_campaign_retrieve",
        tags=[TAG_MADADKAR_ADMIN_CAMPAIGN],
        summary="جزئیات حرکت — ادمین",
        responses={
            200: ADMIN_CAMPAIGN_DETAIL_RESPONSE,
            403: GENERIC_ERROR_RESPONSE,
            404: GENERIC_ERROR_RESPONSE,
        },
    ),
    patch=extend_schema(
        operation_id="madadkar_admin_campaign_update",
        tags=[TAG_MADADKAR_ADMIN_CAMPAIGN],
        summary="ویرایش حرکت — ادمین",
        description=(
            "ویرایش فیلدهای حرکت با اعمال قوانین قفل:\n\n"
            "- در وضعیت DRAFT و PUBLISHED بدون پرداخت موفق: همه فیلدها قابل ویرایش\n"
            "- بعد از اولین پرداخت موفق: فیلدهای مالی (مبلغ کل، تعداد سهم، مددکار) قفل می‌شوند\n"
            "- در وضعیت COMPLETED و CLOSED: فقط متن‌ها و تصاویر قابل ویرایش\n"
            "- deadline فقط می‌تواند به جلو منتقل شود (نه عقب)"
        ),
        request=CampaignAdminUpdateSerializer,
        responses={
            200: ADMIN_CAMPAIGN_DETAIL_RESPONSE,
            400: GENERIC_ERROR_RESPONSE,
            403: GENERIC_ERROR_RESPONSE,
            404: GENERIC_ERROR_RESPONSE,
        },
    ),
    delete=extend_schema(
        operation_id="madadkar_admin_campaign_delete",
        tags=[TAG_MADADKAR_ADMIN_CAMPAIGN],
        summary="حذف نرم حرکت — ادمین",
        description="فقط حرکت‌های در وضعیت DRAFT قابل حذف هستند.",
        responses={
            200: EMPTY_SUCCESS_RESPONSE,
            400: GENERIC_ERROR_RESPONSE,
            403: GENERIC_ERROR_RESPONSE,
            404: GENERIC_ERROR_RESPONSE,
        },
    ),
)
class MadadkarAdminCampaignDetailView(APIView):
    """retrieve + update + delete campaign — admin."""

    permission_classes = [IsMadadkarAdminUser]
    parser_classes = [MultiPartParser, FormParser, JSONParser]

    def get(self, request: Request, campaign_id: int) -> Response:
        campaign = selectors.get_admin_campaign_by_id(campaign_id=campaign_id)
        if campaign is None:
            return ErrorResponse(
                message="حرکتی با این شناسه یافت نشد.",
                status_code=status.HTTP_404_NOT_FOUND,
            )
        return SuccessResponse(
            data=CampaignAdminDetailSerializer(campaign).data,
            message="جزئیات حرکت با موفقیت دریافت شد.",
        )

    def patch(self, request: Request, campaign_id: int) -> Response:
        campaign = selectors.get_admin_campaign_by_id(campaign_id=campaign_id)
        if campaign is None:
            return ErrorResponse(
                message="حرکتی با این شناسه یافت نشد.",
                status_code=status.HTTP_404_NOT_FOUND,
            )

        serializer = CampaignAdminUpdateSerializer(
            data=request.data,
            partial=True,
            context={"campaign": campaign},
        )
        serializer.is_valid(raise_exception=True)

        update_data = dict(serializer.validated_data)

        # تبدیل sponsor_id به sponsor instance در صورت ارسال
        if "sponsor_id" in update_data:
            sponsor_id = update_data.pop("sponsor_id")
            sponsor = Sponsor.objects.filter(pk=sponsor_id).first()
            if sponsor is None:
                return ErrorResponse(
                    message="مددکاری با این شناسه یافت نشد.",
                    status_code=status.HTTP_404_NOT_FOUND,
                )
            update_data["sponsor"] = sponsor

        try:
            campaign = services.update_campaign(campaign=campaign, **update_data)
        except (CampaignFieldLockedError, CampaignInvalidDataError) as exc:
            return ErrorResponse(message=str(exc))

        metadata = extract_audit_metadata(request)
        log_action_async(
            user_id=request.user.pk,
            action=audit_actions.MADADKAR_CAMPAIGN_UPDATED,
            resource_type="madadkar_campaign",
            resource_id=str(campaign.pk),
            changes={k: str(v) for k, v in serializer.validated_data.items()},
            **metadata,
        )

        return SuccessResponse(
            data=CampaignAdminDetailSerializer(campaign).data,
            message="حرکت با موفقیت بروزرسانی شد.",
        )

    def delete(self, request: Request, campaign_id: int) -> Response:
        campaign = selectors.get_admin_campaign_by_id(campaign_id=campaign_id)
        if campaign is None:
            return ErrorResponse(
                message="حرکتی با این شناسه یافت نشد.",
                status_code=status.HTTP_404_NOT_FOUND,
            )

        try:
            services.delete_campaign(campaign=campaign)
        except CampaignInvalidStateError as exc:
            return ErrorResponse(message=str(exc))

        metadata = extract_audit_metadata(request)
        log_action(
            user_id=request.user.pk,
            action=audit_actions.MADADKAR_CAMPAIGN_DELETED,
            resource_type="madadkar_campaign",
            resource_id=str(campaign_id),
            extra_data={"slug": campaign.slug},
            **metadata,
        )

        return DeletedResponse(message="حرکت با موفقیت حذف شد.")


# ============================================================
# Admin — Campaign Lifecycle Actions
# ============================================================


class MadadkarAdminCampaignPublishView(APIView):
    """انتشار حرکت — admin."""

    permission_classes = [IsMadadkarAdminUser]

    @extend_schema(
        operation_id="madadkar_admin_campaign_publish",
        tags=[TAG_MADADKAR_ADMIN_CAMPAIGN],
        summary="انتشار حرکت — ادمین",
        description="انتقال حرکت از DRAFT به PUBLISHED.",
        request=None,
        responses={
            200: ADMIN_CAMPAIGN_DETAIL_RESPONSE,
            400: GENERIC_ERROR_RESPONSE,
            403: GENERIC_ERROR_RESPONSE,
            404: GENERIC_ERROR_RESPONSE,
        },
    )
    def post(self, request: Request, campaign_id: int) -> Response:
        campaign = selectors.get_admin_campaign_by_id(campaign_id=campaign_id)
        if campaign is None:
            return ErrorResponse(
                message="حرکتی با این شناسه یافت نشد.",
                status_code=status.HTTP_404_NOT_FOUND,
            )

        try:
            campaign = services.publish_campaign(campaign=campaign)
        except CampaignInvalidStateError as exc:
            return ErrorResponse(message=str(exc))

        metadata = extract_audit_metadata(request)
        log_action_async(
            user_id=request.user.pk,
            action=audit_actions.MADADKAR_CAMPAIGN_PUBLISHED,
            resource_type="madadkar_campaign",
            resource_id=str(campaign.pk),
            **metadata,
        )

        return SuccessResponse(
            data=CampaignAdminDetailSerializer(campaign).data,
            message="حرکت با موفقیت منتشر شد.",
        )


class MadadkarAdminCampaignCloseView(APIView):
    """بستن دستی حرکت — admin."""

    permission_classes = [IsMadadkarAdminUser]

    @extend_schema(
        operation_id="madadkar_admin_campaign_close",
        tags=[TAG_MADADKAR_ADMIN_CAMPAIGN],
        summary="بستن دستی حرکت — ادمین",
        description=("انتقال حرکت از PUBLISHED به CLOSED. از این پس امکان مشارکت جدید وجود ندارد."),
        request=None,
        responses={
            200: ADMIN_CAMPAIGN_DETAIL_RESPONSE,
            400: GENERIC_ERROR_RESPONSE,
            403: GENERIC_ERROR_RESPONSE,
            404: GENERIC_ERROR_RESPONSE,
        },
    )
    def post(self, request: Request, campaign_id: int) -> Response:
        campaign = selectors.get_admin_campaign_by_id(campaign_id=campaign_id)
        if campaign is None:
            return ErrorResponse(
                message="حرکتی با این شناسه یافت نشد.",
                status_code=status.HTTP_404_NOT_FOUND,
            )

        try:
            campaign = services.close_campaign(campaign=campaign)
        except CampaignInvalidStateError as exc:
            return ErrorResponse(message=str(exc))

        metadata = extract_audit_metadata(request)
        log_action_async(
            user_id=request.user.pk,
            action=audit_actions.MADADKAR_CAMPAIGN_CLOSED,
            resource_type="madadkar_campaign",
            resource_id=str(campaign.pk),
            **metadata,
        )

        return SuccessResponse(
            data=CampaignAdminDetailSerializer(campaign).data,
            message="حرکت با موفقیت بسته شد.",
        )


# ============================================================
# Admin — Campaign Gallery
# ============================================================


class MadadkarAdminCampaignImageListCreateView(APIView):
    """list + upload gallery image — admin."""

    permission_classes = [IsMadadkarAdminUser]
    parser_classes = [MultiPartParser, FormParser, JSONParser]

    @extend_schema(
        operation_id="madadkar_admin_campaign_images_list",
        tags=[TAG_MADADKAR_ADMIN_CAMPAIGN],
        summary="لیست تصاویر گالری حرکت",
        responses={
            200: ADMIN_CAMPAIGN_IMAGE_LIST_RESPONSE,
            403: GENERIC_ERROR_RESPONSE,
            404: GENERIC_ERROR_RESPONSE,
        },
    )
    def get(self, request: Request, campaign_id: int) -> Response:
        campaign = selectors.get_admin_campaign_by_id(campaign_id=campaign_id)
        if campaign is None:
            return ErrorResponse(
                message="حرکتی با این شناسه یافت نشد.",
                status_code=status.HTTP_404_NOT_FOUND,
            )

        images = campaign.gallery_images.filter(is_active=True).order_by(
            "display_order",
            "created_at",
        )
        return SuccessResponse(
            data=CampaignImageReadSerializer(images, many=True).data,
            message="لیست تصاویر گالری با موفقیت دریافت شد.",
        )

    @extend_schema(
        operation_id="madadkar_admin_campaign_images_create",
        tags=[TAG_MADADKAR_ADMIN_CAMPAIGN],
        summary="افزودن تصویر به گالری حرکت",
        request=CampaignImageCreateSerializer,
        responses={
            201: ADMIN_CAMPAIGN_IMAGE_RESPONSE,
            400: GENERIC_ERROR_RESPONSE,
            403: GENERIC_ERROR_RESPONSE,
            404: GENERIC_ERROR_RESPONSE,
        },
    )
    def post(self, request: Request, campaign_id: int) -> Response:
        campaign = selectors.get_admin_campaign_by_id(campaign_id=campaign_id)
        if campaign is None:
            return ErrorResponse(
                message="حرکتی با این شناسه یافت نشد.",
                status_code=status.HTTP_404_NOT_FOUND,
            )

        serializer = CampaignImageCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        image = services.add_campaign_image(
            campaign=campaign,
            **serializer.validated_data,
        )

        metadata = extract_audit_metadata(request)
        log_action_async(
            user_id=request.user.pk,
            action=audit_actions.MADADKAR_CAMPAIGN_IMAGE_ADDED,
            resource_type="madadkar_campaign_image",
            resource_id=str(image.pk),
            extra_data={"campaign_id": campaign_id},
            **metadata,
        )

        return CreatedResponse(
            data=CampaignImageReadSerializer(image).data,
            message="تصویر با موفقیت به گالری اضافه شد.",
        )


class MadadkarAdminCampaignImageDeleteView(APIView):
    """delete gallery image — admin."""

    permission_classes = [IsMadadkarAdminUser]

    @extend_schema(
        operation_id="madadkar_admin_campaign_images_delete",
        tags=[TAG_MADADKAR_ADMIN_CAMPAIGN],
        summary="حذف تصویر از گالری حرکت",
        responses={
            200: EMPTY_SUCCESS_RESPONSE,
            403: GENERIC_ERROR_RESPONSE,
            404: GENERIC_ERROR_RESPONSE,
        },
    )
    def delete(self, request: Request, campaign_id: int, image_id: int) -> Response:
        campaign = selectors.get_admin_campaign_by_id(campaign_id=campaign_id)
        if campaign is None:
            return ErrorResponse(
                message="حرکتی با این شناسه یافت نشد.",
                status_code=status.HTTP_404_NOT_FOUND,
            )

        image = campaign.gallery_images.filter(pk=image_id, is_active=True).first()
        if image is None:
            return ErrorResponse(
                message="تصویری با این شناسه یافت نشد.",
                status_code=status.HTTP_404_NOT_FOUND,
            )

        services.delete_campaign_image(image=image)

        metadata = extract_audit_metadata(request)
        log_action_async(
            user_id=request.user.pk,
            action=audit_actions.MADADKAR_CAMPAIGN_IMAGE_REMOVED,
            resource_type="madadkar_campaign_image",
            resource_id=str(image_id),
            extra_data={"campaign_id": campaign_id},
            **metadata,
        )

        return DeletedResponse(message="تصویر با موفقیت از گالری حذف شد.")


# ============================================================
# Admin — Analytics & Reports
# ============================================================


class MadadkarAdminCampaignParticipantsListView(APIView):
    """
    لیست مشارکت‌کنندگان یک حرکت — admin.

    فقط participationهای PAID. ترتیب: بزرگ‌ترین مبلغ ابتدا.
    """

    permission_classes = [IsMadadkarAdminUser]

    @extend_schema(
        operation_id="madadkar_admin_campaign_participants_list",
        tags=[TAG_MADADKAR_ADMIN_ANALYTICS],
        summary="لیست مشارکت‌کنندگان حرکت — ادمین",
        description=(
            "دریافت لیست تمام مشارکت‌های موفق (PAID) یک حرکت. "
            "ترتیب: بزرگ‌ترین مبلغ ابتدا، سپس آخرین پرداخت‌ها.\n\n"
            "شامل اطلاعات کامل کاربر و Payment."
        ),
        parameters=LIST_PAGINATION_PARAMS,
        responses={
            200: ADMIN_PARTICIPANTS_LIST_RESPONSE,
            403: GENERIC_ERROR_RESPONSE,
            404: GENERIC_ERROR_RESPONSE,
        },
    )
    def get(self, request: Request, campaign_id: int) -> Response:
        campaign = selectors.get_admin_campaign_by_id(campaign_id=campaign_id)
        if campaign is None:
            return ErrorResponse(
                message="حرکتی با این شناسه یافت نشد.",
                status_code=status.HTTP_404_NOT_FOUND,
            )

        queryset = selectors.get_campaign_paid_participations_queryset(
            campaign=campaign,
        )

        paginator = StandardPagination()
        page = paginator.paginate_queryset(queryset, request, view=self)

        if page is not None:
            serializer = AdminParticipantDetailSerializer(page, many=True)
            return paginator.get_paginated_response(
                serializer.data,
                message="لیست مشارکت‌کنندگان با موفقیت دریافت شد.",
            )

        serializer = AdminParticipantDetailSerializer(queryset, many=True)
        return SuccessResponse(
            data=serializer.data,
            message="لیست مشارکت‌کنندگان با موفقیت دریافت شد.",
        )


class MadadkarAdminCampaignLeaderboardView(APIView):
    """Top contributors یک حرکت — admin."""

    permission_classes = [IsMadadkarAdminUser]

    @extend_schema(
        operation_id="madadkar_admin_campaign_leaderboard",
        tags=[TAG_MADADKAR_ADMIN_ANALYTICS],
        summary="رتبه‌بندی بزرگ‌ترین مشارکت‌کنندگان — ادمین",
        description=(
            "نمایش top contributors یک حرکت بر اساس مجموع مبلغ پرداخت‌شده.\n\n"
            "**Query param:**\n"
            "- `top_n` (اختیاری، پیش‌فرض 10، حداکثر 100): تعداد نفرات برتر."
        ),
        parameters=[
            OpenApiParameter(
                name="top_n",
                type=OpenApiTypes.INT,
                location=OpenApiParameter.QUERY,
                description="تعداد نفرات برتر (پیش‌فرض ۱۰، حداکثر ۱۰۰)",
            ),
        ],
        responses={
            200: ADMIN_LEADERBOARD_RESPONSE,
            403: GENERIC_ERROR_RESPONSE,
            404: GENERIC_ERROR_RESPONSE,
        },
    )
    def get(self, request: Request, campaign_id: int) -> Response:
        campaign = selectors.get_admin_campaign_by_id(campaign_id=campaign_id)
        if campaign is None:
            return ErrorResponse(
                message="حرکتی با این شناسه یافت نشد.",
                status_code=status.HTTP_404_NOT_FOUND,
            )

        top_n_raw = request.query_params.get("top_n", "10")
        try:
            top_n = max(1, min(int(top_n_raw), 100))
        except (TypeError, ValueError):
            top_n = 10

        leaderboard = selectors.get_campaign_leaderboard(
            campaign=campaign,
            top_n=top_n,
        )

        serializer = AdminLeaderboardEntrySerializer(leaderboard, many=True)
        return SuccessResponse(
            data=serializer.data,
            message="رتبه‌بندی مشارکت‌کنندگان با موفقیت دریافت شد.",
        )


class MadadkarAdminCampaignAnalyticsView(APIView):
    """آمار تجمیعی یک حرکت — admin dashboard."""

    permission_classes = [IsMadadkarAdminUser]

    @extend_schema(
        operation_id="madadkar_admin_campaign_analytics",
        tags=[TAG_MADADKAR_ADMIN_ANALYTICS],
        summary="آمار تجمیعی حرکت — ادمین",
        description=(
            "دریافت آمار کامل یک حرکت برای دشبورد ادمین:\n"
            "- تعداد مشارکت‌ها به تفکیک وضعیت\n"
            "- مجموع مبلغ و سهم پرداخت‌شده\n"
            "- تعداد کاربران یکتای پرداخت‌کننده\n"
            "- درصد پیشرفت و سهم باقی‌مانده"
        ),
        responses={
            200: ADMIN_CAMPAIGN_ANALYTICS_RESPONSE,
            403: GENERIC_ERROR_RESPONSE,
            404: GENERIC_ERROR_RESPONSE,
        },
    )
    def get(self, request: Request, campaign_id: int) -> Response:
        campaign = selectors.get_admin_campaign_by_id(campaign_id=campaign_id)
        if campaign is None:
            return ErrorResponse(
                message="حرکتی با این شناسه یافت نشد.",
                status_code=status.HTTP_404_NOT_FOUND,
            )

        analytics = selectors.get_campaign_analytics(campaign=campaign)
        serializer = AdminCampaignAnalyticsSerializer(analytics)
        return SuccessResponse(
            data=serializer.data,
            message="آمار حرکت با موفقیت دریافت شد.",
        )


class MadadkarAdminCampaignExportView(APIView):
    """خروجی Excel از مشارکت‌کنندگان یک حرکت — admin."""

    permission_classes = [IsMadadkarAdminUser]

    @extend_schema(
        operation_id="madadkar_admin_campaign_export",
        tags=[TAG_MADADKAR_ADMIN_ANALYTICS],
        summary="خروجی Excel از پرداخت‌های حرکت — ادمین",
        description=(
            "تولید و دانلود فایل Excel حرفه‌ای شامل تمام پرداخت‌های موفق "
            "یک حرکت.\n\n"
            "**ویژگی‌های فایل:**\n"
            "- RTL alignment (راست به چپ)\n"
            "- Styled headers با رنگ‌بندی\n"
            "- ردیف summary در پایان (مجموع‌ها)\n"
            "- فرمت‌بندی اعداد و تاریخ‌ها\n"
            "- اطلاعات کامل: نام، ایمیل، موبایل، تعداد سهم، مبلغ، "
            "کد رهگیری، تاریخ"
        ),
        responses={
            (200, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"): {
                "type": "string",
                "format": "binary",
            },
            403: GENERIC_ERROR_RESPONSE,
            404: GENERIC_ERROR_RESPONSE,
        },
    )
    def get(self, request: Request, campaign_id: int) -> HttpResponse:
        campaign = selectors.get_admin_campaign_by_id(campaign_id=campaign_id)
        if campaign is None:
            return ErrorResponse(
                message="حرکتی با این شناسه یافت نشد.",
                status_code=status.HTTP_404_NOT_FOUND,
            )

        excel_buffer = generate_campaign_participants_excel(campaign=campaign)
        filename = build_excel_filename(campaign=campaign)

        # Audit — sync log (export یک عملیات حساس است)
        metadata = extract_audit_metadata(request)
        log_action(
            user_id=request.user.pk,
            action=audit_actions.MADADKAR_EXPORT_PARTICIPANTS,
            resource_type="madadkar_campaign",
            resource_id=str(campaign.pk),
            extra_data={
                "campaign_title": campaign.title,
                "filename": filename,
            },
            **metadata,
        )

        response = HttpResponse(
            excel_buffer.getvalue(),
            content_type=("application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"),
        )
        response["Content-Disposition"] = f'attachment; filename="{filename}"'
        response["Content-Length"] = str(excel_buffer.getbuffer().nbytes)
        return response


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


def _parse_int_query_param(
    *, request: Request, name: str, default: int, minimum: int, maximum: int
) -> int:
    """Parse bounded integer query params for intelligence endpoints."""
    raw_value = request.query_params.get(name, default)
    try:
        parsed = int(raw_value)
    except (TypeError, ValueError):
        parsed = default
    return max(minimum, min(parsed, maximum))


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


class MadadkarAdminCampaignDisbursableSummaryView(APIView):
    """Return disbursable amount summary for one campaign."""

    permission_classes = [IsMadadkarAdminUser]

    @extend_schema(
        operation_id="madadkar_admin_campaign_disbursable_summary",
        tags=[TAG_MADADKAR_ADMIN_ANALYTICS],
        summary="مانده قابل تخصیص حرکت — ادمین",
        responses={
            200: ADMIN_DISBURSABLE_SUMMARY_RESPONSE,
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
        summary = selectors.get_campaign_disbursable_summary(campaign=campaign)
        return SuccessResponse(
            data=CampaignDisbursableSummarySerializer(summary).data,
            message="مانده قابل تخصیص با موفقیت دریافت شد.",
        )


def _audit_disbursement_action(*, request: Request, disbursement, action: str) -> None:
    """Audit sensitive disbursement workflow actions."""
    metadata = extract_audit_metadata(request)
    log_action_async(
        user_id=request.user.pk,
        action=action,
        resource_type="madadkar_disbursement",
        resource_id=str(disbursement.pk),
        extra_data={
            "campaign_id": disbursement.campaign_id,
            "amount": disbursement.amount,
            "status": disbursement.status,
        },
        **metadata,
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

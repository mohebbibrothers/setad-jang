"""مشترکات views — constants/helpers که گروه‌های دامنه‌ای import می‌کنند.

با ابزار split_views در فاز ۱۱ از views.py جدا شد؛ منطق دست‌نخورده است(برشِ verbatim). facade در views.py همه را دوباره export می‌کند تا مسیرهایimport بیرونی (urls/tests) تغییر نکنند.
"""

from __future__ import annotations

import logging
from typing import Any
from urllib.parse import urlencode

from django.conf import settings
from drf_spectacular.utils import (
    OpenApiParameter,
    OpenApiTypes,
)
from rest_framework.request import Request

from apps.audit_logs.helpers import extract_audit_metadata
from apps.audit_logs.services import log_action_async
from apps.core.schemas import (
    build_error_response_serializer,
    build_paginated_success_response_serializer,
    build_success_response_serializer,
)

from . import selectors
from .models import Participation
from .serializers import (
    AdminCampaignAnalyticsSerializer,
    AdminLeaderboardEntrySerializer,
    AdminParticipantDetailSerializer,
    AdminPaymentListSerializer,
    CampaignAdminDetailSerializer,
    CampaignAdminListSerializer,
    CampaignDisbursableSummarySerializer,
    CampaignDisbursementSerializer,
    CampaignFinancialControlSummarySerializer,
    CampaignImageReadSerializer,
    CampaignIntelligenceSerializer,
    CampaignPublicDetailSerializer,
    CampaignPublicListSerializer,
    CampaignTransparencySerializer,
    DonationReceiptSerializer,
    DonationReceiptVerificationResultSerializer,
    FinancialAdjustmentSerializer,
    MadadkarFinancialControlSnapshotSerializer,
    MadadkarIntelligenceOverviewSerializer,
    MadadkarRiskSignalSerializer,
    ParticipationInitiatedResponseSerializer,
    ParticipationUserDetailSerializer,
    ParticipationUserListSerializer,
    PaymentReconciliationBatchSerializer,
    PaymentReconciliationItemSerializer,
    PaymentRefundSerializer,
    PaymentVerifyResultSerializer,
    SponsorAdminSerializer,
    SponsorPublicSerializer,
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


def _build_payment_result_url(*, authority: str, result: str) -> str:
    """
    ساخت URL صفحهٔ نتیجهٔ پرداخت روی فرانت — مقصد نهاییِ کاربر پس از callback.

    GET callbackِ مرورگر: ابتدا تراکنش در بک‌اند verify می‌شود و بعد کاربر
    با 302 به این صفحه می‌رود. خودِ صفحه دوباره (idempotent) با POST همان
    authority را تأیید می‌گیرد تا پارامترهای URL هرگز «منبع حقیقت» نباشند.
    """
    base = settings.MADADKAR_PAYMENT_RESULT_BASE_URL.rstrip("/")
    query = urlencode({"authority": authority, "result": result})
    return f"{base}/madadkar/paydone/?{query}"


def _normalized_callback_params(source: Any) -> dict[str, str]:
    """
    نرمال‌سازی caseِ پارامترهای callback درگاه‌ها.

    زرین‌پال v4 کاربر را با نام‌های capitalized برمی‌گرداند
    (`?Authority=…&Status=OK|NOK`) درحالی‌که سریالایزر ما lowercase است.
    نگاشت دقیقاً همین‌جا در مرز ورود انجام می‌شود تا contract داخلی یکدست
    بماند و callback واقعی درگاه هرگز به‌خاطر case خطای 400 نگیرد.

    مقادیرِ truthy اول برنده‌اند؛ ترتیب lowercase → Titlecase → UPPERCASE
    عمدی است تا اگر روزی هر دو شکل با هم آمدند، کلاینت‌های قدیمی (سندباکس،
    تست‌ها) اولویت داشته باشند.
    """
    out: dict[str, str] = {}
    for key in ("authority", "Authority", "AUTHORITY"):
        value = source.get(key)
        if value:
            out["authority"] = str(value)
            break
    for key in ("status", "Status", "STATUS"):
        value = source.get(key)
        if value:
            out["status"] = str(value)
            break
    return out


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

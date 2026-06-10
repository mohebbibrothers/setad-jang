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
from .serializers import (
    AdminCampaignAnalyticsSerializer,
    AdminLeaderboardEntrySerializer,
    AdminParticipantDetailSerializer,
    AdminPaymentListSerializer,
    CampaignAdminCreateSerializer,
    CampaignAdminDetailSerializer,
    CampaignAdminListSerializer,
    CampaignAdminUpdateSerializer,
    CampaignImageCreateSerializer,
    CampaignImageReadSerializer,
    CampaignPublicDetailSerializer,
    CampaignPublicListSerializer,
    ParticipationInitiatedResponseSerializer,
    ParticipationInitiateSerializer,
    ParticipationUserDetailSerializer,
    ParticipationUserListSerializer,
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
    InsufficientSharesError,
    InvalidShareCountError,
    PaymentAmountMismatchError,
    PaymentGatewayError,
    PaymentNotFoundError,
    SponsorInUseError,
    SponsorInvalidDataError,
)
from .throttles import (
    MadadkarBrowseAnonThrottle,
    MadadkarBrowseUserThrottle,
    MadadkarParticipateThrottle,
    MadadkarPaymentVerifyThrottle,
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
    OpenApiParameter(name="sponsor", type=OpenApiTypes.INT, location=OpenApiParameter.QUERY, description="شناسه مددکار"),
    OpenApiParameter(name="status", type=OpenApiTypes.STR, location=OpenApiParameter.QUERY, enum=["draft", "published", "completed", "closed"], description="وضعیت حرکت"),
    OpenApiParameter(name="is_visible", type=OpenApiTypes.BOOL, location=OpenApiParameter.QUERY),
    OpenApiParameter(name="is_active", type=OpenApiTypes.BOOL, location=OpenApiParameter.QUERY),
    OpenApiParameter(name="created_after", type=OpenApiTypes.DATETIME, location=OpenApiParameter.QUERY),
    OpenApiParameter(name="created_before", type=OpenApiTypes.DATETIME, location=OpenApiParameter.QUERY),
    OpenApiParameter(name="min_total_amount", type=OpenApiTypes.INT, location=OpenApiParameter.QUERY),
    OpenApiParameter(name="max_total_amount", type=OpenApiTypes.INT, location=OpenApiParameter.QUERY),
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
        mobile = (
            getattr(user, "phone_number", "")
            or getattr(user, "mobile", "")
            or ""
        )

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
        queryset = selectors.get_public_sponsors_queryset()
        paginator = StandardPagination()
        page = paginator.paginate_queryset(queryset, request, view=self)

        if page is not None:
            serializer = SponsorPublicSerializer(page, many=True)
            return paginator.get_paginated_response(
                serializer.data,
                message="لیست مددکاران با موفقیت دریافت شد.",
            )

        serializer = SponsorPublicSerializer(queryset, many=True)
        return SuccessResponse(
            data=serializer.data,
            message="لیست مددکاران با موفقیت دریافت شد.",
        )


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
        sponsor = selectors.get_sponsor_by_slug_public(slug=slug)
        if sponsor is None:
            return ErrorResponse(
                message="مددکاری با این مشخصات یافت نشد.",
                status_code=status.HTTP_404_NOT_FOUND,
            )
        serializer = SponsorPublicSerializer(sponsor)
        return SuccessResponse(
            data=serializer.data,
            message="جزئیات مددکار با موفقیت دریافت شد.",
        )


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
        queryset = selectors.get_public_campaigns_queryset()
        filterset = CampaignPublicFilter(request.query_params, queryset=queryset)
        if filterset.is_valid():
            queryset = filterset.qs

        paginator = StandardPagination()
        page = paginator.paginate_queryset(queryset, request, view=self)

        if page is not None:
            serializer = CampaignPublicListSerializer(
                page, many=True, context={"request": request},
            )
            return paginator.get_paginated_response(
                serializer.data,
                message="لیست حرکت‌ها با موفقیت دریافت شد.",
            )

        serializer = CampaignPublicListSerializer(
            queryset, many=True, context={"request": request},
        )
        return SuccessResponse(
            data=serializer.data,
            message="لیست حرکت‌ها با موفقیت دریافت شد.",
        )


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
        campaign = selectors.get_public_campaign_by_slug(slug=slug)
        if campaign is None:
            return ErrorResponse(
                message="حرکتی با این مشخصات یافت نشد.",
                status_code=status.HTTP_404_NOT_FOUND,
            )
        serializer = CampaignPublicDetailSerializer(
            campaign, context={"request": request},
        )
        return SuccessResponse(
            data=serializer.data,
            message="جزئیات حرکت با موفقیت دریافت شد.",
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
                "پرداخت با موفقیت تأیید شد."
                if is_success
                else "پرداخت تأیید نشد یا ناموفق بود."
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
        responses={201: ADMIN_SPONSOR_DETAIL_RESPONSE, 400: GENERIC_ERROR_RESPONSE, 403: GENERIC_ERROR_RESPONSE},
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
        responses={200: ADMIN_SPONSOR_DETAIL_RESPONSE, 403: GENERIC_ERROR_RESPONSE, 404: GENERIC_ERROR_RESPONSE},
    ),
    patch=extend_schema(
        operation_id="madadkar_admin_sponsor_update",
        tags=[TAG_MADADKAR_ADMIN_SPONSOR],
        summary="ویرایش مددکار — ادمین",
        request=SponsorUpdateSerializer,
        responses={200: ADMIN_SPONSOR_DETAIL_RESPONSE, 400: GENERIC_ERROR_RESPONSE, 403: GENERIC_ERROR_RESPONSE, 404: GENERIC_ERROR_RESPONSE},
    ),
    delete=extend_schema(
        operation_id="madadkar_admin_sponsor_delete",
        tags=[TAG_MADADKAR_ADMIN_SPONSOR],
        summary="حذف نرم مددکار — ادمین",
        responses={200: EMPTY_SUCCESS_RESPONSE, 400: GENERIC_ERROR_RESPONSE, 403: GENERIC_ERROR_RESPONSE, 404: GENERIC_ERROR_RESPONSE},
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
                sponsor=sponsor, **serializer.validated_data,
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
        responses={201: ADMIN_CAMPAIGN_DETAIL_RESPONSE, 400: GENERIC_ERROR_RESPONSE, 403: GENERIC_ERROR_RESPONSE, 404: GENERIC_ERROR_RESPONSE},
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
        responses={200: ADMIN_CAMPAIGN_DETAIL_RESPONSE, 403: GENERIC_ERROR_RESPONSE, 404: GENERIC_ERROR_RESPONSE},
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
        responses={200: ADMIN_CAMPAIGN_DETAIL_RESPONSE, 400: GENERIC_ERROR_RESPONSE, 403: GENERIC_ERROR_RESPONSE, 404: GENERIC_ERROR_RESPONSE},
    ),
    delete=extend_schema(
        operation_id="madadkar_admin_campaign_delete",
        tags=[TAG_MADADKAR_ADMIN_CAMPAIGN],
        summary="حذف نرم حرکت — ادمین",
        description="فقط حرکت‌های در وضعیت DRAFT قابل حذف هستند.",
        responses={200: EMPTY_SUCCESS_RESPONSE, 400: GENERIC_ERROR_RESPONSE, 403: GENERIC_ERROR_RESPONSE, 404: GENERIC_ERROR_RESPONSE},
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
            data=request.data, partial=True, context={"campaign": campaign},
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
        description=(
            "انتقال حرکت از PUBLISHED به CLOSED. "
            "از این پس امکان مشارکت جدید وجود ندارد."
        ),
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
            "display_order", "created_at",
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
            campaign=campaign, **serializer.validated_data,
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
            content_type=(
                "application/vnd.openxmlformats-officedocument."
                "spreadsheetml.sheet"
            ),
        )
        response["Content-Disposition"] = f'attachment; filename="{filename}"'
        response["Content-Length"] = str(excel_buffer.getbuffer().nbytes)
        return response


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

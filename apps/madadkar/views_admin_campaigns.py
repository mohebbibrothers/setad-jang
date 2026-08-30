"""گروه دامنه‌ای `views_admin_campaigns` از views — فاز ۱۱ (تفکیک P3-16).

کلاس‌ها عیناً منتقل شده‌اند؛ مشترکات از views_common؛ نامِ عمومیِ این گروه‌ها را فقط از facade (apps.*.views) یا همین ماژول import کنید.
"""

from __future__ import annotations

from django.http import HttpResponse
from drf_spectacular.utils import (
    OpenApiParameter,
    OpenApiTypes,
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
from .export import build_excel_filename, generate_campaign_participants_excel
from .filters import (
    CampaignAdminFilter,
)
from .models import Sponsor
from .permissions import (
    IsMadadkarAdminUser,
)
from .serializers import (
    AdminCampaignAnalyticsSerializer,
    AdminLeaderboardEntrySerializer,
    AdminParticipantDetailSerializer,
    CampaignAdminCreateSerializer,
    CampaignAdminDetailSerializer,
    CampaignAdminListSerializer,
    CampaignAdminUpdateSerializer,
    CampaignDisbursableSummarySerializer,
    CampaignImageCreateSerializer,
    CampaignImageReadSerializer,
)
from .services import (
    CampaignFieldLockedError,
    CampaignInvalidDataError,
    CampaignInvalidStateError,
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

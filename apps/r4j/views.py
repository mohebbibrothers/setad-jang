"""
Views اپ R4J — Reward for Justice.

ساختار:
- Public: لیست و جزئیات criminals منتشرشده
- Admin Criminals: CRUD کامل + publish/unpublish
- Admin Nested: phones, socials, photos, attachments, aliases, field_visibility
- User Reports: submit، لیست mine، جزئیات mine، cancel request
- Admin Reports: لیست همه، جزئیات، review، cancel approve/reject
- User Bounties: set/update، لیست mine، cancel request
- Admin Bounties: لیست همه، جزئیات، cancel approve/reject

اصول طراحی:
- View هیچ business logic مستقیمی ندارد — همه از طریق service layer.
- Audit log برای تمام mutationهای مهم ثبت می‌شود.
- response envelope و استانداردهای Swagger پروژه به‌طور کامل رعایت می‌شوند.
- nested viewها از یک parent lookup مشترک استفاده می‌کنند تا 404 consistency
  حفظ شود.
- bounty endpointهای حساس از permission و throttle مناسب استفاده می‌کنند.
"""

from __future__ import annotations

import hashlib

from django.contrib.auth import get_user_model
from drf_spectacular.utils import (
    OpenApiParameter,
    OpenApiTypes,
    extend_schema,
    extend_schema_view,
)
from rest_framework import status
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.permissions import AllowAny, IsAuthenticated
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
from .filters import (
    R4JBountyAdminFilter,
    R4JBountyUserFilter,
    R4JCriminalAdminFilter,
    R4JCriminalPublicFilter,
    R4JReportAdminFilter,
    R4JReportUserFilter,
)
from .permissions import IsFullyVerifiedUser, IsR4JAdminUser
from .serializers import (
    R4JAdminAttachmentSerializer,
    R4JAdminBountyDetailSerializer,
    R4JAdminBountyListSerializer,
    R4JAdminCriminalDetailSerializer,
    R4JAdminCriminalListSerializer,
    R4JAdminFieldVisibilitySerializer,
    R4JAdminPhoneSerializer,
    R4JAdminPhotoSerializer,
    R4JAdminReportDetailSerializer,
    R4JAdminReportListSerializer,
    R4JAdminSocialSerializer,
    R4JAliasCreateSerializer,
    R4JAliasSerializer,
    R4JAttachmentCreateSerializer,
    R4JBountyCancelActionSerializer,
    R4JBountySetSerializer,
    R4JCaseAssignSerializer,
    R4JCaseCreateFromReportSerializer,
    R4JCaseEventSerializer,
    R4JCaseEvidenceRequestSerializer,
    R4JCaseNoteRequiredSerializer,
    R4JCaseOperationsOverviewSerializer,
    R4JCasePrioritySerializer,
    R4JCaseTriageSerializer,
    R4JCriminalCreateSerializer,
    R4JCriminalUpdateSerializer,
    R4JEvidenceCustodyEventSerializer,
    R4JEvidenceCustodyReviewSerializer,
    R4JFieldVisibilityUpsertSerializer,
    R4JInvestigationCaseDetailSerializer,
    R4JInvestigationCaseListSerializer,
    R4JPhoneCreateSerializer,
    R4JPhoneUpdateSerializer,
    R4JPhotoCreateSerializer,
    R4JPublicCriminalDetailSerializer,
    R4JPublicCriminalListSerializer,
    R4JReportCancelActionSerializer,
    R4JReportReviewSerializer,
    R4JReportSubmitSerializer,
    R4JSocialCreateSerializer,
    R4JSocialUpdateSerializer,
    R4JUserBountySerializer,
    R4JUserReportDetailSerializer,
    R4JUserReportListSerializer,
)
from .services import (
    BountyNotCancelable,
    BountyNotInCancelRequested,
    BountyUpdateNotAllowed,
    CriminalAlreadyPublished,
    CriminalAlreadyUnpublished,
    InvalidBountyAmount,
    InvalidReportableField,
    InvestigationCaseAlreadyExists,
    R4JServiceError,
    ReportNotCancelable,
    ReportNotInCancelRequested,
    ReportNotReviewable,
)
from .throttles import (
    R4JBountySetThrottle,
    R4JBrowseAnonThrottle,
    R4JBrowseUserThrottle,
    R4JReportCreateThrottle,
)

# ============================================================
# Tag Constants
# ============================================================

TAG_R4J_PUBLIC = "جایزه‌ای برای عدالت — عمومی"
TAG_R4J_USER = "جایزه‌ای برای عدالت — کاربر"
TAG_R4J_BOUNTY = "جایزه‌ای برای عدالت — تعیین جایزه"
TAG_R4J_ADMIN = "جایزه‌ای برای عدالت — مدیریت"



def _build_filters_signature(request: Request) -> str:
    """Build a stable short signature for cacheable public list filters."""
    relevant_keys = sorted(k for k in request.query_params.keys() if k not in {"page", "page_size"})
    if not relevant_keys:
        return "no_filters"

    parts = [f"{key}={request.query_params.get(key, '')}" for key in relevant_keys]
    raw = "|".join(parts)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]

# ============================================================
# Swagger Response Schemas
# ============================================================

GENERIC_ERROR_RESPONSE = build_error_response_serializer(
    name="R4JGenericErrorResponse",
)
EMPTY_SUCCESS_RESPONSE = build_success_response_serializer(
    name="R4JEmptySuccessResponse",
)

# Public
PUBLIC_LIST_RESPONSE = build_paginated_success_response_serializer(
    name="R4JPublicCriminalListResponse",
    item_serializer=R4JPublicCriminalListSerializer,
)
PUBLIC_DETAIL_RESPONSE = build_success_response_serializer(
    name="R4JPublicCriminalDetailResponse",
    data_serializer=R4JPublicCriminalDetailSerializer,
)

# Admin — Criminal
ADMIN_LIST_RESPONSE = build_paginated_success_response_serializer(
    name="R4JAdminCriminalListResponse",
    item_serializer=R4JAdminCriminalListSerializer,
)
ADMIN_DETAIL_RESPONSE = build_success_response_serializer(
    name="R4JAdminCriminalDetailResponse",
    data_serializer=R4JAdminCriminalDetailSerializer,
)

# Admin — Nested
ADMIN_PHONE_RESPONSE = build_success_response_serializer(
    name="R4JAdminPhoneResponse",
    data_serializer=R4JAdminPhoneSerializer,
)
ADMIN_PHONE_LIST_RESPONSE = build_success_response_serializer(
    name="R4JAdminPhoneListResponse",
    data_serializer=R4JAdminPhoneSerializer,
    many=True,
)
ADMIN_SOCIAL_RESPONSE = build_success_response_serializer(
    name="R4JAdminSocialResponse",
    data_serializer=R4JAdminSocialSerializer,
)
ADMIN_SOCIAL_LIST_RESPONSE = build_success_response_serializer(
    name="R4JAdminSocialListResponse",
    data_serializer=R4JAdminSocialSerializer,
    many=True,
)
ADMIN_PHOTO_RESPONSE = build_success_response_serializer(
    name="R4JAdminPhotoResponse",
    data_serializer=R4JAdminPhotoSerializer,
)
ADMIN_PHOTO_LIST_RESPONSE = build_success_response_serializer(
    name="R4JAdminPhotoListResponse",
    data_serializer=R4JAdminPhotoSerializer,
    many=True,
)
ADMIN_ATTACHMENT_RESPONSE = build_success_response_serializer(
    name="R4JAdminAttachmentResponse",
    data_serializer=R4JAdminAttachmentSerializer,
)
ADMIN_ATTACHMENT_LIST_RESPONSE = build_success_response_serializer(
    name="R4JAdminAttachmentListResponse",
    data_serializer=R4JAdminAttachmentSerializer,
    many=True,
)
ADMIN_CUSTODY_EVENT_RESPONSE = build_success_response_serializer(
    name="R4JAdminCustodyEventResponse",
    data_serializer=R4JEvidenceCustodyEventSerializer,
)
ADMIN_CUSTODY_EVENT_LIST_RESPONSE = build_paginated_success_response_serializer(
    name="R4JAdminCustodyEventListResponse",
    item_serializer=R4JEvidenceCustodyEventSerializer,
)
ADMIN_ALIAS_RESPONSE = build_success_response_serializer(
    name="R4JAdminAliasResponse",
    data_serializer=R4JAliasSerializer,
)
ADMIN_ALIAS_LIST_RESPONSE = build_success_response_serializer(
    name="R4JAdminAliasListResponse",
    data_serializer=R4JAliasSerializer,
    many=True,
)
ADMIN_VISIBILITY_LIST_RESPONSE = build_success_response_serializer(
    name="R4JAdminVisibilityListResponse",
    data_serializer=R4JAdminFieldVisibilitySerializer,
    many=True,
)
ADMIN_VISIBILITY_RESPONSE = build_success_response_serializer(
    name="R4JAdminVisibilityResponse",
    data_serializer=R4JAdminFieldVisibilitySerializer,
)

# Reports — User
USER_REPORT_LIST_RESPONSE = build_paginated_success_response_serializer(
    name="R4JUserReportListResponse",
    item_serializer=R4JUserReportListSerializer,
)
USER_REPORT_DETAIL_RESPONSE = build_success_response_serializer(
    name="R4JUserReportDetailResponse",
    data_serializer=R4JUserReportDetailSerializer,
)

# Reports — Admin
ADMIN_REPORT_LIST_RESPONSE = build_paginated_success_response_serializer(
    name="R4JAdminReportListResponse",
    item_serializer=R4JAdminReportListSerializer,
)
ADMIN_REPORT_DETAIL_RESPONSE = build_success_response_serializer(
    name="R4JAdminReportDetailResponse",
    data_serializer=R4JAdminReportDetailSerializer,
)

# Bounties — User
USER_BOUNTY_LIST_RESPONSE = build_paginated_success_response_serializer(
    name="R4JUserBountyListResponse",
    item_serializer=R4JUserBountySerializer,
)
USER_BOUNTY_DETAIL_RESPONSE = build_success_response_serializer(
    name="R4JUserBountyDetailResponse",
    data_serializer=R4JUserBountySerializer,
)

# Bounties — Admin
ADMIN_BOUNTY_LIST_RESPONSE = build_paginated_success_response_serializer(
    name="R4JAdminBountyListResponse",
    item_serializer=R4JAdminBountyListSerializer,
)
ADMIN_BOUNTY_DETAIL_RESPONSE = build_success_response_serializer(
    name="R4JAdminBountyDetailResponse",
    data_serializer=R4JAdminBountyDetailSerializer,
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

PUBLIC_LIST_FILTER_PARAMS = [
    *LIST_PAGINATION_PARAMS,
    OpenApiParameter(
        name="search",
        type=OpenApiTypes.STR,
        location=OpenApiParameter.QUERY,
        description="جستجو در نام، نام خانوادگی، slug و اسامی مستعار",
    ),
    OpenApiParameter(
        name="country",
        type=OpenApiTypes.STR,
        location=OpenApiParameter.QUERY,
        description="فیلتر بر اساس کشور",
    ),
    OpenApiParameter(
        name="province",
        type=OpenApiTypes.STR,
        location=OpenApiParameter.QUERY,
        description="فیلتر بر اساس استان",
    ),
    OpenApiParameter(
        name="city",
        type=OpenApiTypes.STR,
        location=OpenApiParameter.QUERY,
        description="فیلتر بر اساس شهر",
    ),
    OpenApiParameter(
        name="gender",
        type=OpenApiTypes.STR,
        location=OpenApiParameter.QUERY,
        enum=["male", "female", "unknown"],
        description="فیلتر بر اساس جنسیت",
    ),
]

ADMIN_LIST_FILTER_PARAMS = [
    *PUBLIC_LIST_FILTER_PARAMS,
    OpenApiParameter(
        name="is_published",
        type=OpenApiTypes.BOOL,
        location=OpenApiParameter.QUERY,
        description="فیلتر بر اساس انتشار",
    ),
    OpenApiParameter(
        name="is_active",
        type=OpenApiTypes.BOOL,
        location=OpenApiParameter.QUERY,
        description="فیلتر بر اساس فعال بودن",
    ),
]

ADMIN_REPORT_FILTER_PARAMS = [
    *LIST_PAGINATION_PARAMS,
    OpenApiParameter(
        name="status",
        type=OpenApiTypes.STR,
        location=OpenApiParameter.QUERY,
        description="فیلتر بر اساس وضعیت گزارش",
    ),
    OpenApiParameter(
        name="criminal_id",
        type=OpenApiTypes.INT,
        location=OpenApiParameter.QUERY,
        description="فیلتر بر اساس شناسه مجرم",
    ),
    OpenApiParameter(
        name="submitted_by_id",
        type=OpenApiTypes.INT,
        location=OpenApiParameter.QUERY,
        description="فیلتر بر اساس شناسه گزارش‌دهنده",
    ),
    OpenApiParameter(
        name="created_after",
        type=OpenApiTypes.DATETIME,
        location=OpenApiParameter.QUERY,
        description="گزارشات بعد از این تاریخ",
    ),
    OpenApiParameter(
        name="created_before",
        type=OpenApiTypes.DATETIME,
        location=OpenApiParameter.QUERY,
        description="گزارشات قبل از این تاریخ",
    ),
]

USER_REPORT_FILTER_PARAMS = [
    *LIST_PAGINATION_PARAMS,
    OpenApiParameter(
        name="status",
        type=OpenApiTypes.STR,
        location=OpenApiParameter.QUERY,
        description="فیلتر بر اساس وضعیت گزارش",
    ),
]

USER_BOUNTY_FILTER_PARAMS = [
    *LIST_PAGINATION_PARAMS,
    OpenApiParameter(
        name="status",
        type=OpenApiTypes.STR,
        location=OpenApiParameter.QUERY,
        description="فیلتر بر اساس وضعیت جایزه",
    ),
    OpenApiParameter(
        name="criminal_id",
        type=OpenApiTypes.INT,
        location=OpenApiParameter.QUERY,
        description="فیلتر بر اساس شناسه مجرم",
    ),
    OpenApiParameter(
        name="created_after",
        type=OpenApiTypes.DATETIME,
        location=OpenApiParameter.QUERY,
        description="جوایز ثبت‌شده بعد از این تاریخ",
    ),
    OpenApiParameter(
        name="created_before",
        type=OpenApiTypes.DATETIME,
        location=OpenApiParameter.QUERY,
        description="جوایز ثبت‌شده قبل از این تاریخ",
    ),
]

ADMIN_BOUNTY_FILTER_PARAMS = [
    *LIST_PAGINATION_PARAMS,
    OpenApiParameter(
        name="status",
        type=OpenApiTypes.STR,
        location=OpenApiParameter.QUERY,
        description="فیلتر بر اساس وضعیت جایزه",
    ),
    OpenApiParameter(
        name="criminal_id",
        type=OpenApiTypes.INT,
        location=OpenApiParameter.QUERY,
        description="فیلتر بر اساس شناسه مجرم",
    ),
    OpenApiParameter(
        name="user_id",
        type=OpenApiTypes.INT,
        location=OpenApiParameter.QUERY,
        description="فیلتر بر اساس شناسه کاربر تعیین‌کننده جایزه",
    ),
    OpenApiParameter(
        name="created_after",
        type=OpenApiTypes.DATETIME,
        location=OpenApiParameter.QUERY,
        description="جوایز ثبت‌شده بعد از این تاریخ",
    ),
    OpenApiParameter(
        name="created_before",
        type=OpenApiTypes.DATETIME,
        location=OpenApiParameter.QUERY,
        description="جوایز ثبت‌شده قبل از این تاریخ",
    ),
]


# ============================================================
# Public Views
# ============================================================


@extend_schema_view(
    get=extend_schema(
        operation_id="r4j_public_criminals_list",
        tags=[TAG_R4J_PUBLIC],
        summary="لیست مجرمین منتشرشده",
        description=(
            "دریافت لیست مجرمین منتشرشده برای نمایش عمومی.\n\n"
            "فقط رکوردهای فعال و منتشرشده در پاسخ هستند. "
            "نتایج paginated و قابل فیلتر می‌باشند."
        ),
        parameters=PUBLIC_LIST_FILTER_PARAMS,
        responses={200: PUBLIC_LIST_RESPONSE},
    ),
)
class R4JPublicCriminalListView(APIView):
    """لیست عمومی مجرمین منتشرشده."""

    permission_classes = [AllowAny]
    throttle_classes = [R4JBrowseAnonThrottle, R4JBrowseUserThrottle]

    def get(self, request: Request) -> Response:
        filters_signature = _build_filters_signature(request)
        page_number = request.query_params.get("page", "1")
        page_size = request.query_params.get("page_size", str(StandardPagination.page_size))
        ordering = request.query_params.get("ordering", "")

        cached_payload = selectors.get_public_criminals_page_cached(
            page=page_number,
            page_size=page_size,
            ordering=ordering,
            filters_signature=filters_signature,
        )
        if cached_payload is not None:
            return SuccessResponse(data=cached_payload)

        queryset = selectors.get_public_criminals_queryset()
        filterset = R4JCriminalPublicFilter(request.query_params, queryset=queryset)
        if filterset.is_valid():
            queryset = filterset.qs

        paginator = StandardPagination()
        page = paginator.paginate_queryset(queryset, request, view=self)

        if page is not None:
            serializer = R4JPublicCriminalListSerializer(
                page,
                many=True,
                context={"request": request},
            )
            response = paginator.get_paginated_response(
                serializer.data,
                message="لیست مجرمین با موفقیت دریافت شد.",
            )
            selectors.set_public_criminals_page_cache(
                page=page_number,
                page_size=page_size,
                ordering=ordering,
                filters_signature=filters_signature,
                payload=response.data["data"],
            )
            return response

        serializer = R4JPublicCriminalListSerializer(
            queryset,
            many=True,
            context={"request": request},
        )
        return SuccessResponse(
            data=serializer.data,
            message="لیست مجرمین با موفقیت دریافت شد.",
        )


@extend_schema_view(
    get=extend_schema(
        operation_id="r4j_public_criminal_retrieve",
        tags=[TAG_R4J_PUBLIC],
        summary="جزئیات یک مجرم منتشرشده",
        description=(
            "دریافت جزئیات یک مجرم با استفاده از id یا slug.\n\n"
            "فیلدهای حساس بر اساس تنظیمات per-criminal visibility "
            "نمایش داده یا مخفی می‌شوند."
        ),
        responses={
            200: PUBLIC_DETAIL_RESPONSE,
            404: GENERIC_ERROR_RESPONSE,
        },
    ),
)
class R4JPublicCriminalDetailView(APIView):
    """جزئیات یک مجرم — public."""

    permission_classes = [AllowAny]
    throttle_classes = [R4JBrowseAnonThrottle, R4JBrowseUserThrottle]

    def get(self, request: Request, lookup: str) -> Response:
        criminal = selectors.get_public_criminal_detail_cached(lookup=lookup)
        if criminal is None:
            return ErrorResponse(
                message="مجرمی با این مشخصات یافت نشد.",
                status_code=status.HTTP_404_NOT_FOUND,
            )
        serializer = R4JPublicCriminalDetailSerializer(
            criminal,
            context={"request": request},
        )
        return SuccessResponse(
            data=serializer.data,
            message="جزئیات با موفقیت دریافت شد.",
        )


# ============================================================
# Admin — Criminals CRUD
# ============================================================


@extend_schema_view(
    get=extend_schema(
        operation_id="r4j_admin_criminals_list",
        tags=[TAG_R4J_ADMIN],
        summary="لیست مجرمین — ادمین",
        description="لیست تمام مجرمین شامل draft و soft-deleted.",
        parameters=ADMIN_LIST_FILTER_PARAMS,
        responses={
            200: ADMIN_LIST_RESPONSE,
            403: GENERIC_ERROR_RESPONSE,
        },
    ),
    post=extend_schema(
        operation_id="r4j_admin_criminals_create",
        tags=[TAG_R4J_ADMIN],
        summary="ساخت پروفایل مجرم جدید — ادمین",
        description=(
            "ساخت پروفایل جدید. همیشه draft ساخته می‌شود و "
            "باید با endpoint publish منتشر شود."
        ),
        request=R4JCriminalCreateSerializer,
        responses={
            201: ADMIN_DETAIL_RESPONSE,
            400: GENERIC_ERROR_RESPONSE,
            403: GENERIC_ERROR_RESPONSE,
        },
    ),
)
class R4JAdminCriminalListCreateView(APIView):
    """list + create criminals — admin."""

    permission_classes = [IsR4JAdminUser]
    pagination_class = StandardPagination

    def get(self, request: Request) -> Response:
        queryset = selectors.get_admin_criminals_queryset()
        filterset = R4JCriminalAdminFilter(request.query_params, queryset=queryset)
        if filterset.is_valid():
            queryset = filterset.qs

        paginator = self.pagination_class()
        page = paginator.paginate_queryset(queryset, request, view=self)

        if page is not None:
            serializer = R4JAdminCriminalListSerializer(page, many=True)
            return paginator.get_paginated_response(
                serializer.data,
                message="لیست مجرمین با موفقیت دریافت شد.",
            )

        serializer = R4JAdminCriminalListSerializer(queryset, many=True)
        return SuccessResponse(
            data=serializer.data,
            message="لیست مجرمین با موفقیت دریافت شد.",
        )

    def post(self, request: Request) -> Response:
        serializer = R4JCriminalCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        criminal = services.create_criminal(
            created_by=request.user,
            **serializer.validated_data,
        )

        metadata = extract_audit_metadata(request)
        log_action_async(
            user_id=request.user.pk,
            action=audit_actions.R4J_CRIMINAL_CREATED,
            resource_type="r4j_criminal",
            resource_id=str(criminal.pk),
            extra_data={"slug": criminal.slug},
            **metadata,
        )

        return CreatedResponse(
            data=R4JAdminCriminalDetailSerializer(criminal).data,
            message="پروفایل مجرم با موفقیت ساخته شد.",
        )


@extend_schema_view(
    get=extend_schema(
        operation_id="r4j_admin_criminal_retrieve",
        tags=[TAG_R4J_ADMIN],
        summary="جزئیات مجرم — ادمین",
        responses={
            200: ADMIN_DETAIL_RESPONSE,
            403: GENERIC_ERROR_RESPONSE,
            404: GENERIC_ERROR_RESPONSE,
        },
    ),
    patch=extend_schema(
        operation_id="r4j_admin_criminal_update",
        tags=[TAG_R4J_ADMIN],
        summary="ویرایش مجرم — ادمین",
        request=R4JCriminalUpdateSerializer,
        responses={
            200: ADMIN_DETAIL_RESPONSE,
            400: GENERIC_ERROR_RESPONSE,
            403: GENERIC_ERROR_RESPONSE,
            404: GENERIC_ERROR_RESPONSE,
        },
    ),
    delete=extend_schema(
        operation_id="r4j_admin_criminal_delete",
        tags=[TAG_R4J_ADMIN],
        summary="حذف نرم مجرم — ادمین",
        description="غیرفعال (soft delete) و خودکار unpublish می‌شود.",
        responses={
            200: EMPTY_SUCCESS_RESPONSE,
            403: GENERIC_ERROR_RESPONSE,
            404: GENERIC_ERROR_RESPONSE,
        },
    ),
)
class R4JAdminCriminalDetailView(APIView):
    """retrieve + update + delete — admin."""

    permission_classes = [IsR4JAdminUser]

    def get(self, request: Request, criminal_id: int) -> Response:
        criminal = selectors.get_admin_criminal_detail(lookup=criminal_id)
        if criminal is None:
            return ErrorResponse(
                message="مجرمی با این شناسه یافت نشد.",
                status_code=status.HTTP_404_NOT_FOUND,
            )
        return SuccessResponse(
            data=R4JAdminCriminalDetailSerializer(criminal).data,
            message="جزئیات با موفقیت دریافت شد.",
        )

    def patch(self, request: Request, criminal_id: int) -> Response:
        criminal = selectors.get_admin_criminal_by_id(criminal_id)
        if criminal is None:
            return ErrorResponse(
                message="مجرمی با این شناسه یافت نشد.",
                status_code=status.HTTP_404_NOT_FOUND,
            )
        serializer = R4JCriminalUpdateSerializer(data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)

        criminal = services.update_criminal(
            criminal=criminal,
            **serializer.validated_data,
        )

        metadata = extract_audit_metadata(request)
        log_action_async(
            user_id=request.user.pk,
            action=audit_actions.R4J_CRIMINAL_UPDATED,
            resource_type="r4j_criminal",
            resource_id=str(criminal.pk),
            changes={k: v for k, v in serializer.validated_data.items()},
            **metadata,
        )

        return SuccessResponse(
            data=R4JAdminCriminalDetailSerializer(criminal).data,
            message="پروفایل با موفقیت بروزرسانی شد.",
        )

    def delete(self, request: Request, criminal_id: int) -> Response:
        criminal = selectors.get_admin_criminal_by_id(criminal_id)
        if criminal is None:
            return ErrorResponse(
                message="مجرمی با این شناسه یافت نشد.",
                status_code=status.HTTP_404_NOT_FOUND,
            )
        services.soft_delete_criminal(criminal=criminal)

        metadata = extract_audit_metadata(request)
        log_action(
            user_id=request.user.pk,
            action=audit_actions.R4J_CRIMINAL_DELETED,
            resource_type="r4j_criminal",
            resource_id=str(criminal_id),
            extra_data={"slug": criminal.slug},
            **metadata,
        )

        return DeletedResponse(message="پروفایل با موفقیت غیرفعال شد.")


# ============================================================
# Admin — Publish / Unpublish
# ============================================================


class R4JAdminCriminalPublishView(APIView):
    """انتشار یک مجرم — admin."""

    permission_classes = [IsR4JAdminUser]

    @extend_schema(
        operation_id="r4j_admin_criminal_publish",
        tags=[TAG_R4J_ADMIN],
        summary="انتشار مجرم — ادمین",
        request=None,
        responses={
            200: ADMIN_DETAIL_RESPONSE,
            400: GENERIC_ERROR_RESPONSE,
            403: GENERIC_ERROR_RESPONSE,
            404: GENERIC_ERROR_RESPONSE,
        },
    )
    def post(self, request: Request, criminal_id: int) -> Response:
        criminal = selectors.get_admin_criminal_by_id(criminal_id)
        if criminal is None:
            return ErrorResponse(
                message="مجرمی با این شناسه یافت نشد.",
                status_code=status.HTTP_404_NOT_FOUND,
            )
        try:
            criminal = services.publish_criminal(criminal=criminal)
        except CriminalAlreadyPublished as exc:
            return ErrorResponse(message=str(exc))

        metadata = extract_audit_metadata(request)
        log_action_async(
            user_id=request.user.pk,
            action=audit_actions.R4J_CRIMINAL_PUBLISHED,
            resource_type="r4j_criminal",
            resource_id=str(criminal.pk),
            **metadata,
        )

        return SuccessResponse(
            data=R4JAdminCriminalDetailSerializer(criminal).data,
            message="پروفایل با موفقیت منتشر شد.",
        )


class R4JAdminCriminalUnpublishView(APIView):
    """خروج از انتشار یک مجرم — admin."""

    permission_classes = [IsR4JAdminUser]

    @extend_schema(
        operation_id="r4j_admin_criminal_unpublish",
        tags=[TAG_R4J_ADMIN],
        summary="خروج از انتشار مجرم — ادمین",
        request=None,
        responses={
            200: ADMIN_DETAIL_RESPONSE,
            400: GENERIC_ERROR_RESPONSE,
            403: GENERIC_ERROR_RESPONSE,
            404: GENERIC_ERROR_RESPONSE,
        },
    )
    def post(self, request: Request, criminal_id: int) -> Response:
        criminal = selectors.get_admin_criminal_by_id(criminal_id)
        if criminal is None:
            return ErrorResponse(
                message="مجرمی با این شناسه یافت نشد.",
                status_code=status.HTTP_404_NOT_FOUND,
            )
        try:
            criminal = services.unpublish_criminal(criminal=criminal)
        except CriminalAlreadyUnpublished as exc:
            return ErrorResponse(message=str(exc))

        metadata = extract_audit_metadata(request)
        log_action_async(
            user_id=request.user.pk,
            action=audit_actions.R4J_CRIMINAL_UNPUBLISHED,
            resource_type="r4j_criminal",
            resource_id=str(criminal.pk),
            **metadata,
        )

        return SuccessResponse(
            data=R4JAdminCriminalDetailSerializer(criminal).data,
            message="انتشار پروفایل با موفقیت لغو شد.",
        )


# ============================================================
# Admin — Nested: Aliases
# ============================================================


class R4JAdminAliasListCreateView(APIView):
    """list + create aliases — admin."""

    permission_classes = [IsR4JAdminUser]

    @extend_schema(
        operation_id="r4j_admin_aliases_list",
        tags=[TAG_R4J_ADMIN],
        summary="لیست اسامی مستعار",
        responses={200: ADMIN_ALIAS_LIST_RESPONSE, 404: GENERIC_ERROR_RESPONSE},
    )
    def get(self, request: Request, criminal_id: int) -> Response:
        criminal = selectors.get_admin_criminal_by_id(criminal_id)
        if criminal is None:
            return ErrorResponse(
                message="مجرمی با این شناسه یافت نشد.",
                status_code=status.HTTP_404_NOT_FOUND,
            )
        aliases = selectors.get_admin_aliases(criminal_id=criminal_id)
        return SuccessResponse(
            data=R4JAliasSerializer(aliases, many=True).data,
            message="لیست اسامی مستعار با موفقیت دریافت شد.",
        )

    @extend_schema(
        operation_id="r4j_admin_aliases_create",
        tags=[TAG_R4J_ADMIN],
        summary="افزودن نام مستعار",
        request=R4JAliasCreateSerializer,
        responses={
            201: ADMIN_ALIAS_RESPONSE,
            400: GENERIC_ERROR_RESPONSE,
            404: GENERIC_ERROR_RESPONSE,
        },
    )
    def post(self, request: Request, criminal_id: int) -> Response:
        criminal = selectors.get_admin_criminal_by_id(criminal_id)
        if criminal is None:
            return ErrorResponse(
                message="مجرمی با این شناسه یافت نشد.",
                status_code=status.HTTP_404_NOT_FOUND,
            )
        serializer = R4JAliasCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        alias = services.add_alias(
            criminal=criminal,
            alias=serializer.validated_data["alias"],
        )
        return CreatedResponse(
            data=R4JAliasSerializer(alias).data,
            message="نام مستعار با موفقیت اضافه شد.",
        )


class R4JAdminAliasDeleteView(APIView):
    """delete one alias — admin."""

    permission_classes = [IsR4JAdminUser]

    @extend_schema(
        operation_id="r4j_admin_aliases_delete",
        tags=[TAG_R4J_ADMIN],
        summary="حذف نام مستعار",
        responses={200: EMPTY_SUCCESS_RESPONSE, 404: GENERIC_ERROR_RESPONSE},
    )
    def delete(self, request: Request, criminal_id: int, alias_id: int) -> Response:
        alias_obj = selectors.get_admin_alias_by_id(
            criminal_id=criminal_id,
            alias_id=alias_id,
        )
        if alias_obj is None:
            return ErrorResponse(
                message="نام مستعاری با این شناسه یافت نشد.",
                status_code=status.HTTP_404_NOT_FOUND,
            )
        services.remove_alias(alias_obj=alias_obj)
        return DeletedResponse(message="نام مستعار با موفقیت حذف شد.")


# ============================================================
# Admin — Nested: Phones
# ============================================================


class R4JAdminPhoneListCreateView(APIView):
    """list + create phones — admin."""

    permission_classes = [IsR4JAdminUser]

    @extend_schema(
        operation_id="r4j_admin_phones_list",
        tags=[TAG_R4J_ADMIN],
        summary="لیست شماره‌های تماس",
        responses={200: ADMIN_PHONE_LIST_RESPONSE, 404: GENERIC_ERROR_RESPONSE},
    )
    def get(self, request: Request, criminal_id: int) -> Response:
        criminal = selectors.get_admin_criminal_by_id(criminal_id)
        if criminal is None:
            return ErrorResponse(
                message="مجرمی با این شناسه یافت نشد.",
                status_code=status.HTTP_404_NOT_FOUND,
            )
        phones = selectors.get_admin_phones(criminal_id=criminal_id)
        return SuccessResponse(
            data=R4JAdminPhoneSerializer(phones, many=True).data,
            message="لیست شماره‌ها با موفقیت دریافت شد.",
        )

    @extend_schema(
        operation_id="r4j_admin_phones_create",
        tags=[TAG_R4J_ADMIN],
        summary="افزودن شماره تماس",
        request=R4JPhoneCreateSerializer,
        responses={
            201: ADMIN_PHONE_RESPONSE,
            400: GENERIC_ERROR_RESPONSE,
            404: GENERIC_ERROR_RESPONSE,
        },
    )
    def post(self, request: Request, criminal_id: int) -> Response:
        criminal = selectors.get_admin_criminal_by_id(criminal_id)
        if criminal is None:
            return ErrorResponse(
                message="مجرمی با این شناسه یافت نشد.",
                status_code=status.HTTP_404_NOT_FOUND,
            )
        serializer = R4JPhoneCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        phone = services.add_phone(criminal=criminal, **serializer.validated_data)

        metadata = extract_audit_metadata(request)
        log_action_async(
            user_id=request.user.pk,
            action=audit_actions.R4J_CRIMINAL_PHONE_ADDED,
            resource_type="r4j_criminal_phone",
            resource_id=str(phone.pk),
            extra_data={"criminal_id": criminal_id},
            **metadata,
        )

        return CreatedResponse(
            data=R4JAdminPhoneSerializer(phone).data,
            message="شماره تماس با موفقیت اضافه شد.",
        )


class R4JAdminPhoneDetailView(APIView):
    """update + delete phone — admin."""

    permission_classes = [IsR4JAdminUser]

    @extend_schema(
        operation_id="r4j_admin_phones_update",
        tags=[TAG_R4J_ADMIN],
        summary="ویرایش شماره تماس",
        request=R4JPhoneUpdateSerializer,
        responses={
            200: ADMIN_PHONE_RESPONSE,
            400: GENERIC_ERROR_RESPONSE,
            404: GENERIC_ERROR_RESPONSE,
        },
    )
    def patch(self, request: Request, criminal_id: int, phone_id: int) -> Response:
        phone = selectors.get_admin_phone_by_id(
            criminal_id=criminal_id,
            phone_id=phone_id,
        )
        if phone is None:
            return ErrorResponse(
                message="شماره‌ای با این شناسه یافت نشد.",
                status_code=status.HTTP_404_NOT_FOUND,
            )
        serializer = R4JPhoneUpdateSerializer(data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        phone = services.update_phone(phone=phone, **serializer.validated_data)
        return SuccessResponse(
            data=R4JAdminPhoneSerializer(phone).data,
            message="شماره تماس با موفقیت بروزرسانی شد.",
        )

    @extend_schema(
        operation_id="r4j_admin_phones_delete",
        tags=[TAG_R4J_ADMIN],
        summary="حذف شماره تماس",
        responses={200: EMPTY_SUCCESS_RESPONSE, 404: GENERIC_ERROR_RESPONSE},
    )
    def delete(self, request: Request, criminal_id: int, phone_id: int) -> Response:
        phone = selectors.get_admin_phone_by_id(
            criminal_id=criminal_id,
            phone_id=phone_id,
        )
        if phone is None:
            return ErrorResponse(
                message="شماره‌ای با این شناسه یافت نشد.",
                status_code=status.HTTP_404_NOT_FOUND,
            )
        services.remove_phone(phone=phone)

        metadata = extract_audit_metadata(request)
        log_action_async(
            user_id=request.user.pk,
            action=audit_actions.R4J_CRIMINAL_PHONE_REMOVED,
            resource_type="r4j_criminal_phone",
            resource_id=str(phone_id),
            extra_data={"criminal_id": criminal_id},
            **metadata,
        )
        return DeletedResponse(message="شماره با موفقیت حذف شد.")


# ============================================================
# Admin — Nested: Socials
# ============================================================


class R4JAdminSocialListCreateView(APIView):
    """list + create socials — admin."""

    permission_classes = [IsR4JAdminUser]

    @extend_schema(
        operation_id="r4j_admin_socials_list",
        tags=[TAG_R4J_ADMIN],
        summary="لیست شبکه‌های اجتماعی",
        responses={200: ADMIN_SOCIAL_LIST_RESPONSE, 404: GENERIC_ERROR_RESPONSE},
    )
    def get(self, request: Request, criminal_id: int) -> Response:
        criminal = selectors.get_admin_criminal_by_id(criminal_id)
        if criminal is None:
            return ErrorResponse(
                message="مجرمی با این شناسه یافت نشد.",
                status_code=status.HTTP_404_NOT_FOUND,
            )
        socials = selectors.get_admin_socials(criminal_id=criminal_id)
        return SuccessResponse(
            data=R4JAdminSocialSerializer(socials, many=True).data,
            message="لیست شبکه‌ها با موفقیت دریافت شد.",
        )

    @extend_schema(
        operation_id="r4j_admin_socials_create",
        tags=[TAG_R4J_ADMIN],
        summary="افزودن شبکه اجتماعی",
        request=R4JSocialCreateSerializer,
        responses={
            201: ADMIN_SOCIAL_RESPONSE,
            400: GENERIC_ERROR_RESPONSE,
            404: GENERIC_ERROR_RESPONSE,
        },
    )
    def post(self, request: Request, criminal_id: int) -> Response:
        criminal = selectors.get_admin_criminal_by_id(criminal_id)
        if criminal is None:
            return ErrorResponse(
                message="مجرمی با این شناسه یافت نشد.",
                status_code=status.HTTP_404_NOT_FOUND,
            )
        serializer = R4JSocialCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            social = services.add_social(criminal=criminal, **serializer.validated_data)
        except R4JServiceError as exc:
            return ErrorResponse(message=str(exc))

        metadata = extract_audit_metadata(request)
        log_action_async(
            user_id=request.user.pk,
            action=audit_actions.R4J_CRIMINAL_SOCIAL_ADDED,
            resource_type="r4j_criminal_social",
            resource_id=str(social.pk),
            extra_data={"criminal_id": criminal_id, "platform": social.platform},
            **metadata,
        )

        return CreatedResponse(
            data=R4JAdminSocialSerializer(social).data,
            message="شبکه اجتماعی با موفقیت اضافه شد.",
        )


class R4JAdminSocialDetailView(APIView):
    """update + delete social — admin."""

    permission_classes = [IsR4JAdminUser]

    @extend_schema(
        operation_id="r4j_admin_socials_update",
        tags=[TAG_R4J_ADMIN],
        summary="ویرایش شبکه اجتماعی",
        request=R4JSocialUpdateSerializer,
        responses={
            200: ADMIN_SOCIAL_RESPONSE,
            400: GENERIC_ERROR_RESPONSE,
            404: GENERIC_ERROR_RESPONSE,
        },
    )
    def patch(self, request: Request, criminal_id: int, social_id: int) -> Response:
        social = selectors.get_admin_social_by_id(
            criminal_id=criminal_id,
            social_id=social_id,
        )
        if social is None:
            return ErrorResponse(
                message="شبکه‌ای با این شناسه یافت نشد.",
                status_code=status.HTTP_404_NOT_FOUND,
            )
        serializer = R4JSocialUpdateSerializer(data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        social = services.update_social(social=social, **serializer.validated_data)
        return SuccessResponse(
            data=R4JAdminSocialSerializer(social).data,
            message="شبکه اجتماعی با موفقیت بروزرسانی شد.",
        )

    @extend_schema(
        operation_id="r4j_admin_socials_delete",
        tags=[TAG_R4J_ADMIN],
        summary="حذف شبکه اجتماعی",
        responses={200: EMPTY_SUCCESS_RESPONSE, 404: GENERIC_ERROR_RESPONSE},
    )
    def delete(self, request: Request, criminal_id: int, social_id: int) -> Response:
        social = selectors.get_admin_social_by_id(
            criminal_id=criminal_id,
            social_id=social_id,
        )
        if social is None:
            return ErrorResponse(
                message="شبکه‌ای با این شناسه یافت نشد.",
                status_code=status.HTTP_404_NOT_FOUND,
            )
        services.remove_social(social=social)

        metadata = extract_audit_metadata(request)
        log_action_async(
            user_id=request.user.pk,
            action=audit_actions.R4J_CRIMINAL_SOCIAL_REMOVED,
            resource_type="r4j_criminal_social",
            resource_id=str(social_id),
            extra_data={"criminal_id": criminal_id},
            **metadata,
        )
        return DeletedResponse(message="شبکه اجتماعی با موفقیت حذف شد.")


# ============================================================
# Admin — Nested: Photos
# ============================================================


class R4JAdminPhotoListCreateView(APIView):
    """list + upload photo — admin."""

    permission_classes = [IsR4JAdminUser]
    parser_classes = [MultiPartParser, FormParser, JSONParser]

    @extend_schema(
        operation_id="r4j_admin_photos_list",
        tags=[TAG_R4J_ADMIN],
        summary="لیست عکس‌ها",
        responses={200: ADMIN_PHOTO_LIST_RESPONSE, 404: GENERIC_ERROR_RESPONSE},
    )
    def get(self, request: Request, criminal_id: int) -> Response:
        criminal = selectors.get_admin_criminal_by_id(criminal_id)
        if criminal is None:
            return ErrorResponse(
                message="مجرمی با این شناسه یافت نشد.",
                status_code=status.HTTP_404_NOT_FOUND,
            )
        photos = selectors.get_admin_photos(criminal_id=criminal_id)
        return SuccessResponse(
            data=R4JAdminPhotoSerializer(photos, many=True).data,
            message="لیست عکس‌ها با موفقیت دریافت شد.",
        )

    @extend_schema(
        operation_id="r4j_admin_photos_create",
        tags=[TAG_R4J_ADMIN],
        summary="آپلود عکس",
        request=R4JPhotoCreateSerializer,
        responses={
            201: ADMIN_PHOTO_RESPONSE,
            400: GENERIC_ERROR_RESPONSE,
            404: GENERIC_ERROR_RESPONSE,
        },
    )
    def post(self, request: Request, criminal_id: int) -> Response:
        criminal = selectors.get_admin_criminal_by_id(criminal_id)
        if criminal is None:
            return ErrorResponse(
                message="مجرمی با این شناسه یافت نشد.",
                status_code=status.HTTP_404_NOT_FOUND,
            )
        serializer = R4JPhotoCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        photo = services.add_photo(criminal=criminal, **serializer.validated_data)

        metadata = extract_audit_metadata(request)
        log_action_async(
            user_id=request.user.pk,
            action=audit_actions.R4J_CRIMINAL_PHOTO_ADDED,
            resource_type="r4j_criminal_photo",
            resource_id=str(photo.pk),
            extra_data={"criminal_id": criminal_id, "is_primary": photo.is_primary},
            **metadata,
        )

        return CreatedResponse(
            data=R4JAdminPhotoSerializer(photo).data,
            message="عکس با موفقیت اضافه شد.",
        )


class R4JAdminPhotoDetailView(APIView):
    """delete photo — admin."""

    permission_classes = [IsR4JAdminUser]

    @extend_schema(
        operation_id="r4j_admin_photos_delete",
        tags=[TAG_R4J_ADMIN],
        summary="حذف عکس",
        responses={200: EMPTY_SUCCESS_RESPONSE, 404: GENERIC_ERROR_RESPONSE},
    )
    def delete(self, request: Request, criminal_id: int, photo_id: int) -> Response:
        photo = selectors.get_admin_photo_by_id(
            criminal_id=criminal_id,
            photo_id=photo_id,
        )
        if photo is None:
            return ErrorResponse(
                message="عکسی با این شناسه یافت نشد.",
                status_code=status.HTTP_404_NOT_FOUND,
            )
        services.remove_photo(photo=photo)

        metadata = extract_audit_metadata(request)
        log_action_async(
            user_id=request.user.pk,
            action=audit_actions.R4J_CRIMINAL_PHOTO_REMOVED,
            resource_type="r4j_criminal_photo",
            resource_id=str(photo_id),
            extra_data={"criminal_id": criminal_id},
            **metadata,
        )
        return DeletedResponse(message="عکس با موفقیت حذف شد.")


class R4JAdminPhotoSetPrimaryView(APIView):
    """set a photo as primary — admin."""

    permission_classes = [IsR4JAdminUser]

    @extend_schema(
        operation_id="r4j_admin_photos_set_primary",
        tags=[TAG_R4J_ADMIN],
        summary="تنظیم عکس به‌عنوان اصلی",
        request=None,
        responses={200: ADMIN_PHOTO_RESPONSE, 404: GENERIC_ERROR_RESPONSE},
    )
    def post(self, request: Request, criminal_id: int, photo_id: int) -> Response:
        photo = selectors.get_admin_photo_by_id(
            criminal_id=criminal_id,
            photo_id=photo_id,
        )
        if photo is None:
            return ErrorResponse(
                message="عکسی با این شناسه یافت نشد.",
                status_code=status.HTTP_404_NOT_FOUND,
            )
        photo = services.set_primary_photo(photo=photo)
        return SuccessResponse(
            data=R4JAdminPhotoSerializer(photo).data,
            message="عکس به‌عنوان اصلی تنظیم شد.",
        )


# ============================================================
# Admin — Nested: Attachments
# ============================================================


class R4JAdminAttachmentListCreateView(APIView):
    """list + upload attachment — admin."""

    permission_classes = [IsR4JAdminUser]
    parser_classes = [MultiPartParser, FormParser, JSONParser]

    @extend_schema(
        operation_id="r4j_admin_attachments_list",
        tags=[TAG_R4J_ADMIN],
        summary="لیست اسناد",
        responses={200: ADMIN_ATTACHMENT_LIST_RESPONSE, 404: GENERIC_ERROR_RESPONSE},
    )
    def get(self, request: Request, criminal_id: int) -> Response:
        criminal = selectors.get_admin_criminal_by_id(criminal_id)
        if criminal is None:
            return ErrorResponse(
                message="مجرمی با این شناسه یافت نشد.",
                status_code=status.HTTP_404_NOT_FOUND,
            )
        attachments = selectors.get_admin_attachments(criminal_id=criminal_id)
        return SuccessResponse(
            data=R4JAdminAttachmentSerializer(attachments, many=True).data,
            message="لیست اسناد با موفقیت دریافت شد.",
        )

    @extend_schema(
        operation_id="r4j_admin_attachments_create",
        tags=[TAG_R4J_ADMIN],
        summary="آپلود سند",
        request=R4JAttachmentCreateSerializer,
        responses={
            201: ADMIN_ATTACHMENT_RESPONSE,
            400: GENERIC_ERROR_RESPONSE,
            404: GENERIC_ERROR_RESPONSE,
        },
    )
    def post(self, request: Request, criminal_id: int) -> Response:
        criminal = selectors.get_admin_criminal_by_id(criminal_id)
        if criminal is None:
            return ErrorResponse(
                message="مجرمی با این شناسه یافت نشد.",
                status_code=status.HTTP_404_NOT_FOUND,
            )
        serializer = R4JAttachmentCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        attachment = services.add_attachment(
            criminal=criminal,
            uploaded_by=request.user,
            **serializer.validated_data,
        )
        return CreatedResponse(
            data=R4JAdminAttachmentSerializer(attachment).data,
            message="سند با موفقیت اضافه شد.",
        )


class R4JAdminAttachmentDetailView(APIView):
    """delete attachment — admin."""

    permission_classes = [IsR4JAdminUser]

    @extend_schema(
        operation_id="r4j_admin_attachments_delete",
        tags=[TAG_R4J_ADMIN],
        summary="حذف سند",
        responses={200: EMPTY_SUCCESS_RESPONSE, 404: GENERIC_ERROR_RESPONSE},
    )
    def delete(
        self,
        request: Request,
        criminal_id: int,
        attachment_id: int,
    ) -> Response:
        attachment = selectors.get_admin_attachment_by_id(
            criminal_id=criminal_id,
            attachment_id=attachment_id,
        )
        if attachment is None:
            return ErrorResponse(
                message="سندی با این شناسه یافت نشد.",
                status_code=status.HTTP_404_NOT_FOUND,
            )
        services.remove_attachment(attachment=attachment)
        return DeletedResponse(message="سند با موفقیت حذف شد.")


# ============================================================
# Admin — Field Visibility
# ============================================================


class R4JAdminFieldVisibilityListUpsertView(APIView):
    """list + upsert visibility — admin."""

    permission_classes = [IsR4JAdminUser]

    @extend_schema(
        operation_id="r4j_admin_visibility_list",
        tags=[TAG_R4J_ADMIN],
        summary="لیست تنظیمات نمایش فیلدها",
        responses={200: ADMIN_VISIBILITY_LIST_RESPONSE, 404: GENERIC_ERROR_RESPONSE},
    )
    def get(self, request: Request, criminal_id: int) -> Response:
        criminal = selectors.get_admin_criminal_by_id(criminal_id)
        if criminal is None:
            return ErrorResponse(
                message="مجرمی با این شناسه یافت نشد.",
                status_code=status.HTTP_404_NOT_FOUND,
            )
        items = selectors.get_admin_field_visibility(criminal_id=criminal_id)
        return SuccessResponse(
            data=R4JAdminFieldVisibilitySerializer(items, many=True).data,
            message="لیست با موفقیت دریافت شد.",
        )

    @extend_schema(
        operation_id="r4j_admin_visibility_upsert",
        tags=[TAG_R4J_ADMIN],
        summary="تنظیم نمایش یک فیلد",
        request=R4JFieldVisibilityUpsertSerializer,
        responses={
            200: ADMIN_VISIBILITY_RESPONSE,
            400: GENERIC_ERROR_RESPONSE,
            404: GENERIC_ERROR_RESPONSE,
        },
    )
    def patch(self, request: Request, criminal_id: int) -> Response:
        criminal = selectors.get_admin_criminal_by_id(criminal_id)
        if criminal is None:
            return ErrorResponse(
                message="مجرمی با این شناسه یافت نشد.",
                status_code=status.HTTP_404_NOT_FOUND,
            )
        serializer = R4JFieldVisibilityUpsertSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        obj = services.upsert_field_visibility(
            criminal=criminal,
            field_name=serializer.validated_data["field_name"],
            is_public=serializer.validated_data["is_public"],
        )

        metadata = extract_audit_metadata(request)
        log_action_async(
            user_id=request.user.pk,
            action=audit_actions.R4J_CRIMINAL_VISIBILITY_CHANGED,
            resource_type="r4j_criminal_field_visibility",
            resource_id=str(obj.pk),
            changes={
                "field_name": serializer.validated_data["field_name"],
                "is_public": serializer.validated_data["is_public"],
            },
            extra_data={"criminal_id": criminal_id},
            **metadata,
        )

        return SuccessResponse(
            data=R4JAdminFieldVisibilitySerializer(obj).data,
            message="تنظیم نمایش با موفقیت اعمال شد.",
        )


# ============================================================
# User — Reports (submit + my reports)
# ============================================================


class R4JUserReportSubmitView(APIView):
    """
    ارسال گزارش community توسط کاربر.

    پشتیبانی از دو حالت:
    - JSON: field_changes به‌صورت list مستقیم
    - Multipart: field_changes به‌صورت JSON string + attachments به‌صورت فایل

    endpoint: POST /api/v1/r4j/criminals/{criminal_id}/reports/
    """

    permission_classes = [IsAuthenticated]
    throttle_classes = [R4JReportCreateThrottle]
    parser_classes = [MultiPartParser, FormParser, JSONParser]

    @extend_schema(
        operation_id="r4j_user_report_submit",
        tags=[TAG_R4J_USER],
        summary="ارسال گزارش تکمیلی برای مجرم",
        description=(
            "کاربر لاگین‌کرده می‌تواند گزارشی برای تکمیل یا اصلاح "
            "اطلاعات یک مجرم ارسال کند.\n\n"
            "**حالت JSON:**\n"
            "```json\n"
            "{\n"
            '  "notes": "متن آزاد",\n'
            '  "field_changes": [{"field_name": "city", "suggested_value": "Tehran"}]\n'
            "}\n"
            "```\n\n"
            "**حالت Multipart (با فایل ضمیمه):**\n"
            "- `notes`: string\n"
            "- `field_changes`: JSON string\n"
            "- `attachments`: یک یا چند فایل\n\n"
            "گزارش باید حداقل شامل یک پیشنهاد تغییر فیلد یا یادداشت باشد.\n\n"
            "تا قبل از تأیید ادمین، هیچ تغییری روی پروفایل مجرم اعمال نمی‌شود."
        ),
        request=R4JReportSubmitSerializer,
        responses={
            201: USER_REPORT_DETAIL_RESPONSE,
            400: GENERIC_ERROR_RESPONSE,
            401: GENERIC_ERROR_RESPONSE,
            404: GENERIC_ERROR_RESPONSE,
        },
    )
    def post(self, request: Request, criminal_id: int) -> Response:
        criminal = selectors.get_public_criminal_detail(lookup=criminal_id)
        if criminal is None:
            return ErrorResponse(
                message="مجرمی با این شناسه یافت نشد.",
                status_code=status.HTTP_404_NOT_FOUND,
            )

        serializer = R4JReportSubmitSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        # استخراج فایل‌های ضمیمه از request.FILES
        # کلید 'attachments' می‌تواند چند فایل داشته باشد
        raw_files = request.FILES.getlist("attachments")
        attachments = (
            [{"file": f, "title": f.name, "kind": "document"} for f in raw_files]
            if raw_files
            else None
        )

        try:
            report = services.submit_report(
                criminal=criminal,
                submitted_by=request.user,
                notes=serializer.validated_data.get("notes", ""),
                field_changes=serializer.validated_data.get("field_changes", []),
                attachments=attachments,
            )
        except InvalidReportableField as exc:
            return ErrorResponse(message=str(exc))

        metadata = extract_audit_metadata(request)
        log_action_async(
            user_id=request.user.pk,
            action=audit_actions.R4J_REPORT_SUBMITTED,
            resource_type="r4j_report",
            resource_id=str(report.pk),
            extra_data={
                "criminal_id": criminal_id,
                "attachment_count": len(raw_files),
            },
            **metadata,
        )

        report_detail = selectors.get_user_report_by_id(
            user_id=request.user.pk,
            report_id=report.pk,
        )

        return CreatedResponse(
            data=R4JUserReportDetailSerializer(report_detail).data,
            message="گزارش شما با موفقیت ثبت شد و در انتظار بررسی است.",
        )


@extend_schema_view(
    get=extend_schema(
        operation_id="r4j_user_my_reports_list",
        tags=[TAG_R4J_USER],
        summary="لیست گزارشات من",
        description="دریافت لیست تمام گزارشاتی که توسط کاربر جاری ارسال شده‌اند.",
        parameters=USER_REPORT_FILTER_PARAMS,
        responses={
            200: USER_REPORT_LIST_RESPONSE,
            401: GENERIC_ERROR_RESPONSE,
        },
    ),
)
class R4JUserMyReportsListView(APIView):
    """لیست گزارشات کاربر جاری."""

    permission_classes = [IsAuthenticated]

    def get(self, request: Request) -> Response:
        queryset = selectors.get_user_reports_queryset(user_id=request.user.pk)
        filterset = R4JReportUserFilter(request.query_params, queryset=queryset)
        if filterset.is_valid():
            queryset = filterset.qs

        paginator = StandardPagination()
        page = paginator.paginate_queryset(queryset, request, view=self)

        if page is not None:
            serializer = R4JUserReportListSerializer(page, many=True)
            return paginator.get_paginated_response(
                serializer.data,
                message="لیست گزارشات با موفقیت دریافت شد.",
            )

        serializer = R4JUserReportListSerializer(queryset, many=True)
        return SuccessResponse(
            data=serializer.data,
            message="لیست گزارشات با موفقیت دریافت شد.",
        )


class R4JUserMyReportDetailView(APIView):
    """جزئیات یک گزارش کاربر + cancel request."""

    permission_classes = [IsAuthenticated]

    @extend_schema(
        operation_id="r4j_user_my_report_retrieve",
        tags=[TAG_R4J_USER],
        summary="جزئیات یک گزارش من",
        responses={
            200: USER_REPORT_DETAIL_RESPONSE,
            401: GENERIC_ERROR_RESPONSE,
            404: GENERIC_ERROR_RESPONSE,
        },
    )
    def get(self, request: Request, report_id: int) -> Response:
        report = selectors.get_user_report_by_id(
            user_id=request.user.pk,
            report_id=report_id,
        )
        if report is None:
            return ErrorResponse(
                message="گزارشی با این شناسه یافت نشد.",
                status_code=status.HTTP_404_NOT_FOUND,
            )
        return SuccessResponse(
            data=R4JUserReportDetailSerializer(report).data,
            message="جزئیات گزارش با موفقیت دریافت شد.",
        )


class R4JUserReportCancelView(APIView):
    """
    درخواست لغو گزارش توسط کاربر.

    endpoint: POST /api/v1/r4j/me/reports/{report_id}/cancel/
    """

    permission_classes = [IsAuthenticated]

    @extend_schema(
        operation_id="r4j_user_report_cancel",
        tags=[TAG_R4J_USER],
        summary="درخواست لغو گزارش",
        description=(
            "کاربر می‌تواند درخواست لغو گزارشی که ارسال کرده را بدهد.\n\n"
            "فقط گزارش‌هایی که در وضعیت «در انتظار بررسی» هستند قابل لغو می‌باشند.\n\n"
            "درخواست لغو باید توسط ادمین تأیید یا رد شود."
        ),
        request=None,
        responses={
            200: USER_REPORT_DETAIL_RESPONSE,
            400: GENERIC_ERROR_RESPONSE,
            401: GENERIC_ERROR_RESPONSE,
            404: GENERIC_ERROR_RESPONSE,
        },
    )
    def post(self, request: Request, report_id: int) -> Response:
        report = selectors.get_user_report_by_id(
            user_id=request.user.pk,
            report_id=report_id,
        )
        if report is None:
            return ErrorResponse(
                message="گزارشی با این شناسه یافت نشد.",
                status_code=status.HTTP_404_NOT_FOUND,
            )

        try:
            report = services.request_report_cancel(
                report=report,
                user=request.user,
            )
        except ReportNotCancelable as exc:
            return ErrorResponse(message=str(exc))

        metadata = extract_audit_metadata(request)
        log_action_async(
            user_id=request.user.pk,
            action=audit_actions.R4J_REPORT_CANCEL_REQUESTED,
            resource_type="r4j_report",
            resource_id=str(report.pk),
            **metadata,
        )

        report_refreshed = selectors.get_user_report_by_id(
            user_id=request.user.pk,
            report_id=report.pk,
        )

        return SuccessResponse(
            data=R4JUserReportDetailSerializer(report_refreshed).data,
            message="درخواست لغو گزارش با موفقیت ثبت شد.",
        )


# ============================================================
# Admin — Reports
# ============================================================


@extend_schema_view(
    get=extend_schema(
        operation_id="r4j_admin_reports_list",
        tags=[TAG_R4J_ADMIN],
        summary="لیست گزارشات — ادمین",
        description="دریافت لیست تمام گزارشات با امکان فیلتر کامل.",
        parameters=ADMIN_REPORT_FILTER_PARAMS,
        responses={
            200: ADMIN_REPORT_LIST_RESPONSE,
            403: GENERIC_ERROR_RESPONSE,
        },
    ),
)
class R4JAdminReportListView(APIView):
    """لیست همه گزارشات — admin."""

    permission_classes = [IsR4JAdminUser]

    def get(self, request: Request) -> Response:
        queryset = selectors.get_admin_reports_queryset()
        filterset = R4JReportAdminFilter(request.query_params, queryset=queryset)
        if filterset.is_valid():
            queryset = filterset.qs

        paginator = StandardPagination()
        page = paginator.paginate_queryset(queryset, request, view=self)

        if page is not None:
            serializer = R4JAdminReportListSerializer(page, many=True)
            return paginator.get_paginated_response(
                serializer.data,
                message="لیست گزارشات با موفقیت دریافت شد.",
            )

        serializer = R4JAdminReportListSerializer(queryset, many=True)
        return SuccessResponse(
            data=serializer.data,
            message="لیست گزارشات با موفقیت دریافت شد.",
        )


class R4JAdminReportDetailView(APIView):
    """جزئیات یک گزارش — admin."""

    permission_classes = [IsR4JAdminUser]

    @extend_schema(
        operation_id="r4j_admin_report_retrieve",
        tags=[TAG_R4J_ADMIN],
        summary="جزئیات گزارش — ادمین",
        responses={
            200: ADMIN_REPORT_DETAIL_RESPONSE,
            403: GENERIC_ERROR_RESPONSE,
            404: GENERIC_ERROR_RESPONSE,
        },
    )
    def get(self, request: Request, report_id: int) -> Response:
        report = selectors.get_admin_report_by_id(report_id=report_id)
        if report is None:
            return ErrorResponse(
                message="گزارشی با این شناسه یافت نشد.",
                status_code=status.HTTP_404_NOT_FOUND,
            )
        return SuccessResponse(
            data=R4JAdminReportDetailSerializer(report).data,
            message="جزئیات گزارش با موفقیت دریافت شد.",
        )


class R4JAdminReportReviewView(APIView):
    """
    بررسی گزارش توسط ادمین — per-field approve/reject + apply.

    endpoint: POST /api/v1/r4j/admin/reports/{report_id}/review/
    """

    permission_classes = [IsR4JAdminUser]

    @extend_schema(
        operation_id="r4j_admin_report_review",
        tags=[TAG_R4J_ADMIN],
        summary="بررسی گزارش — ادمین",
        description=(
            "ادمین می‌تواند برای هر فیلد گزارش به‌صورت مستقل تصمیم بگیرد.\n\n"
            "بعد از review:\n"
            "- اگر همه field_changeها approve شوند → وضعیت APPROVED\n"
            "- اگر برخی approve شوند → وضعیت PARTIALLY_APPROVED\n"
            "- اگر هیچ‌کدام approve نشوند → وضعیت REJECTED\n\n"
            "تغییرات approved بلافاصله روی پروفایل مجرم اعمال می‌شوند."
        ),
        request=R4JReportReviewSerializer,
        responses={
            200: ADMIN_REPORT_DETAIL_RESPONSE,
            400: GENERIC_ERROR_RESPONSE,
            403: GENERIC_ERROR_RESPONSE,
            404: GENERIC_ERROR_RESPONSE,
        },
    )
    def post(self, request: Request, report_id: int) -> Response:
        report = selectors.get_admin_report_by_id(report_id=report_id)
        if report is None:
            return ErrorResponse(
                message="گزارشی با این شناسه یافت نشد.",
                status_code=status.HTTP_404_NOT_FOUND,
            )

        serializer = R4JReportReviewSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        try:
            report = services.review_report(
                report=report,
                reviewed_by=request.user,
                field_decisions=serializer.validated_data.get("field_decisions", []),
                admin_note=serializer.validated_data.get("admin_note", ""),
            )
        except ReportNotReviewable as exc:
            return ErrorResponse(message=str(exc))

        metadata = extract_audit_metadata(request)
        log_action_async(
            user_id=request.user.pk,
            action=audit_actions.R4J_REPORT_REVIEWED,
            resource_type="r4j_report",
            resource_id=str(report.pk),
            extra_data={"final_status": report.status},
            **metadata,
        )

        report_refreshed = selectors.get_admin_report_by_id(report_id=report.pk)

        return SuccessResponse(
            data=R4JAdminReportDetailSerializer(report_refreshed).data,
            message="گزارش با موفقیت بررسی شد.",
        )


class R4JAdminReportCancelApproveView(APIView):
    """
    تأیید درخواست لغو گزارش توسط ادمین.

    endpoint: POST /api/v1/r4j/admin/reports/{report_id}/cancel/approve/
    """

    permission_classes = [IsR4JAdminUser]

    @extend_schema(
        operation_id="r4j_admin_report_cancel_approve",
        tags=[TAG_R4J_ADMIN],
        summary="تأیید درخواست لغو گزارش — ادمین",
        request=R4JReportCancelActionSerializer,
        responses={
            200: ADMIN_REPORT_DETAIL_RESPONSE,
            400: GENERIC_ERROR_RESPONSE,
            403: GENERIC_ERROR_RESPONSE,
            404: GENERIC_ERROR_RESPONSE,
        },
    )
    def post(self, request: Request, report_id: int) -> Response:
        report = selectors.get_admin_report_by_id(report_id=report_id)
        if report is None:
            return ErrorResponse(
                message="گزارشی با این شناسه یافت نشد.",
                status_code=status.HTTP_404_NOT_FOUND,
            )

        serializer = R4JReportCancelActionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        try:
            report = services.approve_report_cancel(
                report=report,
                admin=request.user,
                admin_note=serializer.validated_data.get("admin_note", ""),
            )
        except ReportNotInCancelRequested as exc:
            return ErrorResponse(message=str(exc))

        metadata = extract_audit_metadata(request)
        log_action_async(
            user_id=request.user.pk,
            action=audit_actions.R4J_REPORT_CANCEL_APPROVED,
            resource_type="r4j_report",
            resource_id=str(report.pk),
            **metadata,
        )

        report_refreshed = selectors.get_admin_report_by_id(report_id=report.pk)

        return SuccessResponse(
            data=R4JAdminReportDetailSerializer(report_refreshed).data,
            message="درخواست لغو گزارش تأیید شد.",
        )


class R4JAdminReportCancelRejectView(APIView):
    """
    رد درخواست لغو گزارش توسط ادمین.

    endpoint: POST /api/v1/r4j/admin/reports/{report_id}/cancel/reject/
    """

    permission_classes = [IsR4JAdminUser]

    @extend_schema(
        operation_id="r4j_admin_report_cancel_reject",
        tags=[TAG_R4J_ADMIN],
        summary="رد درخواست لغو گزارش — ادمین",
        request=R4JReportCancelActionSerializer,
        responses={
            200: ADMIN_REPORT_DETAIL_RESPONSE,
            400: GENERIC_ERROR_RESPONSE,
            403: GENERIC_ERROR_RESPONSE,
            404: GENERIC_ERROR_RESPONSE,
        },
    )
    def post(self, request: Request, report_id: int) -> Response:
        report = selectors.get_admin_report_by_id(report_id=report_id)
        if report is None:
            return ErrorResponse(
                message="گزارشی با این شناسه یافت نشد.",
                status_code=status.HTTP_404_NOT_FOUND,
            )

        serializer = R4JReportCancelActionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        try:
            report = services.reject_report_cancel(
                report=report,
                admin=request.user,
                admin_note=serializer.validated_data.get("admin_note", ""),
            )
        except ReportNotInCancelRequested as exc:
            return ErrorResponse(message=str(exc))

        metadata = extract_audit_metadata(request)
        log_action_async(
            user_id=request.user.pk,
            action=audit_actions.R4J_REPORT_CANCEL_REJECTED,
            resource_type="r4j_report",
            resource_id=str(report.pk),
            **metadata,
        )

        report_refreshed = selectors.get_admin_report_by_id(report_id=report.pk)

        return SuccessResponse(
            data=R4JAdminReportDetailSerializer(report_refreshed).data,
            message="درخواست لغو گزارش رد شد و گزارش به وضعیت در انتظار بررسی بازگشت.",
        )


# ============================================================
# User — Bounties
# ============================================================


@extend_schema_view(
    get=extend_schema(
        operation_id="r4j_user_my_bounties_list",
        tags=[TAG_R4J_BOUNTY],
        summary="لیست جوایز من",
        description="دریافت لیست تمام جوایزی که توسط کاربر جاری تعیین شده‌اند.",
        parameters=USER_BOUNTY_FILTER_PARAMS,
        responses={
            200: USER_BOUNTY_LIST_RESPONSE,
            401: GENERIC_ERROR_RESPONSE,
        },
    ),
)
class R4JUserMyBountiesListView(APIView):
    """لیست bountyهای کاربر جاری."""

    permission_classes = [IsAuthenticated]

    def get(self, request: Request) -> Response:
        queryset = selectors.get_user_bounties_queryset(user_id=request.user.pk)
        filterset = R4JBountyUserFilter(request.query_params, queryset=queryset)
        if filterset.is_valid():
            queryset = filterset.qs

        paginator = StandardPagination()
        page = paginator.paginate_queryset(queryset, request, view=self)

        if page is not None:
            serializer = R4JUserBountySerializer(page, many=True)
            return paginator.get_paginated_response(
                serializer.data,
                message="لیست جوایز با موفقیت دریافت شد.",
            )

        serializer = R4JUserBountySerializer(queryset, many=True)
        return SuccessResponse(
            data=serializer.data,
            message="لیست جوایز با موفقیت دریافت شد.",
        )


class R4JUserBountySetView(APIView):
    """
    تعیین یا ویرایش bounty توسط کاربر fully verified.

    endpoint: POST /api/v1/r4j/criminals/{criminal_id}/bounty/
    """

    permission_classes = [IsFullyVerifiedUser]
    throttle_classes = [R4JBountySetThrottle]

    @extend_schema(
        operation_id="r4j_user_bounty_set_or_update",
        tags=[TAG_R4J_BOUNTY],
        summary="تعیین یا ویرایش جایزه برای مجرم",
        description=(
            "کاربرانی که احراز هویت کامل داشته و پروفایل آن‌ها کامل باشد "
            "می‌توانند برای یک مجرم جایزه تعیین کنند.\n\n"
            "اگر قبلاً برای همان مجرم جایزه‌ای فعال ثبت کرده باشند، همان رکورد "
            "به‌روزرسانی می‌شود؛ در غیر این صورت رکورد جدید ساخته می‌شود."
        ),
        request=R4JBountySetSerializer,
        responses={
            201: USER_BOUNTY_DETAIL_RESPONSE,
            200: USER_BOUNTY_DETAIL_RESPONSE,
            400: GENERIC_ERROR_RESPONSE,
            401: GENERIC_ERROR_RESPONSE,
            403: GENERIC_ERROR_RESPONSE,
            404: GENERIC_ERROR_RESPONSE,
            429: GENERIC_ERROR_RESPONSE,
        },
    )
    def post(self, request: Request, criminal_id: int) -> Response:
        criminal = selectors.get_public_criminal_detail(lookup=criminal_id)
        if criminal is None:
            return ErrorResponse(
                message="مجرمی با این شناسه یافت نشد.",
                status_code=status.HTTP_404_NOT_FOUND,
            )

        serializer = R4JBountySetSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        try:
            bounty, created = services.set_or_update_bounty(
                criminal=criminal,
                user=request.user,
                amount_toman=serializer.validated_data["amount_toman"],
            )
        except (InvalidBountyAmount, BountyUpdateNotAllowed) as exc:
            return ErrorResponse(message=str(exc))

        metadata = extract_audit_metadata(request)
        log_action_async(
            user_id=request.user.pk,
            action=(
                audit_actions.R4J_BOUNTY_CREATED
                if created
                else audit_actions.R4J_BOUNTY_UPDATED
            ),
            resource_type="r4j_bounty",
            resource_id=str(bounty.pk),
            extra_data={
                "criminal_id": criminal_id,
                "amount_toman": bounty.amount_toman,
            },
            **metadata,
        )

        bounty_detail = selectors.get_user_bounty_by_id(
            user_id=request.user.pk,
            bounty_id=bounty.pk,
        )

        if created:
            return CreatedResponse(
                data=R4JUserBountySerializer(bounty_detail).data,
                message="جایزه با موفقیت ثبت شد.",
            )

        return SuccessResponse(
            data=R4JUserBountySerializer(bounty_detail).data,
            message="جایزه با موفقیت بروزرسانی شد.",
        )


class R4JUserBountyCancelView(APIView):
    """
    درخواست لغو bounty توسط owner.

    endpoint: POST /api/v1/r4j/me/bounties/{bounty_id}/cancel/
    """

    permission_classes = [IsAuthenticated]

    @extend_schema(
        operation_id="r4j_user_bounty_cancel_request",
        tags=[TAG_R4J_BOUNTY],
        summary="درخواست لغو جایزه",
        description=(
            "کاربر می‌تواند برای جایزه‌ای که خودش تعیین کرده درخواست لغو ثبت کند.\n\n"
            "فقط جایزه‌های فعال قابل درخواست لغو هستند و درخواست لغو باید "
            "توسط ادمین تأیید یا رد شود."
        ),
        request=None,
        responses={
            200: USER_BOUNTY_DETAIL_RESPONSE,
            400: GENERIC_ERROR_RESPONSE,
            401: GENERIC_ERROR_RESPONSE,
            404: GENERIC_ERROR_RESPONSE,
        },
    )
    def post(self, request: Request, bounty_id: int) -> Response:
        bounty = selectors.get_user_bounty_by_id(
            user_id=request.user.pk,
            bounty_id=bounty_id,
        )
        if bounty is None:
            return ErrorResponse(
                message="جایزه‌ای با این شناسه یافت نشد.",
                status_code=status.HTTP_404_NOT_FOUND,
            )

        try:
            bounty = services.request_bounty_cancel(
                bounty=bounty,
                user=request.user,
            )
        except BountyNotCancelable as exc:
            return ErrorResponse(message=str(exc))

        metadata = extract_audit_metadata(request)
        log_action_async(
            user_id=request.user.pk,
            action=audit_actions.R4J_BOUNTY_CANCEL_REQUESTED,
            resource_type="r4j_bounty",
            resource_id=str(bounty.pk),
            **metadata,
        )

        bounty_refreshed = selectors.get_user_bounty_by_id(
            user_id=request.user.pk,
            bounty_id=bounty.pk,
        )

        return SuccessResponse(
            data=R4JUserBountySerializer(bounty_refreshed).data,
            message="درخواست لغو جایزه با موفقیت ثبت شد.",
        )


# ============================================================
# Admin — Bounties
# ============================================================


@extend_schema_view(
    get=extend_schema(
        operation_id="r4j_admin_bounties_list",
        tags=[TAG_R4J_ADMIN],
        summary="لیست جوایز — ادمین",
        description="دریافت لیست تمام جوایز ثبت‌شده با امکان فیلتر کامل.",
        parameters=ADMIN_BOUNTY_FILTER_PARAMS,
        responses={
            200: ADMIN_BOUNTY_LIST_RESPONSE,
            403: GENERIC_ERROR_RESPONSE,
        },
    ),
)
class R4JAdminBountyListView(APIView):
    """لیست تمام bountyها — admin."""

    permission_classes = [IsR4JAdminUser]

    def get(self, request: Request) -> Response:
        queryset = selectors.get_admin_bounties_queryset()
        filterset = R4JBountyAdminFilter(request.query_params, queryset=queryset)
        if filterset.is_valid():
            queryset = filterset.qs

        paginator = StandardPagination()
        page = paginator.paginate_queryset(queryset, request, view=self)

        if page is not None:
            serializer = R4JAdminBountyListSerializer(page, many=True)
            return paginator.get_paginated_response(
                serializer.data,
                message="لیست جوایز با موفقیت دریافت شد.",
            )

        serializer = R4JAdminBountyListSerializer(queryset, many=True)
        return SuccessResponse(
            data=serializer.data,
            message="لیست جوایز با موفقیت دریافت شد.",
        )


class R4JAdminBountyDetailView(APIView):
    """جزئیات یک bounty — admin."""

    permission_classes = [IsR4JAdminUser]

    @extend_schema(
        operation_id="r4j_admin_bounty_retrieve",
        tags=[TAG_R4J_ADMIN],
        summary="جزئیات جایزه — ادمین",
        responses={
            200: ADMIN_BOUNTY_DETAIL_RESPONSE,
            403: GENERIC_ERROR_RESPONSE,
            404: GENERIC_ERROR_RESPONSE,
        },
    )
    def get(self, request: Request, bounty_id: int) -> Response:
        bounty = selectors.get_admin_bounty_by_id(bounty_id=bounty_id)
        if bounty is None:
            return ErrorResponse(
                message="جایزه‌ای با این شناسه یافت نشد.",
                status_code=status.HTTP_404_NOT_FOUND,
            )
        return SuccessResponse(
            data=R4JAdminBountyDetailSerializer(bounty).data,
            message="جزئیات جایزه با موفقیت دریافت شد.",
        )


class R4JAdminBountyCancelApproveView(APIView):
    """
    تأیید درخواست لغو bounty توسط ادمین.

    endpoint: POST /api/v1/r4j/admin/bounties/{bounty_id}/cancel/approve/
    """

    permission_classes = [IsR4JAdminUser]

    @extend_schema(
        operation_id="r4j_admin_bounty_cancel_approve",
        tags=[TAG_R4J_ADMIN],
        summary="تأیید درخواست لغو جایزه — ادمین",
        request=R4JBountyCancelActionSerializer,
        responses={
            200: ADMIN_BOUNTY_DETAIL_RESPONSE,
            400: GENERIC_ERROR_RESPONSE,
            403: GENERIC_ERROR_RESPONSE,
            404: GENERIC_ERROR_RESPONSE,
        },
    )
    def post(self, request: Request, bounty_id: int) -> Response:
        bounty = selectors.get_admin_bounty_by_id(bounty_id=bounty_id)
        if bounty is None:
            return ErrorResponse(
                message="جایزه‌ای با این شناسه یافت نشد.",
                status_code=status.HTTP_404_NOT_FOUND,
            )

        serializer = R4JBountyCancelActionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        try:
            bounty = services.approve_bounty_cancel(
                bounty=bounty,
                admin=request.user,
                admin_note=serializer.validated_data.get("admin_note", ""),
            )
        except BountyNotInCancelRequested as exc:
            return ErrorResponse(message=str(exc))

        metadata = extract_audit_metadata(request)
        log_action_async(
            user_id=request.user.pk,
            action=audit_actions.R4J_BOUNTY_CANCEL_APPROVED,
            resource_type="r4j_bounty",
            resource_id=str(bounty.pk),
            **metadata,
        )

        bounty_refreshed = selectors.get_admin_bounty_by_id(bounty_id=bounty.pk)

        return SuccessResponse(
            data=R4JAdminBountyDetailSerializer(bounty_refreshed).data,
            message="درخواست لغو جایزه تأیید شد.",
        )


class R4JAdminBountyCancelRejectView(APIView):
    """
    رد درخواست لغو bounty توسط ادمین.

    endpoint: POST /api/v1/r4j/admin/bounties/{bounty_id}/cancel/reject/
    """

    permission_classes = [IsR4JAdminUser]

    @extend_schema(
        operation_id="r4j_admin_bounty_cancel_reject",
        tags=[TAG_R4J_ADMIN],
        summary="رد درخواست لغو جایزه — ادمین",
        request=R4JBountyCancelActionSerializer,
        responses={
            200: ADMIN_BOUNTY_DETAIL_RESPONSE,
            400: GENERIC_ERROR_RESPONSE,
            403: GENERIC_ERROR_RESPONSE,
            404: GENERIC_ERROR_RESPONSE,
        },
    )
    def post(self, request: Request, bounty_id: int) -> Response:
        bounty = selectors.get_admin_bounty_by_id(bounty_id=bounty_id)
        if bounty is None:
            return ErrorResponse(
                message="جایزه‌ای با این شناسه یافت نشد.",
                status_code=status.HTTP_404_NOT_FOUND,
            )

        serializer = R4JBountyCancelActionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        try:
            bounty = services.reject_bounty_cancel(
                bounty=bounty,
                admin=request.user,
                admin_note=serializer.validated_data.get("admin_note", ""),
            )
        except BountyNotInCancelRequested as exc:
            return ErrorResponse(message=str(exc))

        metadata = extract_audit_metadata(request)
        log_action_async(
            user_id=request.user.pk,
            action=audit_actions.R4J_BOUNTY_CANCEL_REJECTED,
            resource_type="r4j_bounty",
            resource_id=str(bounty.pk),
            **metadata,
        )

        bounty_refreshed = selectors.get_admin_bounty_by_id(bounty_id=bounty.pk)

        return SuccessResponse(
            data=R4JAdminBountyDetailSerializer(bounty_refreshed).data,
            message="درخواست لغو جایزه رد شد و جایزه دوباره فعال شد.",
        )


class R4JAdminEvidenceCustodyListView(APIView):
    """Admin list endpoint for evidence chain-of-custody events."""

    permission_classes = [IsR4JAdminUser]

    @extend_schema(
        operation_id="r4j_admin_evidence_custody_list",
        tags=[TAG_R4J_ADMIN],
        summary="لیست زنجیره نگهداری شواهد",
        responses={200: ADMIN_CUSTODY_EVENT_LIST_RESPONSE},
    )
    def get(self, request: Request) -> Response:
        queryset = selectors.get_admin_evidence_custody_events()
        event_type = request.query_params.get("event_type")
        if event_type:
            queryset = queryset.filter(event_type=event_type)
        file_hash = request.query_params.get("file_sha256")
        if file_hash:
            queryset = queryset.filter(file_sha256=file_hash)
        paginator = StandardPagination()
        page = paginator.paginate_queryset(queryset, request, view=self)
        serializer = R4JEvidenceCustodyEventSerializer(page, many=True)
        return paginator.get_paginated_response(serializer.data, message="زنجیره نگهداری شواهد دریافت شد.")


class R4JAdminEvidenceCustodyReviewView(APIView):
    """Admin endpoint to append a custody review/transfer/reject event."""

    permission_classes = [IsR4JAdminUser]

    @extend_schema(
        operation_id="r4j_admin_evidence_custody_review",
        tags=[TAG_R4J_ADMIN],
        request=R4JEvidenceCustodyReviewSerializer,
        responses={201: ADMIN_CUSTODY_EVENT_RESPONSE, 404: GENERIC_ERROR_RESPONSE},
    )
    def post(self, request: Request, event_id: int) -> Response:
        event = selectors.get_admin_evidence_custody_event_by_id(event_id=event_id)
        if event is None:
            return ErrorResponse(message="رویداد custody یافت نشد.", status_code=status.HTTP_404_NOT_FOUND)
        serializer = R4JEvidenceCustodyReviewSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        new_event = services.record_evidence_custody_review(
            event=event,
            actor=request.user,
            event_type=serializer.validated_data["event_type"],
            note=serializer.validated_data.get("note", ""),
        )
        log_action_async(
            user_id=request.user.pk,
            action=audit_actions.R4J_EVIDENCE_CUSTODY_REVIEWED,
            resource_type="r4j_evidence_custody_event",
            resource_id=str(new_event.pk),
            extra_data={"event_type": new_event.event_type, "file_sha256": new_event.file_sha256},
            **extract_audit_metadata(request),
        )
        return CreatedResponse(data=R4JEvidenceCustodyEventSerializer(new_event).data, message="رویداد custody ثبت شد.")

# ============================================================
# Admin — Investigation Case Management & Operational Workflow
# ============================================================


CASE_LIST_RESPONSE = build_paginated_success_response_serializer(
    name="R4JCaseListResponse",
    item_serializer=R4JInvestigationCaseListSerializer,
)
CASE_DETAIL_RESPONSE = build_success_response_serializer(
    name="R4JCaseDetailResponse",
    data_serializer=R4JInvestigationCaseDetailSerializer,
)
CASE_EVENT_LIST_RESPONSE = build_success_response_serializer(
    name="R4JCaseEventListResponse",
    data_serializer=R4JCaseEventSerializer,
    many=True,
)
CASE_OVERVIEW_RESPONSE = build_success_response_serializer(
    name="R4JCaseOperationsOverviewResponse",
    data_serializer=R4JCaseOperationsOverviewSerializer,
)


def _audit_case_action(request: Request, *, action: str, case, extra_data: dict | None = None) -> None:
    """Centralized async audit logging for R4J case admin actions."""
    log_action_async(
        user_id=request.user.pk,
        action=action,
        resource_type="r4j_investigation_case",
        resource_id=str(case.pk),
        extra_data={"case_number": case.case_number, **(extra_data or {})},
        **extract_audit_metadata(request),
    )


def _case_or_404(*, case_number: str):
    """Resolve case by number for admin endpoints."""
    return selectors.get_admin_investigation_case_by_number(case_number=case_number)


class R4JAdminCaseListView(APIView):
    """Admin endpoint for listing operational investigation cases."""

    permission_classes = [IsR4JAdminUser]

    @extend_schema(
        operation_id="r4j_admin_case_list",
        tags=[TAG_R4J_ADMIN],
        summary="لیست پرونده‌های عملیاتی R4J",
        parameters=[*LIST_PAGINATION_PARAMS],
        responses={200: CASE_LIST_RESPONSE},
    )
    def get(self, request: Request) -> Response:
        queryset = selectors.get_admin_investigation_cases_queryset()
        status_filter = request.query_params.get("status")
        if status_filter:
            queryset = queryset.filter(status=status_filter)
        priority = request.query_params.get("priority")
        if priority:
            queryset = queryset.filter(priority=priority)
        assigned_to = request.query_params.get("assigned_to")
        if assigned_to:
            queryset = queryset.filter(assigned_to_id=assigned_to)
        paginator = StandardPagination()
        page = paginator.paginate_queryset(queryset, request, view=self)
        serializer = R4JInvestigationCaseListSerializer(page, many=True)
        return paginator.get_paginated_response(serializer.data, message="پرونده‌های عملیاتی دریافت شد.")


class R4JAdminCaseCreateFromReportView(APIView):
    """Admin endpoint to create an operational case from a report."""

    permission_classes = [IsR4JAdminUser]

    @extend_schema(
        operation_id="r4j_admin_case_create_from_report",
        tags=[TAG_R4J_ADMIN],
        request=R4JCaseCreateFromReportSerializer,
        responses={201: CASE_DETAIL_RESPONSE, 404: GENERIC_ERROR_RESPONSE},
    )
    def post(self, request: Request, report_id: int) -> Response:
        report = selectors.get_admin_report_by_id(report_id=report_id)
        if report is None:
            return ErrorResponse(message="گزارش یافت نشد.", status_code=status.HTTP_404_NOT_FOUND)
        serializer = R4JCaseCreateFromReportSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            case = services.create_investigation_case_from_report(report=report, actor=request.user)
        except InvestigationCaseAlreadyExists as exc:
            return ErrorResponse(message=str(exc), status_code=status.HTTP_409_CONFLICT)
        _audit_case_action(request, action=audit_actions.R4J_CASE_CREATED, case=case, extra_data={"report_id": report.pk})
        return CreatedResponse(data=R4JInvestigationCaseDetailSerializer(case).data, message="پرونده عملیاتی ایجاد شد.")


class R4JAdminCaseDetailView(APIView):
    """Admin endpoint for case detail."""

    permission_classes = [IsR4JAdminUser]

    @extend_schema(
        operation_id="r4j_admin_case_detail",
        tags=[TAG_R4J_ADMIN],
        responses={200: CASE_DETAIL_RESPONSE, 404: GENERIC_ERROR_RESPONSE},
    )
    def get(self, request: Request, case_number: str) -> Response:
        case = _case_or_404(case_number=case_number)
        if case is None:
            return ErrorResponse(message="پرونده یافت نشد.", status_code=status.HTTP_404_NOT_FOUND)
        return SuccessResponse(data=R4JInvestigationCaseDetailSerializer(case).data, message="جزئیات پرونده دریافت شد.")


class R4JAdminCaseTriageView(APIView):
    """Admin endpoint for case triage."""

    permission_classes = [IsR4JAdminUser]

    @extend_schema(operation_id="r4j_admin_case_triage", tags=[TAG_R4J_ADMIN], request=R4JCaseTriageSerializer, responses={200: CASE_DETAIL_RESPONSE})
    def post(self, request: Request, case_number: str) -> Response:
        case = _case_or_404(case_number=case_number)
        if case is None:
            return ErrorResponse(message="پرونده یافت نشد.", status_code=status.HTTP_404_NOT_FOUND)
        serializer = R4JCaseTriageSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            case = services.triage_investigation_case(case=case, actor=request.user, **serializer.validated_data)
        except R4JServiceError as exc:
            return ErrorResponse(message=str(exc))
        _audit_case_action(request, action=audit_actions.R4J_CASE_TRIAGED, case=case)
        return SuccessResponse(data=R4JInvestigationCaseDetailSerializer(case).data, message="پرونده تریاژ شد.")


class R4JAdminCaseAssignView(APIView):
    """Admin endpoint for assigning a case."""

    permission_classes = [IsR4JAdminUser]

    @extend_schema(operation_id="r4j_admin_case_assign", tags=[TAG_R4J_ADMIN], request=R4JCaseAssignSerializer, responses={200: CASE_DETAIL_RESPONSE})
    def post(self, request: Request, case_number: str) -> Response:
        case = _case_or_404(case_number=case_number)
        if case is None:
            return ErrorResponse(message="پرونده یافت نشد.", status_code=status.HTTP_404_NOT_FOUND)
        serializer = R4JCaseAssignSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user_model = get_user_model()
        assignee = user_model.objects.filter(pk=serializer.validated_data["assignee_id"], is_active=True).first()
        if assignee is None:
            return ErrorResponse(message="کاربر مسئول یافت نشد.", status_code=status.HTTP_404_NOT_FOUND)
        try:
            case = services.assign_investigation_case(case=case, actor=request.user, assignee=assignee, note=serializer.validated_data.get("note", ""))
        except R4JServiceError as exc:
            return ErrorResponse(message=str(exc))
        _audit_case_action(request, action=audit_actions.R4J_CASE_ASSIGNED, case=case, extra_data={"assignee_id": assignee.pk})
        return SuccessResponse(data=R4JInvestigationCaseDetailSerializer(case).data, message="پرونده ارجاع شد.")


class R4JAdminCasePriorityView(APIView):
    """Admin endpoint for changing case priority."""

    permission_classes = [IsR4JAdminUser]

    @extend_schema(operation_id="r4j_admin_case_priority", tags=[TAG_R4J_ADMIN], request=R4JCasePrioritySerializer, responses={200: CASE_DETAIL_RESPONSE})
    def post(self, request: Request, case_number: str) -> Response:
        case = _case_or_404(case_number=case_number)
        if case is None:
            return ErrorResponse(message="پرونده یافت نشد.", status_code=status.HTTP_404_NOT_FOUND)
        serializer = R4JCasePrioritySerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            case = services.change_investigation_case_priority(case=case, actor=request.user, **serializer.validated_data)
        except R4JServiceError as exc:
            return ErrorResponse(message=str(exc))
        _audit_case_action(request, action=audit_actions.R4J_CASE_PRIORITY_CHANGED, case=case, extra_data={"priority": case.priority})
        return SuccessResponse(data=R4JInvestigationCaseDetailSerializer(case).data, message="اولویت پرونده تغییر کرد.")


class R4JAdminCaseEvidenceRequestView(APIView):
    """Admin endpoint for requesting more evidence."""

    permission_classes = [IsR4JAdminUser]

    @extend_schema(operation_id="r4j_admin_case_evidence_request", tags=[TAG_R4J_ADMIN], request=R4JCaseEvidenceRequestSerializer, responses={200: CASE_DETAIL_RESPONSE})
    def post(self, request: Request, case_number: str) -> Response:
        case = _case_or_404(case_number=case_number)
        if case is None:
            return ErrorResponse(message="پرونده یافت نشد.", status_code=status.HTTP_404_NOT_FOUND)
        serializer = R4JCaseEvidenceRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            case = services.request_more_evidence(case=case, actor=request.user, note=serializer.validated_data["note"])
        except R4JServiceError as exc:
            return ErrorResponse(message=str(exc))
        _audit_case_action(request, action=audit_actions.R4J_CASE_EVIDENCE_REQUESTED, case=case)
        return SuccessResponse(data=R4JInvestigationCaseDetailSerializer(case).data, message="درخواست مدرک بیشتر ثبت شد.")


class R4JAdminCaseEscalateView(APIView):
    """Admin endpoint for escalating a case."""

    permission_classes = [IsR4JAdminUser]

    @extend_schema(operation_id="r4j_admin_case_escalate", tags=[TAG_R4J_ADMIN], request=R4JCaseNoteRequiredSerializer, responses={200: CASE_DETAIL_RESPONSE})
    def post(self, request: Request, case_number: str) -> Response:
        return _case_reason_transition(request, case_number, services.escalate_investigation_case, audit_actions.R4J_CASE_ESCALATED, "پرونده فوری شد.")


class R4JAdminCaseResolveView(APIView):
    """Admin endpoint for resolving a case."""

    permission_classes = [IsR4JAdminUser]

    @extend_schema(operation_id="r4j_admin_case_resolve", tags=[TAG_R4J_ADMIN], request=R4JCaseNoteRequiredSerializer, responses={200: CASE_DETAIL_RESPONSE})
    def post(self, request: Request, case_number: str) -> Response:
        return _case_reason_transition(request, case_number, services.resolve_investigation_case, audit_actions.R4J_CASE_RESOLVED, "پرونده حل شد.")


class R4JAdminCaseRejectView(APIView):
    """Admin endpoint for rejecting a case."""

    permission_classes = [IsR4JAdminUser]

    @extend_schema(operation_id="r4j_admin_case_reject", tags=[TAG_R4J_ADMIN], request=R4JCaseNoteRequiredSerializer, responses={200: CASE_DETAIL_RESPONSE})
    def post(self, request: Request, case_number: str) -> Response:
        return _case_reason_transition(request, case_number, services.reject_investigation_case, audit_actions.R4J_CASE_REJECTED, "پرونده رد شد.")


class R4JAdminCaseCloseView(APIView):
    """Admin endpoint for closing a case."""

    permission_classes = [IsR4JAdminUser]

    @extend_schema(operation_id="r4j_admin_case_close", tags=[TAG_R4J_ADMIN], request=R4JCaseNoteRequiredSerializer, responses={200: CASE_DETAIL_RESPONSE})
    def post(self, request: Request, case_number: str) -> Response:
        return _case_reason_transition(request, case_number, services.close_investigation_case, audit_actions.R4J_CASE_CLOSED, "پرونده بسته شد.")


class R4JAdminCaseReopenView(APIView):
    """Admin endpoint for reopening a terminal case."""

    permission_classes = [IsR4JAdminUser]

    @extend_schema(operation_id="r4j_admin_case_reopen", tags=[TAG_R4J_ADMIN], request=R4JCaseNoteRequiredSerializer, responses={200: CASE_DETAIL_RESPONSE})
    def post(self, request: Request, case_number: str) -> Response:
        return _case_reason_transition(request, case_number, services.reopen_investigation_case, audit_actions.R4J_CASE_REOPENED, "پرونده بازگشایی شد.")


def _case_reason_transition(request: Request, case_number: str, service_func, audit_action: str, message: str) -> Response:
    """Shared orchestration for reason-required case transitions."""
    case = _case_or_404(case_number=case_number)
    if case is None:
        return ErrorResponse(message="پرونده یافت نشد.", status_code=status.HTTP_404_NOT_FOUND)
    serializer = R4JCaseNoteRequiredSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    try:
        case = service_func(case=case, actor=request.user, reason=serializer.validated_data["reason"])
    except R4JServiceError as exc:
        return ErrorResponse(message=str(exc))
    _audit_case_action(request, action=audit_action, case=case)
    return SuccessResponse(data=R4JInvestigationCaseDetailSerializer(case).data, message=message)


class R4JAdminCaseTimelineView(APIView):
    """Admin endpoint for immutable case timeline."""

    permission_classes = [IsR4JAdminUser]

    @extend_schema(operation_id="r4j_admin_case_timeline", tags=[TAG_R4J_ADMIN], responses={200: CASE_EVENT_LIST_RESPONSE})
    def get(self, request: Request, case_number: str) -> Response:
        case = _case_or_404(case_number=case_number)
        if case is None:
            return ErrorResponse(message="پرونده یافت نشد.", status_code=status.HTTP_404_NOT_FOUND)
        events = selectors.get_admin_investigation_case_timeline(case=case)
        return SuccessResponse(data=R4JCaseEventSerializer(events, many=True).data, message="خط زمانی پرونده دریافت شد.")


class R4JAdminCaseOperationsOverviewView(APIView):
    """Admin operational overview for R4J cases."""

    permission_classes = [IsR4JAdminUser]

    @extend_schema(operation_id="r4j_admin_case_operations_overview", tags=[TAG_R4J_ADMIN], responses={200: CASE_OVERVIEW_RESPONSE})
    def get(self, request: Request) -> Response:
        overview = selectors.get_r4j_case_operations_overview()
        return SuccessResponse(data=overview, message="نمای کلی عملیات R4J دریافت شد.")

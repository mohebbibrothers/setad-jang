"""مشترکات views — constants/helpers که گروه‌های دامنه‌ای import می‌کنند.

با ابزار split_views در فاز ۱۱ از views.py جدا شد؛ منطق دست‌نخورده است(برشِ verbatim). facade در views.py همه را دوباره export می‌کند تا مسیرهایimport بیرونی (urls/tests) تغییر نکنند.
"""

from __future__ import annotations

import hashlib

from drf_spectacular.utils import (
    OpenApiParameter,
    OpenApiTypes,
)
from rest_framework.request import Request

from apps.core.schemas import (
    build_error_response_serializer,
    build_paginated_success_response_serializer,
    build_success_response_serializer,
)

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
    R4JAliasSerializer,
    R4JEvidenceCustodyEventSerializer,
    R4JPublicCriminalDetailSerializer,
    R4JPublicCriminalListSerializer,
    R4JUserBountySerializer,
    R4JUserReportDetailSerializer,
    R4JUserReportListSerializer,
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

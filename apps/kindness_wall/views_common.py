"""مشترکات views — constants/helpers که گروه‌های دامنه‌ای import می‌کنند.

با ابزار split_views در فاز ۱۱ از views.py جدا شد؛ منطق دست‌نخورده است(برشِ verbatim). facade در views.py همه را دوباره export می‌کند تا مسیرهایimport بیرونی (urls/tests) تغییر نکنند.
"""

from __future__ import annotations

from rest_framework import status

from apps.core.responses import ErrorResponse
from apps.core.schemas import (
    build_error_response_serializer,
    build_paginated_success_response_serializer,
    build_success_response_serializer,
)
from apps.kindness_wall.serializers import (
    KindnessAdminAnalyticsSerializer,
    KindnessCategorySerializer,
    KindnessContactRevealSerializer,
    KindnessListingDetailSerializer,
    KindnessListingListSerializer,
    KindnessListingReportSerializer,
    KindnessMatchSerializer,
    KindnessUserListingDetailSerializer,
)

TAG_PUBLIC = "دیوار مهربانی — عمومی"
TAG_USER = "دیوار مهربانی — کاربر"
TAG_ADMIN = "دیوار مهربانی — مدیریت"
ERROR_RESPONSE = build_error_response_serializer(name="KindnessWallErrorResponse")
CATEGORY_LIST_RESPONSE = build_success_response_serializer(
    name="KindnessCategoryListResponse", data_serializer=KindnessCategorySerializer, many=True
)
LISTING_LIST_RESPONSE = build_paginated_success_response_serializer(
    name="KindnessListingListResponse", item_serializer=KindnessListingListSerializer
)
LISTING_DETAIL_RESPONSE = build_success_response_serializer(
    name="KindnessListingDetailResponse", data_serializer=KindnessListingDetailSerializer
)
USER_LISTING_DETAIL_RESPONSE = build_success_response_serializer(
    name="KindnessUserListingDetailResponse", data_serializer=KindnessUserListingDetailSerializer
)
MATCH_LIST_RESPONSE = build_paginated_success_response_serializer(
    name="KindnessMatchListResponse", item_serializer=KindnessMatchSerializer
)
CONTACT_REVEAL_RESPONSE = build_success_response_serializer(
    name="KindnessContactRevealResponse", data_serializer=KindnessContactRevealSerializer
)
REPORT_RESPONSE = build_success_response_serializer(
    name="KindnessListingReportResponse", data_serializer=KindnessListingReportSerializer
)
ANALYTICS_RESPONSE = build_success_response_serializer(
    name="KindnessAnalyticsResponse", data_serializer=KindnessAdminAnalyticsSerializer
)
EMPTY_RESPONSE = build_success_response_serializer(name="KindnessEmptyResponse")


def _service_error_response(
    exc: Exception, *, status_code: int = status.HTTP_400_BAD_REQUEST
) -> ErrorResponse:
    """Convert service-layer exception to project error response."""
    return ErrorResponse(message=str(exc), status_code=status_code)

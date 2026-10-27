"""مشترکات views دیوار مهربانی: برچسب‌ها، اسکیمای پاسخ‌ها و helper خطا."""

from __future__ import annotations

from rest_framework import status

from apps.core.responses import ErrorResponse
from apps.core.schemas import (
    build_error_response_serializer,
    build_paginated_success_response_serializer,
    build_success_response_serializer,
)
from apps.kindness_wall.serializers import (
    KindnessAdminListingSerializer,
    KindnessAdminOfferSerializer,
    KindnessBoardStatsSerializer,
    KindnessCategorySerializer,
    KindnessListingDetailSerializer,
    KindnessListingListSerializer,
    KindnessOfferSerializer,
    KindnessStorySerializer,
)

TAG_PUBLIC = "دیوار مهربانی — عمومی"
TAG_USER = "دیوار مهربانی — کاربر"
TAG_ADMIN = "دیوار مهربانی — مدیریت"

ERROR_RESPONSE = build_error_response_serializer(name="KindnessWallErrorResponse")
EMPTY_RESPONSE = build_success_response_serializer(name="KindnessEmptyResponse")
CATEGORY_LIST_RESPONSE = build_success_response_serializer(
    name="KindnessCategoryListResponse", data_serializer=KindnessCategorySerializer, many=True
)
LISTING_LIST_RESPONSE = build_paginated_success_response_serializer(
    name="KindnessListingListResponse", item_serializer=KindnessListingListSerializer
)
LISTING_DETAIL_RESPONSE = build_success_response_serializer(
    name="KindnessListingDetailResponse", data_serializer=KindnessListingDetailSerializer
)
STORY_LIST_RESPONSE = build_paginated_success_response_serializer(
    name="KindnessStoryListResponse", item_serializer=KindnessStorySerializer
)
BOARD_STATS_RESPONSE = build_success_response_serializer(
    name="KindnessBoardStatsResponse", data_serializer=KindnessBoardStatsSerializer
)
OFFER_RESPONSE = build_success_response_serializer(
    name="KindnessOfferResponse", data_serializer=KindnessOfferSerializer
)
MY_OFFER_LIST_RESPONSE = build_paginated_success_response_serializer(
    name="KindnessMyOfferListResponse", item_serializer=KindnessOfferSerializer
)
ADMIN_LISTING_LIST_RESPONSE = build_paginated_success_response_serializer(
    name="KindnessAdminListingListResponse", item_serializer=KindnessAdminListingSerializer
)
ADMIN_LISTING_DETAIL_RESPONSE = build_success_response_serializer(
    name="KindnessAdminListingDetailResponse", data_serializer=KindnessAdminListingSerializer
)
ADMIN_OFFER_LIST_RESPONSE = build_paginated_success_response_serializer(
    name="KindnessAdminOfferListResponse", item_serializer=KindnessAdminOfferSerializer
)

#: نوع MIME شیت اکسل — همان قراردادی که بقیهٔ خروجی‌های پروژه استفاده می‌کنند.
EXCEL_CONTENT_TYPE = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def _service_error_response(
    exc: Exception, *, status_code: int = status.HTTP_400_BAD_REQUEST
) -> ErrorResponse:
    """تبدیل خطای لایهٔ سرویس به پاسخ خطای استاندارد پروژه."""
    return ErrorResponse(message=str(exc), status_code=status_code)

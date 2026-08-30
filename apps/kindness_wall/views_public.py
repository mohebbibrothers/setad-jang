"""گروه دامنه‌ای `views_public` از views — فاز ۱۱ (تفکیک P3-16).

کلاس‌ها عیناً منتقل شده‌اند؛ مشترکات از views_common؛ نامِ عمومیِ این گروه‌ها را فقط از facade (apps.*.views) یا همین ماژول import کنید.
"""

from __future__ import annotations

from drf_spectacular.utils import extend_schema
from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.core.api_cache import build_cache_variant, cached_public_payload
from apps.core.pagination import StandardPagination
from apps.core.responses import ErrorResponse, SuccessResponse
from apps.core.views import paginated_list_response
from apps.kindness_wall import selectors, services
from apps.kindness_wall.filters import (
    KindnessListingPublicFilter,
)
from apps.kindness_wall.serializers import (
    KindnessCategorySerializer,
    KindnessListingDetailSerializer,
    KindnessListingListSerializer,
    KindnessMatchSerializer,
)
from apps.kindness_wall.throttles import (
    KindnessBrowseAnonThrottle,
    KindnessBrowseUserThrottle,
)

from .views_common import (  # noqa: F401 — re-exportِ رایگان برای بدنه‌های منتقل‌شده
    ANALYTICS_RESPONSE,
    CATEGORY_LIST_RESPONSE,
    CONTACT_REVEAL_RESPONSE,
    EMPTY_RESPONSE,
    ERROR_RESPONSE,
    LISTING_DETAIL_RESPONSE,
    LISTING_LIST_RESPONSE,
    MATCH_LIST_RESPONSE,
    REPORT_RESPONSE,
    TAG_ADMIN,
    TAG_PUBLIC,
    TAG_USER,
    USER_LISTING_DETAIL_RESPONSE,
    _service_error_response,
)


class KindnessCategoryPublicListView(APIView):
    """Public category tree."""

    permission_classes = [AllowAny]
    throttle_classes = [KindnessBrowseAnonThrottle, KindnessBrowseUserThrottle]

    @extend_schema(
        operation_id="kindness_categories_list",
        tags=[TAG_PUBLIC],
        responses={200: CATEGORY_LIST_RESPONSE},
    )
    def get(self, request: Request) -> SuccessResponse:
        """Return active categories."""
        payload = cached_public_payload(
            domain="kindness",
            namespace="kindness:categories",
            parts=("categories",),
            factory=lambda: KindnessCategorySerializer(
                selectors.get_public_categories(), many=True
            ).data,
        )
        return SuccessResponse(data=payload)


class KindnessListingPublicListView(APIView):
    """Public published listing search/list."""

    permission_classes = [AllowAny]
    throttle_classes = [KindnessBrowseAnonThrottle, KindnessBrowseUserThrottle]

    @extend_schema(
        operation_id="kindness_listings_list",
        tags=[TAG_PUBLIC],
        responses={200: LISTING_LIST_RESPONSE},
    )
    def get(self, request: Request) -> Response:
        """Return filtered published listings without phone numbers."""
        base_queryset = selectors.get_public_listings()
        filterset = KindnessListingPublicFilter(request.query_params, queryset=base_queryset)

        def build_payload() -> dict:
            queryset = filterset.qs if filterset.is_valid() else base_queryset
            paginator = StandardPagination()
            page = paginator.paginate_queryset(queryset, request, view=self)
            serializer = KindnessListingListSerializer(page, many=True)
            response = paginator.get_paginated_response(
                serializer.data, message="لیست آگهی‌های دیوار مهربانی دریافت شد."
            )
            return response.data["data"]

        payload = cached_public_payload(
            domain="kindness",
            namespace="kindness:public_list",
            parts=(
                "listings",
                *build_cache_variant(
                    request, filterset=filterset, pagination_class=StandardPagination
                ),
            ),
            factory=build_payload,
        )
        return SuccessResponse(data=payload, message="لیست آگهی‌های دیوار مهربانی دریافت شد.")


class KindnessListingPublicDetailView(APIView):
    """Public listing detail without raw contact phone."""

    permission_classes = [AllowAny]
    throttle_classes = [KindnessBrowseAnonThrottle, KindnessBrowseUserThrottle]

    @extend_schema(
        operation_id="kindness_listings_retrieve",
        tags=[TAG_PUBLIC],
        responses={200: LISTING_DETAIL_RESPONSE, 404: ERROR_RESPONSE},
    )
    def get(self, request: Request, slug: str) -> SuccessResponse | ErrorResponse:
        """Return one published listing and increment view counter."""
        listing = selectors.get_public_listing_by_slug(slug)
        if listing is None:
            return ErrorResponse(message="آگهی یافت نشد.", status_code=status.HTTP_404_NOT_FOUND)
        services.increment_listing_view_count(listing=listing)

        def build_payload() -> dict | None:
            refreshed = selectors.get_public_listing_by_slug(slug)
            if refreshed is None:
                return None
            return KindnessListingDetailSerializer(refreshed).data

        payload = cached_public_payload(
            domain="kindness",
            namespace="kindness:public_detail",
            parts=("listing", slug),
            factory=build_payload,
        )
        if payload is None:
            return ErrorResponse(message="آگهی یافت نشد.", status_code=status.HTTP_404_NOT_FOUND)
        return SuccessResponse(data=payload)


class KindnessListingPublicMatchesView(APIView):
    """Public related matches for a listing."""

    permission_classes = [AllowAny]
    throttle_classes = [KindnessBrowseAnonThrottle, KindnessBrowseUserThrottle]

    @extend_schema(
        operation_id="kindness_listings_matches",
        tags=[TAG_PUBLIC],
        responses={200: MATCH_LIST_RESPONSE, 404: ERROR_RESPONSE},
    )
    def get(self, request: Request, slug: str) -> Response | ErrorResponse:
        """Return active matches for a public listing."""
        listing = selectors.get_public_listing_by_slug(slug)
        if listing is None:
            return ErrorResponse(message="آگهی یافت نشد.", status_code=status.HTTP_404_NOT_FOUND)
        return paginated_list_response(
            request=request,
            view=self,
            queryset=selectors.get_listing_matches(listing=listing),
            serializer_class=KindnessMatchSerializer,
            pagination_class=StandardPagination,
        )

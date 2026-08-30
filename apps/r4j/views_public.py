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

from apps.core.pagination import StandardPagination
from apps.core.responses import (
    ErrorResponse,
    SuccessResponse,
)

from . import selectors
from .filters import (
    R4JCriminalPublicFilter,
)
from .serializers import (
    R4JPublicCriminalDetailSerializer,
    R4JPublicCriminalListSerializer,
)
from .throttles import (
    R4JBrowseAnonThrottle,
    R4JBrowseUserThrottle,
)
from .views_common import (  # noqa: F401 — re-exportِ رایگان برای بدنه‌های منتقل‌شده
    ADMIN_ALIAS_LIST_RESPONSE,
    ADMIN_ALIAS_RESPONSE,
    ADMIN_ATTACHMENT_LIST_RESPONSE,
    ADMIN_ATTACHMENT_RESPONSE,
    ADMIN_BOUNTY_DETAIL_RESPONSE,
    ADMIN_BOUNTY_FILTER_PARAMS,
    ADMIN_BOUNTY_LIST_RESPONSE,
    ADMIN_CUSTODY_EVENT_LIST_RESPONSE,
    ADMIN_CUSTODY_EVENT_RESPONSE,
    ADMIN_DETAIL_RESPONSE,
    ADMIN_LIST_FILTER_PARAMS,
    ADMIN_LIST_RESPONSE,
    ADMIN_PHONE_LIST_RESPONSE,
    ADMIN_PHONE_RESPONSE,
    ADMIN_PHOTO_LIST_RESPONSE,
    ADMIN_PHOTO_RESPONSE,
    ADMIN_REPORT_DETAIL_RESPONSE,
    ADMIN_REPORT_FILTER_PARAMS,
    ADMIN_REPORT_LIST_RESPONSE,
    ADMIN_SOCIAL_LIST_RESPONSE,
    ADMIN_SOCIAL_RESPONSE,
    ADMIN_VISIBILITY_LIST_RESPONSE,
    ADMIN_VISIBILITY_RESPONSE,
    EMPTY_SUCCESS_RESPONSE,
    GENERIC_ERROR_RESPONSE,
    LIST_PAGINATION_PARAMS,
    PUBLIC_DETAIL_RESPONSE,
    PUBLIC_LIST_FILTER_PARAMS,
    PUBLIC_LIST_RESPONSE,
    TAG_R4J_ADMIN,
    TAG_R4J_BOUNTY,
    TAG_R4J_PUBLIC,
    TAG_R4J_USER,
    USER_BOUNTY_DETAIL_RESPONSE,
    USER_BOUNTY_FILTER_PARAMS,
    USER_BOUNTY_LIST_RESPONSE,
    USER_REPORT_DETAIL_RESPONSE,
    USER_REPORT_FILTER_PARAMS,
    USER_REPORT_LIST_RESPONSE,
    _build_filters_signature,
)

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

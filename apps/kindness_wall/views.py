"""API views for Kindness Wall full API layer."""

from __future__ import annotations

from django.http import HttpResponse
from drf_spectacular.utils import extend_schema
from rest_framework import status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.audit_logs import actions as audit_actions
from apps.audit_logs.helpers import extract_audit_metadata
from apps.audit_logs.services import log_action_async
from apps.core.pagination import StandardPagination
from apps.core.responses import CreatedResponse, DeletedResponse, ErrorResponse, SuccessResponse
from apps.core.schemas import (
    build_error_response_serializer,
    build_paginated_success_response_serializer,
    build_success_response_serializer,
)
from apps.kindness_wall import selectors, services
from apps.kindness_wall.export import (
    build_kindness_export_filename,
    build_listings_workbook,
    build_reports_workbook,
)
from apps.kindness_wall.filters import (
    KindnessContactRevealAdminFilter,
    KindnessDuplicateCandidateAdminFilter,
    KindnessListingAdminFilter,
    KindnessListingPublicFilter,
    KindnessMatchAdminFilter,
    KindnessReportAdminFilter,
)
from apps.kindness_wall.permissions import IsKindnessAdminUser
from apps.kindness_wall.serializers import (
    KindnessAdminAnalyticsSerializer,
    KindnessAdminCategoryInputSerializer,
    KindnessAdminContactRevealSerializer,
    KindnessAdminMatchSerializer,
    KindnessAdminReviewSerializer,
    KindnessAdminSuspendSerializer,
    KindnessBookmarkSerializer,
    KindnessCategorySerializer,
    KindnessContactRevealSerializer,
    KindnessDuplicateCandidateSerializer,
    KindnessDuplicateReviewSerializer,
    KindnessListingCreateUpdateSerializer,
    KindnessListingDetailSerializer,
    KindnessListingListSerializer,
    KindnessListingReportCreateSerializer,
    KindnessListingReportSerializer,
    KindnessMatchSerializer,
    KindnessReportReviewInputSerializer,
    KindnessUserListingDetailSerializer,
)
from apps.kindness_wall.throttles import (
    KindnessBrowseAnonThrottle,
    KindnessBrowseUserThrottle,
    KindnessContactRevealThrottle,
    KindnessListingCreateThrottle,
    KindnessReportThrottle,
)

TAG_PUBLIC = "دیوار مهربانی — عمومی"
TAG_USER = "دیوار مهربانی — کاربر"
TAG_ADMIN = "دیوار مهربانی — مدیریت"

ERROR_RESPONSE = build_error_response_serializer(name="KindnessWallErrorResponse")
CATEGORY_LIST_RESPONSE = build_success_response_serializer(name="KindnessCategoryListResponse", data_serializer=KindnessCategorySerializer, many=True)
LISTING_LIST_RESPONSE = build_paginated_success_response_serializer(name="KindnessListingListResponse", item_serializer=KindnessListingListSerializer)
LISTING_DETAIL_RESPONSE = build_success_response_serializer(name="KindnessListingDetailResponse", data_serializer=KindnessListingDetailSerializer)
USER_LISTING_DETAIL_RESPONSE = build_success_response_serializer(name="KindnessUserListingDetailResponse", data_serializer=KindnessUserListingDetailSerializer)
MATCH_LIST_RESPONSE = build_paginated_success_response_serializer(name="KindnessMatchListResponse", item_serializer=KindnessMatchSerializer)
CONTACT_REVEAL_RESPONSE = build_success_response_serializer(name="KindnessContactRevealResponse", data_serializer=KindnessContactRevealSerializer)
REPORT_RESPONSE = build_success_response_serializer(name="KindnessListingReportResponse", data_serializer=KindnessListingReportSerializer)
ANALYTICS_RESPONSE = build_success_response_serializer(name="KindnessAnalyticsResponse", data_serializer=KindnessAdminAnalyticsSerializer)
EMPTY_RESPONSE = build_success_response_serializer(name="KindnessEmptyResponse")


def _service_error_response(exc: Exception, *, status_code: int = status.HTTP_400_BAD_REQUEST) -> ErrorResponse:
    """Convert service-layer exception to project error response."""
    return ErrorResponse(message=str(exc), status_code=status_code)


class KindnessCategoryPublicListView(APIView):
    """Public category tree."""

    permission_classes = [AllowAny]
    throttle_classes = [KindnessBrowseAnonThrottle, KindnessBrowseUserThrottle]

    @extend_schema(operation_id="kindness_categories_list", tags=[TAG_PUBLIC], responses={200: CATEGORY_LIST_RESPONSE})
    def get(self, request: Request) -> SuccessResponse:
        """Return active categories."""
        return SuccessResponse(data=KindnessCategorySerializer(selectors.get_public_categories(), many=True).data)


class KindnessListingPublicListView(APIView):
    """Public published listing search/list."""

    permission_classes = [AllowAny]
    throttle_classes = [KindnessBrowseAnonThrottle, KindnessBrowseUserThrottle]

    @extend_schema(operation_id="kindness_listings_list", tags=[TAG_PUBLIC], responses={200: LISTING_LIST_RESPONSE})
    def get(self, request: Request) -> Response:
        """Return filtered published listings without phone numbers."""
        queryset = selectors.get_public_listings()
        filterset = KindnessListingPublicFilter(request.query_params, queryset=queryset)
        if filterset.is_valid():
            queryset = filterset.qs
        paginator = StandardPagination()
        page = paginator.paginate_queryset(queryset, request, view=self)
        serializer = KindnessListingListSerializer(page, many=True)
        return paginator.get_paginated_response(serializer.data, message="لیست آگهی‌های دیوار مهربانی دریافت شد.")


class KindnessListingPublicDetailView(APIView):
    """Public listing detail without raw contact phone."""

    permission_classes = [AllowAny]
    throttle_classes = [KindnessBrowseAnonThrottle, KindnessBrowseUserThrottle]

    @extend_schema(operation_id="kindness_listings_retrieve", tags=[TAG_PUBLIC], responses={200: LISTING_DETAIL_RESPONSE, 404: ERROR_RESPONSE})
    def get(self, request: Request, slug: str) -> SuccessResponse | ErrorResponse:
        """Return one published listing and increment view counter."""
        listing = selectors.get_public_listing_by_slug(slug)
        if listing is None:
            return ErrorResponse(message="آگهی یافت نشد.", status_code=status.HTTP_404_NOT_FOUND)
        listing = services.increment_listing_view_count(listing=listing)
        return SuccessResponse(data=KindnessListingDetailSerializer(listing).data)


class KindnessListingPublicMatchesView(APIView):
    """Public related matches for a listing."""

    permission_classes = [AllowAny]
    throttle_classes = [KindnessBrowseAnonThrottle, KindnessBrowseUserThrottle]

    @extend_schema(operation_id="kindness_listings_matches", tags=[TAG_PUBLIC], responses={200: MATCH_LIST_RESPONSE, 404: ERROR_RESPONSE})
    def get(self, request: Request, slug: str) -> Response | ErrorResponse:
        """Return active matches for a public listing."""
        listing = selectors.get_public_listing_by_slug(slug)
        if listing is None:
            return ErrorResponse(message="آگهی یافت نشد.", status_code=status.HTTP_404_NOT_FOUND)
        queryset = selectors.get_listing_matches(listing=listing)
        paginator = StandardPagination()
        page = paginator.paginate_queryset(queryset, request, view=self)
        return paginator.get_paginated_response(KindnessMatchSerializer(page, many=True).data)


class KindnessContactRevealView(APIView):
    """Reveal contact phone for authenticated users only."""

    permission_classes = [IsAuthenticated]
    throttle_classes = [KindnessContactRevealThrottle]

    @extend_schema(operation_id="kindness_listings_reveal_contact", tags=[TAG_USER], request=None, responses={200: CONTACT_REVEAL_RESPONSE, 403: ERROR_RESPONSE, 404: ERROR_RESPONSE})
    def post(self, request: Request, slug: str) -> SuccessResponse | ErrorResponse:
        """Reveal phone and record contact reveal audit row."""
        listing = selectors.get_public_listing_by_slug(slug)
        if listing is None:
            return ErrorResponse(message="آگهی یافت نشد.", status_code=status.HTTP_404_NOT_FOUND)
        metadata = extract_audit_metadata(request)
        try:
            reveal = services.reveal_contact(
                listing=listing,
                viewer=request.user,
                ip_address=metadata.get("ip_address"),
                user_agent=metadata.get("user_agent") or "",
                request_id=metadata.get("request_id") or "",
            )
        except (services.KindnessPermissionError, services.KindnessListingStateError) as exc:
            return _service_error_response(exc, status_code=status.HTTP_403_FORBIDDEN)
        log_action_async(user_id=request.user.pk, action=audit_actions.KINDNESS_CONTACT_REVEALED, resource_type="kindness_listing", resource_id=str(listing.pk), extra_data={"listing_owner_id": listing.owner_id}, **metadata)
        return SuccessResponse(data={"phone_number": reveal.phone_snapshot, "listing_id": listing.pk, "owner_full_name": listing.owner_full_name_snapshot}, message="شماره تماس آگهی نمایش داده شد.")


class KindnessListingReportCreateView(APIView):
    """Report a published listing."""

    permission_classes = [IsAuthenticated]
    throttle_classes = [KindnessReportThrottle]

    @extend_schema(operation_id="kindness_listings_report", tags=[TAG_USER], request=KindnessListingReportCreateSerializer, responses={201: REPORT_RESPONSE, 403: ERROR_RESPONSE, 404: ERROR_RESPONSE})
    def post(self, request: Request, slug: str) -> CreatedResponse | ErrorResponse:
        """Create a report for a listing."""
        listing = selectors.get_public_listing_by_slug(slug)
        if listing is None:
            return ErrorResponse(message="آگهی یافت نشد.", status_code=status.HTTP_404_NOT_FOUND)
        serializer = KindnessListingReportCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            report = services.report_listing(listing=listing, reported_by=request.user, **serializer.validated_data)
        except services.KindnessListingStateError as exc:
            return _service_error_response(exc, status_code=status.HTTP_403_FORBIDDEN)
        log_action_async(user_id=request.user.pk, action=audit_actions.KINDNESS_LISTING_REPORTED, resource_type="kindness_listing_report", resource_id=str(report.pk), extra_data={"listing_id": listing.pk}, **extract_audit_metadata(request))
        return CreatedResponse(data=KindnessListingReportSerializer(report).data, message="گزارش شما ثبت شد.")


class KindnessUserListingListCreateView(APIView):
    """User listing dashboard and create endpoint."""

    permission_classes = [IsAuthenticated]
    throttle_classes = [KindnessListingCreateThrottle]

    @extend_schema(operation_id="kindness_user_listings_list", tags=[TAG_USER], responses={200: build_paginated_success_response_serializer(name="KindnessUserListingListResponse", item_serializer=KindnessUserListingDetailSerializer)})
    def get(self, request: Request) -> Response:
        """Return listings owned by current user."""
        queryset = selectors.get_user_listings(user_id=request.user.pk)
        paginator = StandardPagination()
        page = paginator.paginate_queryset(queryset, request, view=self)
        return paginator.get_paginated_response(KindnessUserListingDetailSerializer(page, many=True).data)

    @extend_schema(operation_id="kindness_user_listings_create", tags=[TAG_USER], request=KindnessListingCreateUpdateSerializer, responses={201: USER_LISTING_DETAIL_RESPONSE, 400: ERROR_RESPONSE, 403: ERROR_RESPONSE})
    def post(self, request: Request) -> CreatedResponse | ErrorResponse:
        """Create a draft listing for current user."""
        serializer = KindnessListingCreateUpdateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            listing = services.create_listing(owner=request.user, **serializer.validated_data)
        except services.KindnessProfileIncompleteError as exc:
            return _service_error_response(exc, status_code=status.HTTP_403_FORBIDDEN)
        log_action_async(user_id=request.user.pk, action=audit_actions.KINDNESS_LISTING_CREATED, resource_type="kindness_listing", resource_id=str(listing.pk), **extract_audit_metadata(request))
        return CreatedResponse(data=KindnessUserListingDetailSerializer(listing).data, message="آگهی شما به‌صورت پیش‌نویس ساخته شد.")


class KindnessUserListingDetailView(APIView):
    """User retrieve/update/delete own listing."""

    permission_classes = [IsAuthenticated]
    serializer_class = KindnessUserListingDetailSerializer

    def get(self, request: Request, listing_id: int) -> SuccessResponse | ErrorResponse:
        """Return own listing detail."""
        listing = selectors.get_user_listing_by_id(user_id=request.user.pk, listing_id=listing_id)
        if listing is None:
            return ErrorResponse(message="آگهی یافت نشد.", status_code=status.HTTP_404_NOT_FOUND)
        return SuccessResponse(data=KindnessUserListingDetailSerializer(listing).data)

    def patch(self, request: Request, listing_id: int) -> SuccessResponse | ErrorResponse:
        """Update own listing."""
        listing = selectors.get_user_listing_by_id(user_id=request.user.pk, listing_id=listing_id)
        if listing is None:
            return ErrorResponse(message="آگهی یافت نشد.", status_code=status.HTTP_404_NOT_FOUND)
        serializer = KindnessListingCreateUpdateSerializer(data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        try:
            listing = services.update_listing(listing=listing, user=request.user, **serializer.validated_data)
        except services.KindnessPermissionError as exc:
            return _service_error_response(exc, status_code=status.HTTP_403_FORBIDDEN)
        log_action_async(user_id=request.user.pk, action=audit_actions.KINDNESS_LISTING_UPDATED, resource_type="kindness_listing", resource_id=str(listing.pk), **extract_audit_metadata(request))
        return SuccessResponse(data=KindnessUserListingDetailSerializer(listing).data, message="آگهی بروزرسانی شد.")

    def delete(self, request: Request, listing_id: int) -> DeletedResponse | ErrorResponse:
        """Soft-delete own listing."""
        listing = selectors.get_user_listing_by_id(user_id=request.user.pk, listing_id=listing_id)
        if listing is None:
            return ErrorResponse(message="آگهی یافت نشد.", status_code=status.HTTP_404_NOT_FOUND)
        services.soft_delete_listing(listing=listing, user=request.user)
        log_action_async(user_id=request.user.pk, action=audit_actions.KINDNESS_LISTING_DELETED, resource_type="kindness_listing", resource_id=str(listing.pk), **extract_audit_metadata(request))
        return DeletedResponse(message="آگهی حذف شد.")


class KindnessUserListingSubmitView(APIView):
    """Submit own listing for admin review."""

    permission_classes = [IsAuthenticated]
    serializer_class = KindnessUserListingDetailSerializer

    def post(self, request: Request, listing_id: int) -> SuccessResponse | ErrorResponse:
        """Submit listing for review."""
        listing = selectors.get_user_listing_by_id(user_id=request.user.pk, listing_id=listing_id)
        if listing is None:
            return ErrorResponse(message="آگهی یافت نشد.", status_code=status.HTTP_404_NOT_FOUND)
        try:
            listing = services.submit_listing_for_review(listing=listing, user=request.user)
        except (services.KindnessPermissionError, services.KindnessListingStateError) as exc:
            return _service_error_response(exc)
        log_action_async(user_id=request.user.pk, action=audit_actions.KINDNESS_LISTING_SUBMITTED, resource_type="kindness_listing", resource_id=str(listing.pk), **extract_audit_metadata(request))
        return SuccessResponse(data=KindnessUserListingDetailSerializer(listing).data, message="آگهی برای بررسی ادمین ارسال شد.")


class KindnessUserListingRenewView(APIView):
    """Renew own listing."""

    permission_classes = [IsAuthenticated]
    serializer_class = KindnessUserListingDetailSerializer

    def post(self, request: Request, listing_id: int) -> SuccessResponse | ErrorResponse:
        """Renew listing expiration."""
        listing = selectors.get_user_listing_by_id(user_id=request.user.pk, listing_id=listing_id)
        if listing is None:
            return ErrorResponse(message="آگهی یافت نشد.", status_code=status.HTTP_404_NOT_FOUND)
        try:
            listing = services.renew_listing(listing=listing, user=request.user)
        except (services.KindnessPermissionError, services.KindnessListingStateError) as exc:
            return _service_error_response(exc)
        return SuccessResponse(data=KindnessUserListingDetailSerializer(listing).data, message="آگهی تمدید شد و در صورت نیاز برای بررسی ارسال شد.")


class KindnessUserListingCloseView(APIView):
    """Close own listing without deleting historical workflow data."""

    permission_classes = [IsAuthenticated]
    serializer_class = KindnessUserListingDetailSerializer

    @extend_schema(operation_id="kindness_user_listings_close", tags=[TAG_USER], request=None, responses={200: USER_LISTING_DETAIL_RESPONSE, 403: ERROR_RESPONSE, 404: ERROR_RESPONSE})
    def post(self, request: Request, listing_id: int) -> SuccessResponse | ErrorResponse:
        """Close a listing by its owner."""
        listing = selectors.get_user_listing_by_id(user_id=request.user.pk, listing_id=listing_id)
        if listing is None:
            return ErrorResponse(message="آگهی یافت نشد.", status_code=status.HTTP_404_NOT_FOUND)
        try:
            listing = services.close_listing(listing=listing, user=request.user)
        except (services.KindnessPermissionError, services.KindnessListingStateError) as exc:
            return _service_error_response(exc, status_code=status.HTTP_403_FORBIDDEN)
        log_action_async(user_id=request.user.pk, action=audit_actions.KINDNESS_LISTING_CLOSED, resource_type="kindness_listing", resource_id=str(listing.pk), **extract_audit_metadata(request))
        return SuccessResponse(data=KindnessUserListingDetailSerializer(listing).data, message="آگهی بسته شد.")


class KindnessBookmarkView(APIView):
    """Create/delete bookmark for public listing."""

    permission_classes = [IsAuthenticated]
    serializer_class = KindnessListingDetailSerializer

    def post(self, request: Request, slug: str) -> CreatedResponse | ErrorResponse:
        """Bookmark listing."""
        listing = selectors.get_public_listing_by_slug(slug)
        if listing is None:
            return ErrorResponse(message="آگهی یافت نشد.", status_code=status.HTTP_404_NOT_FOUND)
        bookmark = services.create_bookmark(listing=listing, user=request.user)
        log_action_async(user_id=request.user.pk, action=audit_actions.KINDNESS_BOOKMARK_CREATED, resource_type="kindness_bookmark", resource_id=str(bookmark.pk), extra_data={"listing_id": listing.pk}, **extract_audit_metadata(request))
        return CreatedResponse(data={"listing_id": listing.pk}, message="آگهی ذخیره شد.")

    def delete(self, request: Request, slug: str) -> DeletedResponse | ErrorResponse:
        """Remove bookmark."""
        listing = selectors.get_public_listing_by_slug(slug)
        if listing is None:
            return ErrorResponse(message="آگهی یافت نشد.", status_code=status.HTTP_404_NOT_FOUND)
        services.delete_bookmark(listing=listing, user=request.user)
        log_action_async(user_id=request.user.pk, action=audit_actions.KINDNESS_BOOKMARK_DELETED, resource_type="kindness_listing", resource_id=str(listing.pk), **extract_audit_metadata(request))
        return DeletedResponse(message="آگهی از ذخیره‌ها حذف شد.")


class KindnessUserBookmarkListView(APIView):
    """Current user's saved Kindness Wall listings."""

    permission_classes = [IsAuthenticated]
    serializer_class = KindnessBookmarkSerializer

    @extend_schema(operation_id="kindness_user_bookmarks_list", tags=[TAG_USER], responses={200: build_paginated_success_response_serializer(name="KindnessUserBookmarkListResponse", item_serializer=KindnessBookmarkSerializer)})
    def get(self, request: Request) -> Response:
        """Return bookmarked published listings for current user."""
        queryset = selectors.get_user_bookmarks(user_id=request.user.pk)
        paginator = StandardPagination()
        page = paginator.paginate_queryset(queryset, request, view=self)
        return paginator.get_paginated_response(KindnessBookmarkSerializer(page, many=True).data)


class KindnessUserMatchListView(APIView):
    """Current user's active listing matches."""

    permission_classes = [IsAuthenticated]
    serializer_class = KindnessMatchSerializer

    def get(self, request: Request) -> Response:
        """Return active matches for user's listings."""
        queryset = selectors.get_user_matches(user_id=request.user.pk)
        paginator = StandardPagination()
        page = paginator.paginate_queryset(queryset, request, view=self)
        return paginator.get_paginated_response(KindnessMatchSerializer(page, many=True).data)


class KindnessMatchDismissView(APIView):
    """Dismiss a match."""

    permission_classes = [IsAuthenticated]
    serializer_class = KindnessMatchSerializer

    def post(self, request: Request, match_id: int) -> SuccessResponse | ErrorResponse:
        """Dismiss a match owned by user's source listing."""
        match = selectors.get_match_by_id(match_id=match_id)
        if match is None:
            return ErrorResponse(message="پیشنهاد تطبیق یافت نشد.", status_code=status.HTTP_404_NOT_FOUND)
        try:
            match = services.dismiss_match(match=match, user=request.user)
        except services.KindnessPermissionError as exc:
            return _service_error_response(exc, status_code=status.HTTP_403_FORBIDDEN)
        return SuccessResponse(data=KindnessMatchSerializer(match).data, message="پیشنهاد نادیده گرفته شد.")


class KindnessMatchContactedView(APIView):
    """Mark match as contacted."""

    permission_classes = [IsAuthenticated]
    serializer_class = KindnessMatchSerializer

    def post(self, request: Request, match_id: int) -> SuccessResponse | ErrorResponse:
        """Mark a match as contacted."""
        match = selectors.get_match_by_id(match_id=match_id)
        if match is None:
            return ErrorResponse(message="پیشنهاد تطبیق یافت نشد.", status_code=status.HTTP_404_NOT_FOUND)
        try:
            match = services.mark_match_contacted(match=match, user=request.user)
        except services.KindnessPermissionError as exc:
            return _service_error_response(exc, status_code=status.HTTP_403_FORBIDDEN)
        return SuccessResponse(data=KindnessMatchSerializer(match).data, message="پیشنهاد به‌عنوان تماس‌گرفته‌شده ثبت شد.")


class KindnessAdminCategoryListCreateView(APIView):
    """Admin category tree list/create endpoint."""

    permission_classes = [IsKindnessAdminUser]
    serializer_class = KindnessCategorySerializer

    @extend_schema(operation_id="kindness_admin_categories_list", tags=[TAG_ADMIN], responses={200: CATEGORY_LIST_RESPONSE})
    def get(self, request: Request) -> SuccessResponse:
        """Return all active/inactive categories for tree management."""
        return SuccessResponse(data=KindnessCategorySerializer(selectors.get_admin_categories(), many=True).data)

    @extend_schema(operation_id="kindness_admin_categories_create", tags=[TAG_ADMIN], request=KindnessAdminCategoryInputSerializer, responses={201: build_success_response_serializer(name="KindnessAdminCategoryResponse", data_serializer=KindnessCategorySerializer), 400: ERROR_RESPONSE})
    def post(self, request: Request) -> CreatedResponse | ErrorResponse:
        """Create a tree category via service layer."""
        serializer = KindnessAdminCategoryInputSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            category = services.create_category(**serializer.validated_data)
        except services.KindnessCategoryTreeError as exc:
            return _service_error_response(exc)
        log_action_async(user_id=request.user.pk, action=audit_actions.KINDNESS_CATEGORY_CREATED, resource_type="kindness_category", resource_id=str(category.pk), **extract_audit_metadata(request))
        return CreatedResponse(data=KindnessCategorySerializer(category).data, message="دسته‌بندی دیوار مهربانی ساخته شد.")


class KindnessAdminCategoryDetailView(APIView):
    """Admin category retrieve/update/deactivate endpoint."""

    permission_classes = [IsKindnessAdminUser]
    serializer_class = KindnessCategorySerializer

    def get(self, request: Request, category_id: int) -> SuccessResponse | ErrorResponse:
        """Return one category for admin editing."""
        category = selectors.get_admin_category_by_id(category_id=category_id)
        if category is None:
            return ErrorResponse(message="دسته‌بندی یافت نشد.", status_code=status.HTTP_404_NOT_FOUND)
        return SuccessResponse(data=KindnessCategorySerializer(category).data)

    def patch(self, request: Request, category_id: int) -> SuccessResponse | ErrorResponse:
        """Update category metadata/tree location."""
        category = selectors.get_admin_category_by_id(category_id=category_id)
        if category is None:
            return ErrorResponse(message="دسته‌بندی یافت نشد.", status_code=status.HTTP_404_NOT_FOUND)
        serializer = KindnessAdminCategoryInputSerializer(data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        try:
            if serializer.validated_data.get("is_active") is True and not category.is_active:
                category = services.restore_category(category=category)
                remaining = {key: value for key, value in serializer.validated_data.items() if key != "is_active"}
                if remaining:
                    category = services.update_category(category=category, **remaining)
            elif serializer.validated_data.get("is_active") is False and category.is_active:
                category = services.deactivate_category(category=category)
                remaining = {key: value for key, value in serializer.validated_data.items() if key != "is_active"}
                if remaining:
                    category = services.update_category(category=category, **remaining)
            else:
                category = services.update_category(category=category, **serializer.validated_data)
        except services.KindnessCategoryTreeError as exc:
            return _service_error_response(exc)
        log_action_async(user_id=request.user.pk, action=audit_actions.KINDNESS_CATEGORY_UPDATED, resource_type="kindness_category", resource_id=str(category.pk), **extract_audit_metadata(request))
        return SuccessResponse(data=KindnessCategorySerializer(category).data, message="دسته‌بندی بروزرسانی شد.")

    def delete(self, request: Request, category_id: int) -> DeletedResponse | ErrorResponse:
        """Soft-delete/deactivate category with hierarchy safety checks."""
        category = selectors.get_admin_category_by_id(category_id=category_id)
        if category is None:
            return ErrorResponse(message="دسته‌بندی یافت نشد.", status_code=status.HTTP_404_NOT_FOUND)
        try:
            services.deactivate_category(category=category)
        except services.KindnessCategoryTreeError as exc:
            return _service_error_response(exc)
        log_action_async(user_id=request.user.pk, action=audit_actions.KINDNESS_CATEGORY_DELETED, resource_type="kindness_category", resource_id=str(category.pk), **extract_audit_metadata(request))
        return DeletedResponse(message="دسته‌بندی غیرفعال شد.")


class KindnessAdminListingListView(APIView):
    """Admin list all listings."""

    permission_classes = [IsKindnessAdminUser]
    serializer_class = KindnessUserListingDetailSerializer

    @extend_schema(operation_id="kindness_admin_listings_list", tags=[TAG_ADMIN], responses={200: build_paginated_success_response_serializer(name="KindnessAdminListingListResponse", item_serializer=KindnessUserListingDetailSerializer)})
    def get(self, request: Request) -> Response:
        """Return admin listing list."""
        queryset = selectors.get_admin_listings()
        filterset = KindnessListingAdminFilter(request.query_params, queryset=queryset)
        if filterset.is_valid():
            queryset = filterset.qs
        paginator = StandardPagination()
        page = paginator.paginate_queryset(queryset, request, view=self)
        return paginator.get_paginated_response(KindnessUserListingDetailSerializer(page, many=True).data)


class KindnessAdminListingDetailView(APIView):
    """Admin retrieve listing."""

    permission_classes = [IsKindnessAdminUser]
    serializer_class = KindnessUserListingDetailSerializer

    @extend_schema(operation_id="kindness_admin_listings_retrieve", tags=[TAG_ADMIN], responses={200: USER_LISTING_DETAIL_RESPONSE, 404: ERROR_RESPONSE})
    def get(self, request: Request, listing_id: int) -> SuccessResponse | ErrorResponse:
        """Return one listing for admin."""
        listing = selectors.get_admin_listing_by_id(listing_id)
        if listing is None:
            return ErrorResponse(message="آگهی یافت نشد.", status_code=status.HTTP_404_NOT_FOUND)
        return SuccessResponse(data=KindnessUserListingDetailSerializer(listing).data)


class KindnessAdminListingApproveView(APIView):
    """Admin approve listing."""

    permission_classes = [IsKindnessAdminUser]
    serializer_class = KindnessUserListingDetailSerializer

    def post(self, request: Request, listing_id: int) -> SuccessResponse | ErrorResponse:
        """Approve listing."""
        listing = selectors.get_admin_listing_by_id(listing_id)
        if listing is None:
            return ErrorResponse(message="آگهی یافت نشد.", status_code=status.HTTP_404_NOT_FOUND)
        serializer = KindnessAdminReviewSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            listing = services.approve_listing(listing=listing, admin=request.user, admin_note=serializer.validated_data.get("admin_note", ""))
        except services.KindnessListingStateError as exc:
            return _service_error_response(exc)
        log_action_async(user_id=request.user.pk, action=audit_actions.KINDNESS_LISTING_APPROVED, resource_type="kindness_listing", resource_id=str(listing.pk), **extract_audit_metadata(request))
        return SuccessResponse(data=KindnessUserListingDetailSerializer(listing).data, message="آگهی منتشر شد.")


class KindnessAdminListingRejectView(APIView):
    """Admin reject listing."""

    permission_classes = [IsKindnessAdminUser]
    serializer_class = KindnessUserListingDetailSerializer

    def post(self, request: Request, listing_id: int) -> SuccessResponse | ErrorResponse:
        """Reject listing."""
        listing = selectors.get_admin_listing_by_id(listing_id)
        if listing is None:
            return ErrorResponse(message="آگهی یافت نشد.", status_code=status.HTTP_404_NOT_FOUND)
        serializer = KindnessAdminReviewSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            listing = services.reject_listing(listing=listing, admin=request.user, reason=serializer.validated_data.get("reason", ""), needs_edit=serializer.validated_data.get("needs_edit", False))
        except services.KindnessListingStateError as exc:
            return _service_error_response(exc)
        log_action_async(user_id=request.user.pk, action=audit_actions.KINDNESS_LISTING_REJECTED, resource_type="kindness_listing", resource_id=str(listing.pk), **extract_audit_metadata(request))
        return SuccessResponse(data=KindnessUserListingDetailSerializer(listing).data, message="آگهی رد شد.")


class KindnessAdminListingSuspendView(APIView):
    """Admin suspend listing."""

    permission_classes = [IsKindnessAdminUser]
    serializer_class = KindnessUserListingDetailSerializer

    def post(self, request: Request, listing_id: int) -> SuccessResponse | ErrorResponse:
        """Suspend listing."""
        listing = selectors.get_admin_listing_by_id(listing_id)
        if listing is None:
            return ErrorResponse(message="آگهی یافت نشد.", status_code=status.HTTP_404_NOT_FOUND)
        serializer = KindnessAdminSuspendSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            listing = services.suspend_listing(listing=listing, admin=request.user, reason=serializer.validated_data["reason"])
        except services.KindnessListingStateError as exc:
            return _service_error_response(exc)
        log_action_async(user_id=request.user.pk, action=audit_actions.KINDNESS_LISTING_SUSPENDED, resource_type="kindness_listing", resource_id=str(listing.pk), **extract_audit_metadata(request))
        return SuccessResponse(data=KindnessUserListingDetailSerializer(listing).data, message="آگهی تعلیق شد.")


class KindnessAdminListingRestoreView(APIView):
    """Admin restore suspended listing."""

    permission_classes = [IsKindnessAdminUser]
    serializer_class = KindnessUserListingDetailSerializer

    def post(self, request: Request, listing_id: int) -> SuccessResponse | ErrorResponse:
        """Restore listing."""
        listing = selectors.get_admin_listing_by_id(listing_id)
        if listing is None:
            return ErrorResponse(message="آگهی یافت نشد.", status_code=status.HTTP_404_NOT_FOUND)
        try:
            listing = services.restore_suspended_listing(listing=listing, admin=request.user)
        except services.KindnessListingStateError as exc:
            return _service_error_response(exc)
        return SuccessResponse(data=KindnessUserListingDetailSerializer(listing).data, message="آگهی بازگردانی شد.")


class KindnessAdminReportListView(APIView):
    """Admin report queue."""

    permission_classes = [IsKindnessAdminUser]
    serializer_class = KindnessListingReportSerializer

    def get(self, request: Request) -> Response:
        """Return listing reports."""
        queryset = selectors.get_admin_reports()
        filterset = KindnessReportAdminFilter(request.query_params, queryset=queryset)
        if filterset.is_valid():
            queryset = filterset.qs
        paginator = StandardPagination()
        page = paginator.paginate_queryset(queryset, request, view=self)
        return paginator.get_paginated_response(KindnessListingReportSerializer(page, many=True).data)


class KindnessAdminReportReviewView(APIView):
    """Admin review listing report."""

    permission_classes = [IsKindnessAdminUser]
    serializer_class = KindnessListingReportSerializer

    def post(self, request: Request, report_id: int) -> SuccessResponse | ErrorResponse:
        """Review report and optionally suspend listing."""
        report = selectors.get_admin_report_by_id(report_id=report_id)
        if report is None:
            return ErrorResponse(message="گزارش یافت نشد.", status_code=status.HTTP_404_NOT_FOUND)
        serializer = KindnessReportReviewInputSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        report = services.review_listing_report(
            report=report,
            admin=request.user,
            status=serializer.validated_data["status"],
            admin_note=serializer.validated_data.get("admin_note", ""),
            suspend_listing_on_review=serializer.validated_data.get("suspend_listing", False),
        )
        log_action_async(user_id=request.user.pk, action=audit_actions.KINDNESS_REPORT_REVIEWED, resource_type="kindness_listing_report", resource_id=str(report.pk), **extract_audit_metadata(request))
        return SuccessResponse(data=KindnessListingReportSerializer(report).data, message="گزارش بررسی شد.")


class KindnessAdminAnalyticsView(APIView):
    """Admin analytics summary."""

    permission_classes = [IsKindnessAdminUser]
    serializer_class = KindnessAdminAnalyticsSerializer

    def get(self, request: Request) -> SuccessResponse:
        """Return analytics summary."""
        return SuccessResponse(data=services.get_admin_analytics_summary())


class KindnessAdminMatchListView(APIView):
    """Admin list/filter generated matches."""

    permission_classes = [IsKindnessAdminUser]
    serializer_class = KindnessAdminMatchSerializer

    @extend_schema(operation_id="kindness_admin_matches_list", tags=[TAG_ADMIN], responses={200: build_paginated_success_response_serializer(name="KindnessAdminMatchListResponse", item_serializer=KindnessAdminMatchSerializer)})
    def get(self, request: Request) -> Response:
        """Return all matches with professional moderation filters."""
        queryset = selectors.get_admin_matches()
        filterset = KindnessMatchAdminFilter(request.query_params, queryset=queryset)
        if filterset.is_valid():
            queryset = filterset.qs
        paginator = StandardPagination()
        page = paginator.paginate_queryset(queryset, request, view=self)
        return paginator.get_paginated_response(KindnessAdminMatchSerializer(page, many=True).data)


class KindnessAdminMatchDetailView(APIView):
    """Admin match detail endpoint."""

    permission_classes = [IsKindnessAdminUser]
    serializer_class = KindnessAdminMatchSerializer

    @extend_schema(operation_id="kindness_admin_matches_retrieve", tags=[TAG_ADMIN], responses={200: build_success_response_serializer(name="KindnessAdminMatchDetailResponse", data_serializer=KindnessAdminMatchSerializer), 404: ERROR_RESPONSE})
    def get(self, request: Request, match_id: int) -> SuccessResponse | ErrorResponse:
        """Return one match with source/target listing context."""
        match = selectors.get_admin_match_by_id(match_id=match_id)
        if match is None:
            return ErrorResponse(message="پیشنهاد تطبیق یافت نشد.", status_code=status.HTTP_404_NOT_FOUND)
        return SuccessResponse(data=KindnessAdminMatchSerializer(match).data)


class KindnessAdminContactRevealListView(APIView):
    """Admin contact reveal audit trail."""

    permission_classes = [IsKindnessAdminUser]
    serializer_class = KindnessAdminContactRevealSerializer

    @extend_schema(operation_id="kindness_admin_contact_reveals_list", tags=[TAG_ADMIN], responses={200: build_paginated_success_response_serializer(name="KindnessAdminContactRevealListResponse", item_serializer=KindnessAdminContactRevealSerializer)})
    def get(self, request: Request) -> Response:
        """Return paginated contact reveal records."""
        queryset = selectors.get_admin_contact_reveals()
        filterset = KindnessContactRevealAdminFilter(request.query_params, queryset=queryset)
        if filterset.is_valid():
            queryset = filterset.qs
        paginator = StandardPagination()
        page = paginator.paginate_queryset(queryset, request, view=self)
        return paginator.get_paginated_response(KindnessAdminContactRevealSerializer(page, many=True).data)


class KindnessAdminDuplicateCandidateListView(APIView):
    """Admin list likely duplicate listing candidates."""

    permission_classes = [IsKindnessAdminUser]
    serializer_class = KindnessDuplicateCandidateSerializer

    @extend_schema(operation_id="kindness_admin_duplicates_list", tags=[TAG_ADMIN], responses={200: build_paginated_success_response_serializer(name="KindnessAdminDuplicateListResponse", item_serializer=KindnessDuplicateCandidateSerializer)})
    def get(self, request: Request) -> Response:
        """Return duplicate candidates generated by the matching engine."""
        queryset = selectors.get_admin_duplicate_candidates()
        filterset = KindnessDuplicateCandidateAdminFilter(request.query_params, queryset=queryset)
        if filterset.is_valid():
            queryset = filterset.qs
        paginator = StandardPagination()
        page = paginator.paginate_queryset(queryset, request, view=self)
        return paginator.get_paginated_response(KindnessDuplicateCandidateSerializer(page, many=True).data)


class KindnessAdminDuplicateCandidateReviewView(APIView):
    """Admin review endpoint for duplicate candidates."""

    permission_classes = [IsKindnessAdminUser]
    serializer_class = KindnessDuplicateCandidateSerializer

    @extend_schema(operation_id="kindness_admin_duplicates_review", tags=[TAG_ADMIN], request=KindnessDuplicateReviewSerializer, responses={200: build_success_response_serializer(name="KindnessAdminDuplicateReviewResponse", data_serializer=KindnessDuplicateCandidateSerializer), 404: ERROR_RESPONSE})
    def post(self, request: Request, duplicate_id: int) -> SuccessResponse | ErrorResponse:
        """Confirm or dismiss a likely duplicate candidate."""
        duplicate = selectors.get_admin_duplicate_candidate_by_id(duplicate_id=duplicate_id)
        if duplicate is None:
            return ErrorResponse(message="کاندیدای تکراری یافت نشد.", status_code=status.HTTP_404_NOT_FOUND)
        serializer = KindnessDuplicateReviewSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            duplicate = services.review_duplicate_candidate(duplicate=duplicate, **serializer.validated_data)
        except services.KindnessListingStateError as exc:
            return _service_error_response(exc)
        log_action_async(user_id=request.user.pk, action=audit_actions.KINDNESS_DUPLICATE_REVIEWED, resource_type="kindness_duplicate_candidate", resource_id=str(duplicate.pk), **extract_audit_metadata(request))
        return SuccessResponse(data=KindnessDuplicateCandidateSerializer(duplicate).data, message="وضعیت کاندیدای تکراری بروزرسانی شد.")


class KindnessAdminListingExportView(APIView):
    """Admin Excel export for listings."""

    permission_classes = [IsKindnessAdminUser]

    @extend_schema(operation_id="kindness_admin_listings_export", tags=[TAG_ADMIN], responses={200: None})
    def get(self, request: Request) -> HttpResponse:
        """Export filtered listings as an RTL Excel workbook."""
        queryset = selectors.get_admin_listings()
        filterset = KindnessListingAdminFilter(request.query_params, queryset=queryset)
        if filterset.is_valid():
            queryset = filterset.qs
        workbook = build_listings_workbook(listings=queryset)
        filename = build_kindness_export_filename(export_type="listings")
        log_action_async(user_id=request.user.pk, action=audit_actions.KINDNESS_LISTINGS_EXPORTED, resource_type="kindness_listing", resource_id="bulk", extra_data={"filename": filename}, **extract_audit_metadata(request))
        response = HttpResponse(workbook.getvalue(), content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
        response["Content-Disposition"] = f'attachment; filename="{filename}"'
        return response


class KindnessAdminReportExportView(APIView):
    """Admin Excel export for moderation reports."""

    permission_classes = [IsKindnessAdminUser]

    @extend_schema(operation_id="kindness_admin_reports_export", tags=[TAG_ADMIN], responses={200: None})
    def get(self, request: Request) -> HttpResponse:
        """Export filtered reports as an RTL Excel workbook."""
        queryset = selectors.get_admin_reports()
        filterset = KindnessReportAdminFilter(request.query_params, queryset=queryset)
        if filterset.is_valid():
            queryset = filterset.qs
        workbook = build_reports_workbook(reports=queryset)
        filename = build_kindness_export_filename(export_type="reports")
        log_action_async(user_id=request.user.pk, action=audit_actions.KINDNESS_REPORTS_EXPORTED, resource_type="kindness_listing_report", resource_id="bulk", extra_data={"filename": filename}, **extract_audit_metadata(request))
        response = HttpResponse(workbook.getvalue(), content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
        response["Content-Disposition"] = f'attachment; filename="{filename}"'
        return response

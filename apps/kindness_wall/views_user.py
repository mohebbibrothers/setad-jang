"""گروه دامنه‌ای `views_user` از views — فاز ۱۱ (تفکیک P3-16).

کلاس‌ها عیناً منتقل شده‌اند؛ مشترکات از views_common؛ نامِ عمومیِ این گروه‌ها را فقط از facade (apps.*.views) یا همین ماژول import کنید.
"""

from __future__ import annotations

from drf_spectacular.utils import extend_schema
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.audit_logs import actions as audit_actions
from apps.audit_logs.helpers import extract_audit_metadata
from apps.audit_logs.services import log_action_async
from apps.core.pagination import StandardPagination
from apps.core.responses import CreatedResponse, DeletedResponse, ErrorResponse, SuccessResponse
from apps.core.schemas import (
    build_paginated_success_response_serializer,
)
from apps.core.views import paginated_list_response
from apps.kindness_wall import selectors, services
from apps.kindness_wall.serializers import (
    KindnessBookmarkSerializer,
    KindnessListingCreateUpdateSerializer,
    KindnessMatchSerializer,
    KindnessUserListingDetailSerializer,
)
from apps.kindness_wall.throttles import (
    KindnessListingCreateThrottle,
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


class KindnessUserListingListCreateView(APIView):
    """User listing dashboard and create endpoint."""

    permission_classes = [IsAuthenticated]
    throttle_classes = [KindnessListingCreateThrottle]

    @extend_schema(
        operation_id="kindness_user_listings_list",
        tags=[TAG_USER],
        responses={
            200: build_paginated_success_response_serializer(
                name="KindnessUserListingListResponse",
                item_serializer=KindnessUserListingDetailSerializer,
            )
        },
    )
    def get(self, request: Request) -> Response:
        """Return listings owned by current user."""
        return paginated_list_response(
            request=request,
            view=self,
            queryset=selectors.get_user_listings(user_id=request.user.pk),
            serializer_class=KindnessUserListingDetailSerializer,
            pagination_class=StandardPagination,
        )

    @extend_schema(
        operation_id="kindness_user_listings_create",
        tags=[TAG_USER],
        request=KindnessListingCreateUpdateSerializer,
        responses={201: USER_LISTING_DETAIL_RESPONSE, 400: ERROR_RESPONSE, 403: ERROR_RESPONSE},
    )
    def post(self, request: Request) -> CreatedResponse | ErrorResponse:
        """Create a draft listing for current user."""
        serializer = KindnessListingCreateUpdateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            listing = services.create_listing(owner=request.user, **serializer.validated_data)
        except services.KindnessProfileIncompleteError as exc:
            return _service_error_response(exc, status_code=status.HTTP_403_FORBIDDEN)
        log_action_async(
            user_id=request.user.pk,
            action=audit_actions.KINDNESS_LISTING_CREATED,
            resource_type="kindness_listing",
            resource_id=str(listing.pk),
            **extract_audit_metadata(request),
        )
        return CreatedResponse(
            data=KindnessUserListingDetailSerializer(listing).data,
            message="آگهی شما به‌صورت پیش‌نویس ساخته شد.",
        )


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
            listing = services.update_listing(
                listing=listing, user=request.user, **serializer.validated_data
            )
        except services.KindnessPermissionError as exc:
            return _service_error_response(exc, status_code=status.HTTP_403_FORBIDDEN)
        log_action_async(
            user_id=request.user.pk,
            action=audit_actions.KINDNESS_LISTING_UPDATED,
            resource_type="kindness_listing",
            resource_id=str(listing.pk),
            **extract_audit_metadata(request),
        )
        return SuccessResponse(
            data=KindnessUserListingDetailSerializer(listing).data, message="آگهی بروزرسانی شد."
        )

    def delete(self, request: Request, listing_id: int) -> DeletedResponse | ErrorResponse:
        """Soft-delete own listing."""
        listing = selectors.get_user_listing_by_id(user_id=request.user.pk, listing_id=listing_id)
        if listing is None:
            return ErrorResponse(message="آگهی یافت نشد.", status_code=status.HTTP_404_NOT_FOUND)
        services.soft_delete_listing(listing=listing, user=request.user)
        log_action_async(
            user_id=request.user.pk,
            action=audit_actions.KINDNESS_LISTING_DELETED,
            resource_type="kindness_listing",
            resource_id=str(listing.pk),
            **extract_audit_metadata(request),
        )
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
        log_action_async(
            user_id=request.user.pk,
            action=audit_actions.KINDNESS_LISTING_SUBMITTED,
            resource_type="kindness_listing",
            resource_id=str(listing.pk),
            **extract_audit_metadata(request),
        )
        return SuccessResponse(
            data=KindnessUserListingDetailSerializer(listing).data,
            message="آگهی برای بررسی ادمین ارسال شد.",
        )


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
        return SuccessResponse(
            data=KindnessUserListingDetailSerializer(listing).data,
            message="آگهی تمدید شد و در صورت نیاز برای بررسی ارسال شد.",
        )


class KindnessUserListingCloseView(APIView):
    """Close own listing without deleting historical workflow data."""

    permission_classes = [IsAuthenticated]
    serializer_class = KindnessUserListingDetailSerializer

    @extend_schema(
        operation_id="kindness_user_listings_close",
        tags=[TAG_USER],
        request=None,
        responses={200: USER_LISTING_DETAIL_RESPONSE, 403: ERROR_RESPONSE, 404: ERROR_RESPONSE},
    )
    def post(self, request: Request, listing_id: int) -> SuccessResponse | ErrorResponse:
        """Close a listing by its owner."""
        listing = selectors.get_user_listing_by_id(user_id=request.user.pk, listing_id=listing_id)
        if listing is None:
            return ErrorResponse(message="آگهی یافت نشد.", status_code=status.HTTP_404_NOT_FOUND)
        try:
            listing = services.close_listing(listing=listing, user=request.user)
        except (services.KindnessPermissionError, services.KindnessListingStateError) as exc:
            return _service_error_response(exc, status_code=status.HTTP_403_FORBIDDEN)
        log_action_async(
            user_id=request.user.pk,
            action=audit_actions.KINDNESS_LISTING_CLOSED,
            resource_type="kindness_listing",
            resource_id=str(listing.pk),
            **extract_audit_metadata(request),
        )
        return SuccessResponse(
            data=KindnessUserListingDetailSerializer(listing).data, message="آگهی بسته شد."
        )


class KindnessUserBookmarkListView(APIView):
    """Current user's saved Kindness Wall listings."""

    permission_classes = [IsAuthenticated]
    serializer_class = KindnessBookmarkSerializer

    @extend_schema(
        operation_id="kindness_user_bookmarks_list",
        tags=[TAG_USER],
        responses={
            200: build_paginated_success_response_serializer(
                name="KindnessUserBookmarkListResponse", item_serializer=KindnessBookmarkSerializer
            )
        },
    )
    def get(self, request: Request) -> Response:
        """Return bookmarked published listings for current user."""
        return paginated_list_response(
            request=request,
            view=self,
            queryset=selectors.get_user_bookmarks(user_id=request.user.pk),
            serializer_class=KindnessBookmarkSerializer,
            pagination_class=StandardPagination,
        )


class KindnessUserMatchListView(APIView):
    """Current user's active listing matches."""

    permission_classes = [IsAuthenticated]
    serializer_class = KindnessMatchSerializer

    def get(self, request: Request) -> Response:
        """Return active matches for user's listings."""
        return paginated_list_response(
            request=request,
            view=self,
            queryset=selectors.get_user_matches(user_id=request.user.pk),
            serializer_class=KindnessMatchSerializer,
            pagination_class=StandardPagination,
        )

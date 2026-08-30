"""گروه دامنه‌ای `views_engagement` از views — فاز ۱۱ (تفکیک P3-16).

کلاس‌ها عیناً منتقل شده‌اند؛ مشترکات از views_common؛ نامِ عمومیِ این گروه‌ها را فقط از facade (apps.*.views) یا همین ماژول import کنید.
"""

from __future__ import annotations

from drf_spectacular.utils import extend_schema
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.views import APIView

from apps.audit_logs import actions as audit_actions
from apps.audit_logs.helpers import extract_audit_metadata
from apps.audit_logs.services import log_action_async
from apps.core.responses import CreatedResponse, DeletedResponse, ErrorResponse, SuccessResponse
from apps.kindness_wall import selectors, services
from apps.kindness_wall.serializers import (
    KindnessListingDetailSerializer,
    KindnessListingReportCreateSerializer,
    KindnessListingReportSerializer,
    KindnessMatchSerializer,
)
from apps.kindness_wall.throttles import (
    KindnessContactRevealThrottle,
    KindnessReportThrottle,
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


class KindnessContactRevealView(APIView):
    """Reveal contact phone for authenticated users only."""

    permission_classes = [IsAuthenticated]
    throttle_classes = [KindnessContactRevealThrottle]

    @extend_schema(
        operation_id="kindness_listings_reveal_contact",
        tags=[TAG_USER],
        request=None,
        responses={200: CONTACT_REVEAL_RESPONSE, 403: ERROR_RESPONSE, 404: ERROR_RESPONSE},
    )
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
        log_action_async(
            user_id=request.user.pk,
            action=audit_actions.KINDNESS_CONTACT_REVEALED,
            resource_type="kindness_listing",
            resource_id=str(listing.pk),
            extra_data={"listing_owner_id": listing.owner_id},
            **metadata,
        )
        return SuccessResponse(
            data={
                "phone_number": reveal.phone_snapshot,
                "listing_id": listing.pk,
                "owner_full_name": listing.owner_full_name_snapshot,
            },
            message="شماره تماس آگهی نمایش داده شد.",
        )


class KindnessListingReportCreateView(APIView):
    """Report a published listing."""

    permission_classes = [IsAuthenticated]
    throttle_classes = [KindnessReportThrottle]

    @extend_schema(
        operation_id="kindness_listings_report",
        tags=[TAG_USER],
        request=KindnessListingReportCreateSerializer,
        responses={201: REPORT_RESPONSE, 403: ERROR_RESPONSE, 404: ERROR_RESPONSE},
    )
    def post(self, request: Request, slug: str) -> CreatedResponse | ErrorResponse:
        """Create a report for a listing."""
        listing = selectors.get_public_listing_by_slug(slug)
        if listing is None:
            return ErrorResponse(message="آگهی یافت نشد.", status_code=status.HTTP_404_NOT_FOUND)
        serializer = KindnessListingReportCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            report = services.report_listing(
                listing=listing, reported_by=request.user, **serializer.validated_data
            )
        except services.KindnessListingStateError as exc:
            return _service_error_response(exc, status_code=status.HTTP_403_FORBIDDEN)
        log_action_async(
            user_id=request.user.pk,
            action=audit_actions.KINDNESS_LISTING_REPORTED,
            resource_type="kindness_listing_report",
            resource_id=str(report.pk),
            extra_data={"listing_id": listing.pk},
            **extract_audit_metadata(request),
        )
        return CreatedResponse(
            data=KindnessListingReportSerializer(report).data, message="گزارش شما ثبت شد."
        )


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
        log_action_async(
            user_id=request.user.pk,
            action=audit_actions.KINDNESS_BOOKMARK_CREATED,
            resource_type="kindness_bookmark",
            resource_id=str(bookmark.pk),
            extra_data={"listing_id": listing.pk},
            **extract_audit_metadata(request),
        )
        return CreatedResponse(data={"listing_id": listing.pk}, message="آگهی ذخیره شد.")

    def delete(self, request: Request, slug: str) -> DeletedResponse | ErrorResponse:
        """Remove bookmark."""
        listing = selectors.get_public_listing_by_slug(slug)
        if listing is None:
            return ErrorResponse(message="آگهی یافت نشد.", status_code=status.HTTP_404_NOT_FOUND)
        services.delete_bookmark(listing=listing, user=request.user)
        log_action_async(
            user_id=request.user.pk,
            action=audit_actions.KINDNESS_BOOKMARK_DELETED,
            resource_type="kindness_listing",
            resource_id=str(listing.pk),
            **extract_audit_metadata(request),
        )
        return DeletedResponse(message="آگهی از ذخیره‌ها حذف شد.")


class KindnessMatchDismissView(APIView):
    """Dismiss a match."""

    permission_classes = [IsAuthenticated]
    serializer_class = KindnessMatchSerializer

    def post(self, request: Request, match_id: int) -> SuccessResponse | ErrorResponse:
        """Dismiss a match owned by user's source listing."""
        match = selectors.get_match_by_id(match_id=match_id)
        if match is None:
            return ErrorResponse(
                message="پیشنهاد تطبیق یافت نشد.", status_code=status.HTTP_404_NOT_FOUND
            )
        try:
            match = services.dismiss_match(match=match, user=request.user)
        except services.KindnessPermissionError as exc:
            return _service_error_response(exc, status_code=status.HTTP_403_FORBIDDEN)
        return SuccessResponse(
            data=KindnessMatchSerializer(match).data, message="پیشنهاد نادیده گرفته شد."
        )


class KindnessMatchContactedView(APIView):
    """Mark match as contacted."""

    permission_classes = [IsAuthenticated]
    serializer_class = KindnessMatchSerializer

    def post(self, request: Request, match_id: int) -> SuccessResponse | ErrorResponse:
        """Mark a match as contacted."""
        match = selectors.get_match_by_id(match_id=match_id)
        if match is None:
            return ErrorResponse(
                message="پیشنهاد تطبیق یافت نشد.", status_code=status.HTTP_404_NOT_FOUND
            )
        try:
            match = services.mark_match_contacted(match=match, user=request.user)
        except services.KindnessPermissionError as exc:
            return _service_error_response(exc, status_code=status.HTTP_403_FORBIDDEN)
        return SuccessResponse(
            data=KindnessMatchSerializer(match).data, message="پیشنهاد به‌عنوان تماس‌گرفته‌شده ثبت شد."
        )

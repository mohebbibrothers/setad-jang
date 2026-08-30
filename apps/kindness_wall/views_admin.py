"""گروه دامنه‌ای `views_admin` از views — فاز ۱۱ (تفکیک P3-16).

کلاس‌ها عیناً منتقل شده‌اند؛ مشترکات از views_common؛ نامِ عمومیِ این گروه‌ها را فقط از facade (apps.*.views) یا همین ماژول import کنید.
"""

from __future__ import annotations

from django.http import HttpResponse
from drf_spectacular.utils import extend_schema
from rest_framework import status
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
    build_success_response_serializer,
)
from apps.core.views import paginated_list_response
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
    KindnessCategorySerializer,
    KindnessDuplicateCandidateSerializer,
    KindnessDuplicateReviewSerializer,
    KindnessListingReportSerializer,
    KindnessReportReviewInputSerializer,
    KindnessUserListingDetailSerializer,
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


class KindnessAdminCategoryListCreateView(APIView):
    """Admin category tree list/create endpoint."""

    permission_classes = [IsKindnessAdminUser]
    serializer_class = KindnessCategorySerializer

    @extend_schema(
        operation_id="kindness_admin_categories_list",
        tags=[TAG_ADMIN],
        responses={200: CATEGORY_LIST_RESPONSE},
    )
    def get(self, request: Request) -> SuccessResponse:
        """Return all active/inactive categories for tree management."""
        return SuccessResponse(
            data=KindnessCategorySerializer(selectors.get_admin_categories(), many=True).data
        )

    @extend_schema(
        operation_id="kindness_admin_categories_create",
        tags=[TAG_ADMIN],
        request=KindnessAdminCategoryInputSerializer,
        responses={
            201: build_success_response_serializer(
                name="KindnessAdminCategoryResponse", data_serializer=KindnessCategorySerializer
            ),
            400: ERROR_RESPONSE,
        },
    )
    def post(self, request: Request) -> CreatedResponse | ErrorResponse:
        """Create a tree category via service layer."""
        serializer = KindnessAdminCategoryInputSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            category = services.create_category(**serializer.validated_data)
        except services.KindnessCategoryTreeError as exc:
            return _service_error_response(exc)
        log_action_async(
            user_id=request.user.pk,
            action=audit_actions.KINDNESS_CATEGORY_CREATED,
            resource_type="kindness_category",
            resource_id=str(category.pk),
            **extract_audit_metadata(request),
        )
        return CreatedResponse(
            data=KindnessCategorySerializer(category).data,
            message="دسته‌بندی دیوار مهربانی ساخته شد.",
        )


class KindnessAdminCategoryDetailView(APIView):
    """Admin category retrieve/update/deactivate endpoint."""

    permission_classes = [IsKindnessAdminUser]
    serializer_class = KindnessCategorySerializer

    def get(self, request: Request, category_id: int) -> SuccessResponse | ErrorResponse:
        """Return one category for admin editing."""
        category = selectors.get_admin_category_by_id(category_id=category_id)
        if category is None:
            return ErrorResponse(
                message="دسته‌بندی یافت نشد.", status_code=status.HTTP_404_NOT_FOUND
            )
        return SuccessResponse(data=KindnessCategorySerializer(category).data)

    def patch(self, request: Request, category_id: int) -> SuccessResponse | ErrorResponse:
        """Update category metadata/tree location."""
        category = selectors.get_admin_category_by_id(category_id=category_id)
        if category is None:
            return ErrorResponse(
                message="دسته‌بندی یافت نشد.", status_code=status.HTTP_404_NOT_FOUND
            )
        serializer = KindnessAdminCategoryInputSerializer(data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        try:
            if serializer.validated_data.get("is_active") is True and not category.is_active:
                category = services.restore_category(category=category)
                remaining = {
                    key: value
                    for key, value in serializer.validated_data.items()
                    if key != "is_active"
                }
                if remaining:
                    category = services.update_category(category=category, **remaining)
            elif serializer.validated_data.get("is_active") is False and category.is_active:
                category = services.deactivate_category(category=category)
                remaining = {
                    key: value
                    for key, value in serializer.validated_data.items()
                    if key != "is_active"
                }
                if remaining:
                    category = services.update_category(category=category, **remaining)
            else:
                category = services.update_category(category=category, **serializer.validated_data)
        except services.KindnessCategoryTreeError as exc:
            return _service_error_response(exc)
        log_action_async(
            user_id=request.user.pk,
            action=audit_actions.KINDNESS_CATEGORY_UPDATED,
            resource_type="kindness_category",
            resource_id=str(category.pk),
            **extract_audit_metadata(request),
        )
        return SuccessResponse(
            data=KindnessCategorySerializer(category).data, message="دسته‌بندی بروزرسانی شد."
        )

    def delete(self, request: Request, category_id: int) -> DeletedResponse | ErrorResponse:
        """Soft-delete/deactivate category with hierarchy safety checks."""
        category = selectors.get_admin_category_by_id(category_id=category_id)
        if category is None:
            return ErrorResponse(
                message="دسته‌بندی یافت نشد.", status_code=status.HTTP_404_NOT_FOUND
            )
        try:
            services.deactivate_category(category=category)
        except services.KindnessCategoryTreeError as exc:
            return _service_error_response(exc)
        log_action_async(
            user_id=request.user.pk,
            action=audit_actions.KINDNESS_CATEGORY_DELETED,
            resource_type="kindness_category",
            resource_id=str(category.pk),
            **extract_audit_metadata(request),
        )
        return DeletedResponse(message="دسته‌بندی غیرفعال شد.")


class KindnessAdminListingListView(APIView):
    """Admin list all listings."""

    permission_classes = [IsKindnessAdminUser]
    serializer_class = KindnessUserListingDetailSerializer

    @extend_schema(
        operation_id="kindness_admin_listings_list",
        tags=[TAG_ADMIN],
        responses={
            200: build_paginated_success_response_serializer(
                name="KindnessAdminListingListResponse",
                item_serializer=KindnessUserListingDetailSerializer,
            )
        },
    )
    def get(self, request: Request) -> Response:
        """Return admin listing list."""
        return paginated_list_response(
            request=request,
            view=self,
            queryset=selectors.get_admin_listings(),
            serializer_class=KindnessUserListingDetailSerializer,
            pagination_class=StandardPagination,
            filterset_class=KindnessListingAdminFilter,
        )


class KindnessAdminListingDetailView(APIView):
    """Admin retrieve listing."""

    permission_classes = [IsKindnessAdminUser]
    serializer_class = KindnessUserListingDetailSerializer

    @extend_schema(
        operation_id="kindness_admin_listings_retrieve",
        tags=[TAG_ADMIN],
        responses={200: USER_LISTING_DETAIL_RESPONSE, 404: ERROR_RESPONSE},
    )
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
            listing = services.approve_listing(
                listing=listing,
                admin=request.user,
                admin_note=serializer.validated_data.get("admin_note", ""),
            )
        except services.KindnessListingStateError as exc:
            return _service_error_response(exc)
        log_action_async(
            user_id=request.user.pk,
            action=audit_actions.KINDNESS_LISTING_APPROVED,
            resource_type="kindness_listing",
            resource_id=str(listing.pk),
            **extract_audit_metadata(request),
        )
        return SuccessResponse(
            data=KindnessUserListingDetailSerializer(listing).data, message="آگهی منتشر شد."
        )


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
            listing = services.reject_listing(
                listing=listing,
                admin=request.user,
                reason=serializer.validated_data.get("reason", ""),
                needs_edit=serializer.validated_data.get("needs_edit", False),
            )
        except services.KindnessListingStateError as exc:
            return _service_error_response(exc)
        log_action_async(
            user_id=request.user.pk,
            action=audit_actions.KINDNESS_LISTING_REJECTED,
            resource_type="kindness_listing",
            resource_id=str(listing.pk),
            **extract_audit_metadata(request),
        )
        return SuccessResponse(
            data=KindnessUserListingDetailSerializer(listing).data, message="آگهی رد شد."
        )


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
            listing = services.suspend_listing(
                listing=listing, admin=request.user, reason=serializer.validated_data["reason"]
            )
        except services.KindnessListingStateError as exc:
            return _service_error_response(exc)
        log_action_async(
            user_id=request.user.pk,
            action=audit_actions.KINDNESS_LISTING_SUSPENDED,
            resource_type="kindness_listing",
            resource_id=str(listing.pk),
            **extract_audit_metadata(request),
        )
        return SuccessResponse(
            data=KindnessUserListingDetailSerializer(listing).data, message="آگهی تعلیق شد."
        )


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
        return SuccessResponse(
            data=KindnessUserListingDetailSerializer(listing).data, message="آگهی بازگردانی شد."
        )


class KindnessAdminReportListView(APIView):
    """Admin report queue."""

    permission_classes = [IsKindnessAdminUser]
    serializer_class = KindnessListingReportSerializer

    def get(self, request: Request) -> Response:
        """Return listing reports."""
        return paginated_list_response(
            request=request,
            view=self,
            queryset=selectors.get_admin_reports(),
            serializer_class=KindnessListingReportSerializer,
            pagination_class=StandardPagination,
            filterset_class=KindnessReportAdminFilter,
        )


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
        log_action_async(
            user_id=request.user.pk,
            action=audit_actions.KINDNESS_REPORT_REVIEWED,
            resource_type="kindness_listing_report",
            resource_id=str(report.pk),
            **extract_audit_metadata(request),
        )
        return SuccessResponse(
            data=KindnessListingReportSerializer(report).data, message="گزارش بررسی شد."
        )


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

    @extend_schema(
        operation_id="kindness_admin_matches_list",
        tags=[TAG_ADMIN],
        responses={
            200: build_paginated_success_response_serializer(
                name="KindnessAdminMatchListResponse", item_serializer=KindnessAdminMatchSerializer
            )
        },
    )
    def get(self, request: Request) -> Response:
        """Return all matches with professional moderation filters."""
        return paginated_list_response(
            request=request,
            view=self,
            queryset=selectors.get_admin_matches(),
            serializer_class=KindnessAdminMatchSerializer,
            pagination_class=StandardPagination,
            filterset_class=KindnessMatchAdminFilter,
        )


class KindnessAdminMatchDetailView(APIView):
    """Admin match detail endpoint."""

    permission_classes = [IsKindnessAdminUser]
    serializer_class = KindnessAdminMatchSerializer

    @extend_schema(
        operation_id="kindness_admin_matches_retrieve",
        tags=[TAG_ADMIN],
        responses={
            200: build_success_response_serializer(
                name="KindnessAdminMatchDetailResponse",
                data_serializer=KindnessAdminMatchSerializer,
            ),
            404: ERROR_RESPONSE,
        },
    )
    def get(self, request: Request, match_id: int) -> SuccessResponse | ErrorResponse:
        """Return one match with source/target listing context."""
        match = selectors.get_admin_match_by_id(match_id=match_id)
        if match is None:
            return ErrorResponse(
                message="پیشنهاد تطبیق یافت نشد.", status_code=status.HTTP_404_NOT_FOUND
            )
        return SuccessResponse(data=KindnessAdminMatchSerializer(match).data)


class KindnessAdminContactRevealListView(APIView):
    """Admin contact reveal audit trail."""

    permission_classes = [IsKindnessAdminUser]
    serializer_class = KindnessAdminContactRevealSerializer

    @extend_schema(
        operation_id="kindness_admin_contact_reveals_list",
        tags=[TAG_ADMIN],
        responses={
            200: build_paginated_success_response_serializer(
                name="KindnessAdminContactRevealListResponse",
                item_serializer=KindnessAdminContactRevealSerializer,
            )
        },
    )
    def get(self, request: Request) -> Response:
        """Return paginated contact reveal records."""
        return paginated_list_response(
            request=request,
            view=self,
            queryset=selectors.get_admin_contact_reveals(),
            serializer_class=KindnessAdminContactRevealSerializer,
            pagination_class=StandardPagination,
            filterset_class=KindnessContactRevealAdminFilter,
        )


class KindnessAdminDuplicateCandidateListView(APIView):
    """Admin list likely duplicate listing candidates."""

    permission_classes = [IsKindnessAdminUser]
    serializer_class = KindnessDuplicateCandidateSerializer

    @extend_schema(
        operation_id="kindness_admin_duplicates_list",
        tags=[TAG_ADMIN],
        responses={
            200: build_paginated_success_response_serializer(
                name="KindnessAdminDuplicateListResponse",
                item_serializer=KindnessDuplicateCandidateSerializer,
            )
        },
    )
    def get(self, request: Request) -> Response:
        """Return duplicate candidates generated by the matching engine."""
        return paginated_list_response(
            request=request,
            view=self,
            queryset=selectors.get_admin_duplicate_candidates(),
            serializer_class=KindnessDuplicateCandidateSerializer,
            pagination_class=StandardPagination,
            filterset_class=KindnessDuplicateCandidateAdminFilter,
        )


class KindnessAdminDuplicateCandidateReviewView(APIView):
    """Admin review endpoint for duplicate candidates."""

    permission_classes = [IsKindnessAdminUser]
    serializer_class = KindnessDuplicateCandidateSerializer

    @extend_schema(
        operation_id="kindness_admin_duplicates_review",
        tags=[TAG_ADMIN],
        request=KindnessDuplicateReviewSerializer,
        responses={
            200: build_success_response_serializer(
                name="KindnessAdminDuplicateReviewResponse",
                data_serializer=KindnessDuplicateCandidateSerializer,
            ),
            404: ERROR_RESPONSE,
        },
    )
    def post(self, request: Request, duplicate_id: int) -> SuccessResponse | ErrorResponse:
        """Confirm or dismiss a likely duplicate candidate."""
        duplicate = selectors.get_admin_duplicate_candidate_by_id(duplicate_id=duplicate_id)
        if duplicate is None:
            return ErrorResponse(
                message="کاندیدای تکراری یافت نشد.", status_code=status.HTTP_404_NOT_FOUND
            )
        serializer = KindnessDuplicateReviewSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            duplicate = services.review_duplicate_candidate(
                duplicate=duplicate, **serializer.validated_data
            )
        except services.KindnessListingStateError as exc:
            return _service_error_response(exc)
        log_action_async(
            user_id=request.user.pk,
            action=audit_actions.KINDNESS_DUPLICATE_REVIEWED,
            resource_type="kindness_duplicate_candidate",
            resource_id=str(duplicate.pk),
            **extract_audit_metadata(request),
        )
        return SuccessResponse(
            data=KindnessDuplicateCandidateSerializer(duplicate).data,
            message="وضعیت کاندیدای تکراری بروزرسانی شد.",
        )


class KindnessAdminListingExportView(APIView):
    """Admin Excel export for listings."""

    permission_classes = [IsKindnessAdminUser]

    @extend_schema(
        operation_id="kindness_admin_listings_export", tags=[TAG_ADMIN], responses={200: None}
    )
    def get(self, request: Request) -> HttpResponse:
        """Export filtered listings as an RTL Excel workbook."""
        queryset = selectors.get_admin_listings()
        filterset = KindnessListingAdminFilter(request.query_params, queryset=queryset)
        if filterset.is_valid():
            queryset = filterset.qs
        workbook = build_listings_workbook(listings=queryset)
        filename = build_kindness_export_filename(export_type="listings")
        log_action_async(
            user_id=request.user.pk,
            action=audit_actions.KINDNESS_LISTINGS_EXPORTED,
            resource_type="kindness_listing",
            resource_id="bulk",
            extra_data={"filename": filename},
            **extract_audit_metadata(request),
        )
        response = HttpResponse(
            workbook.getvalue(),
            content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
        response["Content-Disposition"] = f'attachment; filename="{filename}"'
        return response


class KindnessAdminReportExportView(APIView):
    """Admin Excel export for moderation reports."""

    permission_classes = [IsKindnessAdminUser]

    @extend_schema(
        operation_id="kindness_admin_reports_export", tags=[TAG_ADMIN], responses={200: None}
    )
    def get(self, request: Request) -> HttpResponse:
        """Export filtered reports as an RTL Excel workbook."""
        queryset = selectors.get_admin_reports()
        filterset = KindnessReportAdminFilter(request.query_params, queryset=queryset)
        if filterset.is_valid():
            queryset = filterset.qs
        workbook = build_reports_workbook(reports=queryset)
        filename = build_kindness_export_filename(export_type="reports")
        log_action_async(
            user_id=request.user.pk,
            action=audit_actions.KINDNESS_REPORTS_EXPORTED,
            resource_type="kindness_listing_report",
            resource_id="bulk",
            extra_data={"filename": filename},
            **extract_audit_metadata(request),
        )
        response = HttpResponse(
            workbook.getvalue(),
            content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
        response["Content-Disposition"] = f'attachment; filename="{filename}"'
        return response

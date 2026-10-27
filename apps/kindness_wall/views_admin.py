"""Viewهای پنل ادمین دیوار مهربانی (v2).

تمام نوشتن‌های محتوایی از همین‌جا (یا Django Admin) می‌گذرد: دسته‌ها،
آگهی‌ها، اکشن‌های چرخهٔ حیات، تریاج اعلام‌ها و خروجی اکسل. هر تغییر audit
می‌شود و کش عمومی را بی‌اثر می‌کند (signal-based).
"""

from __future__ import annotations

from django.http import HttpResponse
from drf_spectacular.utils import extend_schema
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.audit_logs.helpers import extract_audit_metadata
from apps.audit_logs.services import log_action_async
from apps.core.pagination import StandardPagination
from apps.core.responses import CreatedResponse, DeletedResponse, ErrorResponse, SuccessResponse
from apps.core.views import paginated_list_response
from apps.kindness_wall import selectors, services
from apps.kindness_wall.filters import KindnessListingAdminFilter, KindnessOfferAdminFilter
from apps.kindness_wall.models import KindnessCategory, KindnessListing, KindnessOffer
from apps.kindness_wall.permissions import IsKindnessAdminUser
from apps.kindness_wall.serializers import (
    KindnessAdminListingSerializer,
    KindnessAdminOfferSerializer,
    KindnessCategoryInputSerializer,
    KindnessCategorySerializer,
    KindnessFeatureInputSerializer,
    KindnessFulfillInputSerializer,
    KindnessListingInputSerializer,
    KindnessOfferReviewInputSerializer,
)

from .export import (
    build_kindness_export_filename,
    build_listings_workbook,
    build_offers_workbook,
)
from .views_common import (  # noqa: F401
    ADMIN_LISTING_DETAIL_RESPONSE,
    ADMIN_LISTING_LIST_RESPONSE,
    ADMIN_OFFER_LIST_RESPONSE,
    CATEGORY_LIST_RESPONSE,
    EMPTY_RESPONSE,
    ERROR_RESPONSE,
    EXCEL_CONTENT_TYPE,
    TAG_ADMIN,
    _service_error_response,
)

_RESOURCE_LISTING = "kindness_listing"
_RESOURCE_CATEGORY = "kindness_category"
_RESOURCE_OFFER = "kindness_offer"


def _excel_response(workbook, *, filename: str) -> HttpResponse:
    """پاکت استاندارد دانلود شیت: headers بی‌خطر برای نام فایل فارسی‌محور."""
    response = HttpResponse(
        workbook.getvalue(),
        content_type=EXCEL_CONTENT_TYPE,
    )
    response["Content-Disposition"] = f'attachment; filename="{filename}"'
    response["Content-Length"] = str(len(response.content))
    workbook.close()
    return response


class KindnessAdminCategoryListView(APIView):
    """فهرست/ساخت دسته‌ها (مدیریت کامل taxonomy از پنل)."""

    permission_classes = [IsAuthenticated, IsKindnessAdminUser]
    serializer_class = KindnessCategorySerializer

    @extend_schema(
        operation_id="kindness_admin_categories_list",
        tags=[TAG_ADMIN],
        responses={200: CATEGORY_LIST_RESPONSE},
    )
    def get(self, request: Request) -> Response:
        """دسته‌های فعال با شمارندهٔ آگهی (ویرایش‌شده‌ها بی‌صدا از فهرست می‌روند)."""
        return SuccessResponse(
            data=KindnessCategorySerializer(selectors.get_public_categories(), many=True).data
        )

    @extend_schema(
        operation_id="kindness_admin_categories_create",
        tags=[TAG_ADMIN],
        request=KindnessCategoryInputSerializer,
        responses={201: CATEGORY_LIST_RESPONSE},
    )
    def post(self, request: Request) -> Response:
        """ساخت دسته؛ slug از عنوان ساخته می‌شود (منطق model)."""
        serializer = KindnessCategoryInputSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        category = KindnessCategory.objects.create(**serializer.validated_data)
        log_action_async(
            user_id=request.user.pk,
            action="KINDNESS_CATEGORY_CREATED",
            resource_type=_RESOURCE_CATEGORY,
            resource_id=str(category.pk),
            changes={"title": category.title},
            **extract_audit_metadata(request),
        )
        return CreatedResponse(
            data=KindnessCategorySerializer(category).data, message="دسته ساخته شد."
        )


class KindnessAdminCategoryDetailView(APIView):
    """ویرایش/غیرفعال‌سازی یک دسته."""

    permission_classes = [IsAuthenticated, IsKindnessAdminUser]
    serializer_class = KindnessCategorySerializer

    @extend_schema(
        operation_id="kindness_admin_categories_update",
        tags=[TAG_ADMIN],
        request=KindnessCategoryInputSerializer,
        responses={200: CATEGORY_LIST_RESPONSE},
    )
    def patch(self, request: Request, category_id: int) -> Response:
        """ویرایش فیلدهای قابل‌ویرایش دسته."""
        category = KindnessCategory.objects.filter(pk=category_id).first()
        if category is None:
            return ErrorResponse(message="دسته یافت نشد.", status_code=status.HTTP_404_NOT_FOUND)
        serializer = KindnessCategoryInputSerializer(data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        for field, value in serializer.validated_data.items():
            setattr(category, field, value)
        category.save(update_fields=[*serializer.validated_data.keys(), "updated_at"])
        log_action_async(
            user_id=request.user.pk,
            action="KINDNESS_CATEGORY_UPDATED",
            resource_type=_RESOURCE_CATEGORY,
            resource_id=str(category.pk),
            changes={k: str(v) for k, v in serializer.validated_data.items()},
            **extract_audit_metadata(request),
        )
        return SuccessResponse(
            data=KindnessCategorySerializer(category).data, message="دسته به‌روزرسانی شد."
        )

    @extend_schema(
        operation_id="kindness_admin_categories_deactivate",
        tags=[TAG_ADMIN],
        request=KindnessFeatureInputSerializer,
        responses={200: CATEGORY_LIST_RESPONSE, 409: ERROR_RESPONSE},
    )
    def delete(self, request: Request, category_id: int) -> Response:
        """غیرفعال‌سازی (soft) — نگهبان «دیوار خالی نشود» در services."""
        category = KindnessCategory.objects.filter(pk=category_id).first()
        if category is None:
            return ErrorResponse(message="دسته یافت نشد.", status_code=status.HTTP_404_NOT_FOUND)
        try:
            services.set_category_active(category=category, active=False)
        except services.KindnessCategoryGuardError as exc:
            return _service_error_response(exc, status_code=status.HTTP_409_CONFLICT)
        log_action_async(
            user_id=request.user.pk,
            action="KINDNESS_CATEGORY_DEACTIVATED",
            resource_type=_RESOURCE_CATEGORY,
            resource_id=str(category.pk),
            **extract_audit_metadata(request),
        )
        return DeletedResponse(message="دسته غیرفعال شد.")


class KindnessAdminListingListView(APIView):
    """فهرست کامل آگهی‌ها (همهٔ وضعیت‌ها) با فیلترهای ادمین."""

    permission_classes = [IsAuthenticated, IsKindnessAdminUser]
    serializer_class = KindnessAdminListingSerializer

    @extend_schema(
        operation_id="kindness_admin_listings_list",
        tags=[TAG_ADMIN],
        filters=True,
        responses={200: ADMIN_LISTING_LIST_RESPONSE},
    )
    def get(self, request: Request) -> Response:
        """جستجو/فیلتر روی همهٔ دیوار، نه فقط بخش عمومی."""
        return paginated_list_response(
            request=request,
            view=self,
            queryset=KindnessListing.objects.all()
            .select_related("category")
            .order_by("-created_at"),
            serializer_class=KindnessAdminListingSerializer,
            pagination_class=StandardPagination,
            filterset_class=KindnessListingAdminFilter,
            message="لیست آگهی‌ها دریافت شد.",
        )

    @extend_schema(
        operation_id="kindness_admin_listings_create",
        tags=[TAG_ADMIN],
        request=KindnessListingInputSerializer,
        responses={201: ADMIN_LISTING_DETAIL_RESPONSE},
    )
    def post(self, request: Request) -> Response:
        """ساخت آگهی جدید در وضعیت پیش‌نویس (انتشار اکشن جدا است)."""
        serializer = KindnessListingInputSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        listing = serializer.save(created_by=request.user)
        log_action_async(
            user_id=request.user.pk,
            action="KINDNESS_LISTING_CREATED",
            resource_type=_RESOURCE_LISTING,
            resource_id=str(listing.pk),
            changes={"title": listing.title, "category": listing.category_id},
            **extract_audit_metadata(request),
        )
        return CreatedResponse(
            data=KindnessAdminListingSerializer(listing).data,
            message="آگهی ساخته شد؛ برای انتشار روی «انتشار» بزنید.",
        )


class KindnessAdminListingDetailView(APIView):
    """مشاهده/ویرایش یک آگهی (هر وضعیتی)."""

    permission_classes = [IsAuthenticated, IsKindnessAdminUser]
    serializer_class = KindnessAdminListingSerializer

    @extend_schema(
        operation_id="kindness_admin_listings_retrieve",
        tags=[TAG_ADMIN],
        responses={200: ADMIN_LISTING_DETAIL_RESPONSE},
    )
    def get(self, request: Request, listing_id: int) -> Response:
        """جزئیات ادمین با شمارنده‌ها."""
        listing = self._get(listing_id)
        if isinstance(listing, ErrorResponse):
            return listing
        return SuccessResponse(data=KindnessAdminListingSerializer(listing).data)

    @extend_schema(
        operation_id="kindness_admin_listings_update",
        tags=[TAG_ADMIN],
        request=KindnessListingInputSerializer,
        responses={200: ADMIN_LISTING_DETAIL_RESPONSE},
    )
    def patch(self, request: Request, listing_id: int) -> Response:
        """ویرایش محتوا/کانال‌ها؛ تغییر slug انجام نمی‌شود (لینک‌ها نمی‌شکنند)."""
        listing = self._get(listing_id)
        if isinstance(listing, ErrorResponse):
            return listing
        serializer = KindnessListingInputSerializer(
            instance=listing, data=request.data, partial=True
        )
        serializer.is_valid(raise_exception=True)
        listing = serializer.save()
        log_action_async(
            user_id=request.user.pk,
            action="KINDNESS_LISTING_UPDATED",
            resource_type=_RESOURCE_LISTING,
            resource_id=str(listing.pk),
            changes={k: str(v) for k, v in serializer.validated_data.items()},
            **extract_audit_metadata(request),
        )
        return SuccessResponse(
            data=KindnessAdminListingSerializer(listing).data, message="آگهی به‌روزرسانی شد."
        )

    @staticmethod
    def _get(listing_id: int):
        """خواندن آگهی یا پاسخ ۴۰۴ (الگوی مشترک get/patch)."""
        listing = KindnessListing.objects.filter(pk=listing_id).select_related("category").first()
        if listing is None:
            return ErrorResponse(message="آگهی یافت نشد.", status_code=status.HTTP_404_NOT_FOUND)
        return listing


class KindnessAdminListingActionView(APIView):
    """اکشن‌های چرخهٔ حیات: publish / renew / fulfill / archive / draft / feature.

    یک endpoint به‌جای شیدِ شش‌تایی؛ path پارامتر اکشن مستقیماً روی تابع
    services می‌نشیند و اعتبار عملیات (وضعیت مبدأ، حداقل یک راه تماس) در
    services قفل شده است.
    """

    permission_classes = [IsAuthenticated, IsKindnessAdminUser]
    serializer_class = KindnessAdminListingSerializer

    _DISPATCH = {
        "publish": ("publish_listing", "KINDNESS_LISTING_PUBLISHED", "آگهی روی دیوار منتشر شد."),
        "renew": ("renew_listing", "KINDNESS_LISTING_RENEWED", "مهلت آگهی تمدید شد."),
        "archive": ("archive_listing", "KINDNESS_LISTING_ARCHIVED", "آگهی بایگانی شد."),
        "draft": (
            "revert_to_draft",
            "KINDNESS_LISTING_REVERTED_TO_DRAFT",
            "آگهی به پیش‌نویس برگشت.",
        ),
    }

    @extend_schema(
        operation_id="kindness_admin_listings_action",
        tags=[TAG_ADMIN],
        request=None,
        responses={200: ADMIN_LISTING_DETAIL_RESPONSE, 409: ERROR_RESPONSE},
    )
    def post(self, request: Request, listing_id: int, action: str) -> Response:
        """اجرای اکشن استاندارد روی آگهی."""
        if action == "fulfill":
            return self._fulfill(request, listing_id)
        if action == "feature":
            return self._feature(request, listing_id)
        spec = self._DISPATCH.get(action)
        if spec is None:
            return ErrorResponse(message="اکشن نامعتبر است.", status_code=status.HTTP_404_NOT_FOUND)
        service_name, audit_action, message = spec
        listing = KindnessListing.objects.filter(pk=listing_id).select_related("category").first()
        if listing is None:
            return ErrorResponse(message="آگهی یافت نشد.", status_code=status.HTTP_404_NOT_FOUND)
        service_fn = getattr(services, service_name)
        try:
            listing = service_fn(listing=listing)
        except services.KindnessWallServiceError as exc:
            return _service_error_response(exc, status_code=status.HTTP_409_CONFLICT)
        self._audit(request, audit_action, listing)
        return SuccessResponse(data=KindnessAdminListingSerializer(listing).data, message=message)

    def _fulfill(self, request: Request, listing_id: int) -> Response:
        """برطرف‌شدن با روایت اختیاری بایگانی."""
        listing = KindnessListing.objects.filter(pk=listing_id).first()
        if listing is None:
            return ErrorResponse(message="آگهی یافت نشد.", status_code=status.HTTP_404_NOT_FOUND)
        input_serializer = KindnessFulfillInputSerializer(data=request.data or {})
        input_serializer.is_valid(raise_exception=True)
        try:
            listing = services.fulfill_listing(
                listing=listing, note=input_serializer.validated_data.get("note", "")
            )
        except services.KindnessListingStateError as exc:
            return _service_error_response(exc, status_code=status.HTTP_409_CONFLICT)
        self._audit(request, "KINDNESS_LISTING_FULFILLED", listing)
        return SuccessResponse(
            data=KindnessAdminListingSerializer(listing).data,
            message="نیاز برطرف شد؛ به داستان‌های مهربانی اضافه گرد.",
        )

    def _feature(self, request: Request, listing_id: int) -> Response:
        """ویژه/لغو ویژه (ثبیت بالای تخته)."""
        listing = KindnessListing.objects.filter(pk=listing_id).first()
        if listing is None:
            return ErrorResponse(message="آگهی یافت نشد.", status_code=status.HTTP_404_NOT_FOUND)
        input_serializer = KindnessFeatureInputSerializer(data=request.data or {})
        input_serializer.is_valid(raise_exception=True)
        listing = services.set_featured(
            listing=listing, featured=input_serializer.validated_data["featured"]
        )
        self._audit(request, "KINDNESS_LISTING_FEATURE_TOGGLED", listing)
        return SuccessResponse(
            data=KindnessAdminListingSerializer(listing).data,
            message="نمایش ویژه تغییر کرد.",
        )

    @staticmethod
    def _audit(request: Request, action: str, listing: KindnessListing) -> None:
        """ثبت audit برای اکشن‌های وضعیت (بدون بدنهٔ سنگین)."""
        log_action_async(
            user_id=request.user.pk,
            action=action,
            resource_type=_RESOURCE_LISTING,
            resource_id=str(listing.pk),
            changes={"status": listing.status},
            **extract_audit_metadata(request),
        )


class KindnessAdminOfferListView(APIView):
    """صف تریاج اعلام‌های آمادگی."""

    permission_classes = [IsAuthenticated, IsKindnessAdminUser]
    serializer_class = KindnessAdminOfferSerializer

    @extend_schema(
        operation_id="kindness_admin_offers_list",
        tags=[TAG_ADMIN],
        filters=True,
        responses={200: ADMIN_OFFER_LIST_RESPONSE},
    )
    def get(self, request: Request) -> Response:
        """اعلام‌ها با فیلتر وضعیت/آگهی/کاربر."""
        return paginated_list_response(
            request=request,
            view=self,
            queryset=KindnessOffer.objects.select_related(
                "listing", "listing__category", "user"
            ).order_by("-created_at"),
            serializer_class=KindnessAdminOfferSerializer,
            pagination_class=StandardPagination,
            filterset_class=KindnessOfferAdminFilter,
            message="اعلام‌های آمادگی دریافت شد.",
        )


class KindnessAdminOfferReviewView(APIView):
    """ثبت نتیجهٔ پیگیری روی یک اعلام آمادگی (تماس گرفته شد / رد شد)."""

    permission_classes = [IsAuthenticated, IsKindnessAdminUser]
    serializer_class = KindnessAdminOfferSerializer

    @extend_schema(
        operation_id="kindness_admin_offers_review",
        tags=[TAG_ADMIN],
        request=KindnessOfferReviewInputSerializer,
        responses={200: ADMIN_OFFER_LIST_RESPONSE, 404: ERROR_RESPONSE},
    )
    def post(self, request: Request, offer_id: int) -> Response:
        """بررسی نهایی؛ داوطلب نتیجه را در «اعلام‌های من» می‌بیند."""
        offer = KindnessOffer.objects.filter(pk=offer_id).select_related("listing", "user").first()
        if offer is None:
            return ErrorResponse(
                message="اعلام آمادگی یافت نشد.", status_code=status.HTTP_404_NOT_FOUND
            )
        input_serializer = KindnessOfferReviewInputSerializer(data=request.data)
        input_serializer.is_valid(raise_exception=True)
        offer = services.review_offer(
            offer=offer,
            admin=request.user,
            status=input_serializer.validated_data["status"],
            note=input_serializer.validated_data.get("note", ""),
        )
        log_action_async(
            user_id=request.user.pk,
            action="KINDNESS_OFFER_REVIEWED",
            resource_type=_RESOURCE_OFFER,
            resource_id=str(offer.pk),
            changes={"status": offer.status},
            **extract_audit_metadata(request),
        )
        return SuccessResponse(
            data=KindnessAdminOfferSerializer(offer).data, message="نتیجه ثبت شد."
        )


class KindnessAdminListingsExportView(APIView):
    """خروجی اکسل آگهی‌ها (همان فیلترهای فهرست ادمین اعمال می‌شود)."""

    permission_classes = [IsAuthenticated, IsKindnessAdminUser]

    @extend_schema(
        operation_id="kindness_admin_listings_export",
        tags=[TAG_ADMIN],
        filters=True,
        responses={(200, EXCEL_CONTENT_TYPE): None},
    )
    def get(self, request: Request) -> HttpResponse:
        """استریم شیت؛ برای دیوارهای بزرگ رم نمی‌کند."""
        queryset = KindnessListing.objects.all().select_related("category").order_by("-created_at")
        filterset = KindnessListingAdminFilter(request.query_params, queryset=queryset)
        if filterset.is_valid():
            queryset = filterset.qs
        workbook = build_listings_workbook(listings=queryset.iterator(chunk_size=1000))
        response = _excel_response(
            workbook, filename=build_kindness_export_filename(export_type="listings")
        )
        log_action_async(
            user_id=request.user.pk,
            action="KINDNESS_LISTINGS_EXPORTED",
            resource_type=_RESOURCE_LISTING,
            **extract_audit_metadata(request),
        )
        return response


class KindnessAdminOffersExportView(APIView):
    """خروجی اکسل اعلام‌های آمادگی (بدون اطلاعات تماس داوطلب)."""

    permission_classes = [IsAuthenticated, IsKindnessAdminUser]

    @extend_schema(
        operation_id="kindness_admin_offers_export",
        tags=[TAG_ADMIN],
        filters=True,
        responses={(200, EXCEL_CONTENT_TYPE): None},
    )
    def get(self, request: Request) -> HttpResponse:
        """استریم شیت تریاج."""
        queryset = KindnessOffer.objects.select_related("listing", "user").order_by("-created_at")
        filterset = KindnessOfferAdminFilter(request.query_params, queryset=queryset)
        if filterset.is_valid():
            queryset = filterset.qs
        workbook = build_offers_workbook(offers=queryset.iterator(chunk_size=1000))
        response = _excel_response(
            workbook, filename=build_kindness_export_filename(export_type="offers")
        )
        log_action_async(
            user_id=request.user.pk,
            action="KINDNESS_OFFERS_EXPORTED",
            resource_type=_RESOURCE_OFFER,
            **extract_audit_metadata(request),
        )
        return response

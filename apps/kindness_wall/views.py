"""Viewهای عمومی و کاربری دیوار مهربانی (v2).

معماری: خواندن‌های عمومی از selectors + کش SWR پروژه؛ نوشتن‌ها فقط اعلام
آمادگی است که از services می‌گذرد. تماس واقعی بیرون از اپ و از راه‌های
درج‌شدهٔ خود آگهی است — هیچ endpoint برای «نمایش تدریجی» یا مچینگ نیست.
"""

from __future__ import annotations

from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.core.api_cache import build_cache_variant, cached_public_payload
from apps.core.pagination import StandardPagination
from apps.core.responses import CreatedResponse, ErrorResponse, SuccessResponse
from apps.core.views import paginated_list_response
from apps.kindness_wall import selectors, services
from apps.kindness_wall.choices import RELATED_DEFAULT_LIMIT, RELATED_MAX_LIMIT
from apps.kindness_wall.filters import KindnessListingPublicFilter
from apps.kindness_wall.models import KindnessOffer
from apps.kindness_wall.serializers import (
    KindnessBoardStatsSerializer,
    KindnessCategorySerializer,
    KindnessListingDetailSerializer,
    KindnessListingListSerializer,
    KindnessOfferInputSerializer,
    KindnessOfferSerializer,
    KindnessStorySerializer,
)
from apps.kindness_wall.throttles import (
    KindnessBrowseAnonThrottle,
    KindnessBrowseUserThrottle,
    KindnessOfferCreateThrottle,
    KindnessViewAnonThrottle,
    KindnessViewUserThrottle,
)
from apps.kindness_wall.validators import gated_channel_payload

from .views_common import (  # noqa: F401 — re-export برای بدنه‌ها و import بیرونی
    BOARD_STATS_RESPONSE,
    CATEGORY_LIST_RESPONSE,
    EMPTY_RESPONSE,
    ERROR_RESPONSE,
    LISTING_DETAIL_RESPONSE,
    LISTING_LIST_RESPONSE,
    MY_OFFER_LIST_RESPONSE,
    OFFER_RESPONSE,
    STORY_LIST_RESPONSE,
    TAG_ADMIN,
    TAG_PUBLIC,
    TAG_USER,
    _service_error_response,
)


class KindnessCategoryPublicListView(APIView):
    """دسته‌های فعال دیوار با شمارندهٔ زندهٔ آگهی‌های جاری."""

    permission_classes = [AllowAny]
    throttle_classes = [KindnessBrowseAnonThrottle, KindnessBrowseUserThrottle]

    @extend_schema(
        operation_id="kindness_categories_list",
        tags=[TAG_PUBLIC],
        responses={200: CATEGORY_LIST_RESPONSE},
    )
    def get(self, request: Request) -> Response:
        """فهرست دسته‌ها (کش عمومی؛ با هر ویرایش ادمین invalid می‌شود)."""
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
    """تختهٔ عمومی: آگهی‌های نیاز جاری، قابل فیلتر و جستجو."""

    permission_classes = [AllowAny]
    throttle_classes = [KindnessBrowseAnonThrottle, KindnessBrowseUserThrottle]

    @extend_schema(
        operation_id="kindness_listings_list",
        tags=[TAG_PUBLIC],
        filters=True,
        responses={200: LISTING_LIST_RESPONSE},
    )
    def get(self, request: Request) -> Response:
        """فهرست صفحه‌بندی‌شده بدون هیچ راه تماس (کارت‌ها تماس‌محور نیستند)."""
        base_queryset = selectors.get_public_listings()
        filterset = KindnessListingPublicFilter(request.query_params, queryset=base_queryset)

        def build_payload() -> dict:
            """ساخت بدنهٔ صفحه‌بندی‌شده برای کش (فقط پس از فیلتر معتبر)."""
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
    """جزئیات یک آگهی — شامل راه‌های تماس که ادمین برای همین آگهی تعریف کرده."""

    permission_classes = [AllowAny]
    throttle_classes = [KindnessBrowseAnonThrottle, KindnessBrowseUserThrottle]

    @extend_schema(
        operation_id="kindness_listings_retrieve",
        tags=[TAG_PUBLIC],
        responses={200: LISTING_DETAIL_RESPONSE, 404: ERROR_RESPONSE},
    )
    def get(self, request: Request, slug: str) -> Response:
        """یک آگهی جاری + شمارش بازدید + وضعیت اعلام آمادگیِ کاربر جاری."""
        listing = selectors.get_public_listing_by_slug(slug)
        if listing is None:
            return ErrorResponse(message="آگهی یافت نشد.", status_code=status.HTTP_404_NOT_FOUND)
        # ⚠️ شمارشِ بازدید عمداً این‌جا نیست: این endpoint سروری و کش‌شده است،
        # پس هر revalidate یا prefetch یک «بازدید» جعلی می‌ساخت. شمارش به
        # `POST listings/{slug}/view/` منتقل شده که از مرورگرِ واقعی می‌آید،
        # dedupe دارد و throttle می‌شود.

        def build_payload() -> dict | None:
            """سریال‌سازی نسخهٔ عمومی از تازه‌ترین ردیف (None اگر از تخته رفت)."""
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

        # فیلدهای شخصی‌سازی‌شده بیرون از کش محاسبه می‌شوند؛ کش فقط بخش عمومی را
        # نگه می‌دارد. همین‌جا «دروازهٔ تماس» اعمال می‌شود:
        #   • کاربرِ واردشده → کانال‌های کامل (همان چیزی که در کش است)
        #   • کاربرِ بی‌نام  → همان کانال‌ها با مقدارِ ماسک‌شده و بدونِ لینک
        #     (`contact_gated=true`) تا اسکرپِ انبوهِ شماره‌ها ممکن نباشد و
        #     دیدنِ کاملِ راهِ تماس، انگیزهٔ ثبت‌نامِ واقعی بماند.
        authenticated = bool(getattr(request.user, "is_authenticated", False))
        if authenticated:
            my_offer = selectors.get_user_offer_for_listing(
                user_id=request.user.pk, listing=listing
            )
            payload = {
                **payload,
                "my_offer_status": my_offer.status if my_offer else None,
                "can_offer": True,
                "contact_gated": False,
            }
        else:
            channels = payload.get("contact_channels") or []
            payload = {
                **payload,
                "contact_channels": gated_channel_payload(channels),
                "contact_gated": bool(channels),
                "my_offer_status": None,
                "can_offer": False,
            }
        return SuccessResponse(data=payload)


class KindnessListingViewBeaconView(APIView):
    """ثبتِ بازدیدِ یکتای یک آگهی — beacon سبک از مرورگر.

    چرا یک endpoint جدا؟
      • صفحهٔ جزئیات سروری و ISR‌شده است؛ شمارش در آن، هر revalidate را
        «بازدید» می‌کرد. این‌جا درخواست از مرورگرِ واقعی می‌آید، پس هم عدد
        معنادار است و هم می‌توان بیننده را (کاربر یا IP+UA) تشخیص داد.
      • پاسخ، عددِ **تازه** را می‌دهد تا رابط بدونِ رفرش به‌روزش کند.

    سیاست‌ها:
      • پنجرهٔ dedupe (پیش‌فرض ۶ ساعت) — رفرشِ پیاپی شمارنده را بالا نمی‌برد؛
      • throttle اختصاصی (سخاوتمندانه‌تر از مرور، سخت‌گیرانه‌تر از هیچ)؛
      • کارکنان شمارش نمی‌شوند؛
      • آگهیِ غیرِ‌عمومی ۴۰۴ می‌دهد و هیچ شمارنده‌ای را لمس نمی‌کند.
    """

    permission_classes = [AllowAny]
    throttle_classes = [KindnessViewAnonThrottle, KindnessViewUserThrottle]

    @extend_schema(
        operation_id="kindness_listing_view",
        tags=[TAG_PUBLIC],
        summary="ثبتِ بازدیدِ یکتای آگهی",
        request=None,
        responses={200: None, 404: ERROR_RESPONSE},
    )
    def post(self, request: Request, slug: str) -> Response:
        """شمارش (اگر بیننده در پنجرهٔ dedupe نبود) و برگرداندنِ عددِ تازه."""
        listing = selectors.get_public_listing_by_slug(slug)
        if listing is None:
            return ErrorResponse(message="آگهی یافت نشد.", status_code=status.HTTP_404_NOT_FOUND)

        user = getattr(request, "user", None)
        if user is not None and (
            getattr(user, "is_staff", False) or getattr(user, "is_superuser", False)
        ):
            # پیش‌نمایشِ ادمین نباید آمارِ عمومی را آلوده کند.
            return SuccessResponse(
                data={"counted": False, "view_count": int(listing.view_count or 0)},
                message="بازدیدِ کارکنان شمارش نمی‌شود.",
            )

        counted, view_count = services.register_listing_view(listing=listing, request=request)
        return SuccessResponse(
            data={"counted": counted, "view_count": view_count},
            message="بازدید ثبت شد.",
        )


class KindnessRelatedListView(APIView):
    """نیازهای هم‌ربط با یک آگهی — برای بخشِ «شاید این‌ها هم در توانت باشد».

    تفاوت با فراخوانیِ فهرستِ عمومی:
      • خودِ آگهی سمتِ سرور حذف می‌شود؛
      • ترتیب بر پایهٔ **ربط** است (دسته/شهر/استان/سراسری)، نه فقط تازگی؛
      • سبک است (فقط فیلدهای کارت، بدونِ اطلاعاتِ تماس) و کش می‌شود؛
      • اگر دسته کم‌جمعیت باشد، با نیازهای هم‌استان و سراسری پر می‌شود تا
        بخشِ صفحه هرگز خالی/نصفه نماند.
    """

    permission_classes = [AllowAny]
    throttle_classes = [KindnessBrowseAnonThrottle, KindnessBrowseUserThrottle]

    @extend_schema(
        operation_id="kindness_listing_related",
        tags=[TAG_PUBLIC],
        summary="نیازهای مشابهِ یک آگهی",
        parameters=[
            OpenApiParameter(
                name="limit",
                location=OpenApiParameter.QUERY,
                required=False,
                type=int,
                description="تعداد نتیجه (۱ تا ۱۲، پیش‌فرض ۴).",
            )
        ],
        responses={200: LISTING_LIST_RESPONSE, 404: ERROR_RESPONSE},
    )
    def get(self, request: Request, slug: str) -> Response:
        """فهرستِ کوتاهِ کارت‌ها؛ ۴۰۴ برای آگهیِ غیرِ‌عمومی."""
        listing = selectors.get_public_listing_by_slug(slug)
        if listing is None:
            return ErrorResponse(message="آگهی یافت نشد.", status_code=status.HTTP_404_NOT_FOUND)

        try:
            limit = int(request.query_params.get("limit", RELATED_DEFAULT_LIMIT))
        except (TypeError, ValueError):
            limit = RELATED_DEFAULT_LIMIT
        limit = max(1, min(limit, RELATED_MAX_LIMIT))

        def build_payload() -> list[dict]:
            """سریال‌سازیِ سبک برای کش (کلید شاملِ اسلاگ و limit است)."""
            rows = selectors.get_related_listings(listing=listing, limit=limit)
            return KindnessListingListSerializer(rows, many=True).data

        payload = cached_public_payload(
            domain="kindness",
            namespace="kindness:public_list",
            parts=("related", listing.slug, limit),
            factory=build_payload,
        )
        return SuccessResponse(data=payload, message="نیازهای مشابه دریافت شد.")


class KindnessStoryPublicListView(APIView):
    """بایگانی «داستان‌های مهربانی»: چه نیازهایی برطرف شده است."""

    permission_classes = [AllowAny]
    throttle_classes = [KindnessBrowseAnonThrottle, KindnessBrowseUserThrottle]

    @extend_schema(
        operation_id="kindness_stories_list",
        tags=[TAG_PUBLIC],
        responses={200: STORY_LIST_RESPONSE},
    )
    def get(self, request: Request) -> Response:
        """فهرست نیازهای برطرف‌شده (بدون راه تماس، بدون نام صاحب آگهی)."""

        def build_payload() -> dict:
            """صفحه‌بندی استوری‌ها برای کش."""
            paginator = StandardPagination()
            page = paginator.paginate_queryset(
                selectors.get_fulfilled_stories(), request, view=self
            )
            serializer = KindnessStorySerializer(page, many=True)
            response = paginator.get_paginated_response(
                serializer.data, message="داستان‌های مهربانی دریافت شد."
            )
            return response.data["data"]

        payload = cached_public_payload(
            domain="kindness",
            namespace="kindness:public_list",
            parts=(
                "stories",
                *build_cache_variant(request, filterset=None, pagination_class=StandardPagination),
            ),
            factory=build_payload,
        )
        return SuccessResponse(data=payload, message="داستان‌های مهربانی دریافت شد.")


class KindnessBoardStatsView(APIView):
    """شمارنده‌های تأثیر روی سرصفحهٔ دیوار."""

    permission_classes = [AllowAny]
    throttle_classes = [KindnessBrowseAnonThrottle, KindnessBrowseUserThrottle]

    @extend_schema(
        operation_id="kindness_stats",
        tags=[TAG_PUBLIC],
        responses={200: BOARD_STATS_RESPONSE},
    )
    def get(self, request: Request) -> Response:
        """آمار عمومی دیوار (کش همان namespace فهرست، کلید stats)."""

        def build_payload() -> dict:
            """اسکیمای صریح آمار؛ همان dict سلکتور را مستقیم سریال می‌کند."""
            return KindnessBoardStatsSerializer(selectors.get_board_stats()).data

        payload = cached_public_payload(
            domain="kindness",
            namespace="kindness:public_list",
            parts=("stats",),
            factory=build_payload,
        )
        return SuccessResponse(data=payload)


class KindnessOfferCreateView(APIView):
    """«من می‌تونم کمک کنم» — ثبت/به‌روزرسانی اعلام آمادگی روی یک آگهی."""

    permission_classes = [IsAuthenticated]
    throttle_classes = [KindnessOfferCreateThrottle]

    @extend_schema(
        operation_id="kindness_offer_create",
        tags=[TAG_USER],
        request=KindnessOfferInputSerializer,
        responses={201: OFFER_RESPONSE, 200: OFFER_RESPONSE, 404: ERROR_RESPONSE},
    )
    def post(self, request: Request, slug: str) -> Response:
        """upsert: ثبت اولین اعلام یا ویرایش پیام تا پیش از بررسی ادمین."""
        listing = selectors.get_public_listing_by_slug(slug)
        if listing is None:
            return ErrorResponse(message="آگهی یافت نشد.", status_code=status.HTTP_404_NOT_FOUND)
        input_serializer = KindnessOfferInputSerializer(data=request.data)
        input_serializer.is_valid(raise_exception=True)
        try:
            offer, created = services.submit_offer(
                listing=listing,
                user=request.user,
                message=input_serializer.validated_data.get("message", ""),
            )
        except services.KindnessOfferError as exc:
            return _service_error_response(exc)
        data = KindnessOfferSerializer(offer).data
        message = "اعلام آمادگی شما ثبت شد." if created else "اعلام آمادگی شما به‌روزرسانی شد."
        if created:
            return CreatedResponse(data=data, message=message)
        return SuccessResponse(data=data, message=message)


class KindnessOfferWithdrawView(APIView):
    """پس‌گرفتن اعلام آمادگی — فقط تا پیش از بررسی ادمین."""

    permission_classes = [IsAuthenticated]

    @extend_schema(
        operation_id="kindness_offer_withdraw",
        tags=[TAG_USER],
        responses={200: EMPTY_RESPONSE, 404: ERROR_RESPONSE},
    )
    def delete(self, request: Request, offer_id: int) -> Response:
        """حذف رکورد اعلام (soft حذف نیست؛ رکورد تریاج‌نشده ارزش نگهداری ندارد)."""
        offer = KindnessOffer.objects.filter(pk=offer_id).select_related("listing").first()
        if offer is None:
            return ErrorResponse(
                message="اعلام آمادگی یافت نشد.", status_code=status.HTTP_404_NOT_FOUND
            )
        try:
            services.withdraw_offer(offer=offer, user=request.user)
        except services.KindnessOfferError as exc:
            return _service_error_response(exc)
        return SuccessResponse(data=None, message="اعلام آمادگی پس گرفته شد.")


class KindnessMyOffersView(APIView):
    """فهرست اعلام‌های آمادگی کاربر جاری با نتیجهٔ بررسی ادمین."""

    permission_classes = [IsAuthenticated]

    @extend_schema(
        operation_id="kindness_my_offers",
        tags=[TAG_USER],
        responses={200: MY_OFFER_LIST_RESPONSE},
    )
    def get(self, request: Request) -> Response:
        """صفحه‌بندی استاندارد روی کوئری‌ست selectors."""
        return paginated_list_response(
            request=request,
            view=self,
            queryset=selectors.get_user_offers(user_id=request.user.pk),
            serializer_class=KindnessOfferSerializer,
            pagination_class=StandardPagination,
            message="اعلام‌های آمادگی شما دریافت شد.",
        )

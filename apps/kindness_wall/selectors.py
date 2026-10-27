"""لایهٔ خواندنی (selectors) دیوار مهربانی — کوئری‌های بهینه و یک‌جاشده.

هیچ view ای نباید از صفر queryset بسازد؛ همه‌چیز از اینجا عبور می‌کند تا
prefetchها و شمارنده‌های annotated یک‌بار و درست تعریف شوند.
"""

from __future__ import annotations

from datetime import timedelta

from django.db.models import Count, Prefetch, Q, QuerySet
from django.utils import timezone

from apps.kindness_wall.choices import ListingStatus, OfferStatus, Urgency
from apps.kindness_wall.models import (
    KindnessCategory,
    KindnessListing,
    KindnessListingImage,
    KindnessOffer,
)

#: پنجرهٔ بایگانی «داستان‌های مهربانی» — روز.
ARCHIVE_WINDOW_DAYS = 90


def get_public_categories() -> QuerySet[KindnessCategory]:
    """دسته‌های فعال با شمارندهٔ زندهٔ آگهی‌های جاری (بدون ستون denormalized)."""
    now = timezone.now()
    on_board = (
        Q(listings__is_active=True)
        & Q(listings__status=ListingStatus.PUBLISHED)
        & (Q(listings__expires_at__isnull=True) | Q(listings__expires_at__gt=now))
    )
    return KindnessCategory.objects.annotate(
        open_listings_count=Count("listings", filter=on_board)
    ).order_by("order", "title")


def _images_prefetch() -> Prefetch:
    """Prefetch تصاویر با ترتیب کاور-اول؛ سریالایزر cover را از اولین عنصر می‌خواند."""
    return Prefetch(
        "images",
        queryset=KindnessListingImage.objects.order_by("-is_cover", "order", "id"),
    )


#: ترتیب مرجع تخته — باید بعد از annotate صریح بازاعمال شود، چون
#: «Django در کوئری گروهی default ordering مدل را پاک می‌کند» (clear_ordering
#: داخل add_aggregation) و نتیجه هم ناپایدار می‌شود هم UnorderedObjectList
#: روی pagination.
BOARD_ORDER_BY: tuple[str, ...] = ("-is_featured", "-published_at", "-created_at")


def _optimize_board_queryset(queryset: QuerySet[KindnessListing]) -> QuerySet[KindnessListing]:
    """select_related/prefetch/annotate مشترک تخته و جزئیات + ترتیب صریح."""
    return (
        queryset.select_related("category")
        .prefetch_related(_images_prefetch())
        .annotate(open_offers_count=Count("offers", filter=Q(offers__status=OfferStatus.NEW)))
        .order_by(*BOARD_ORDER_BY)
    )


def get_public_listings() -> QuerySet[KindnessListing]:
    """تختهٔ عمومی: جاری، نامنقضی."""
    return _optimize_board_queryset(KindnessListing.objects.published())


def get_public_listing_by_slug(slug: str) -> KindnessListing | None:
    """جزئیات آگهی جاری؛ ``None`` اگر روی تخته نباشد (پیش‌نویس/منقضی/حذف)."""
    return _optimize_board_queryset(KindnessListing.objects.published()).filter(slug=slug).first()


def get_fulfilled_stories() -> QuerySet[KindnessListing]:
    """بایگانیِ «داستان‌های مهربانی»: نیازهای برطرف‌شده در پنجرهٔ اخیر."""
    since = timezone.now() - timedelta(days=ARCHIVE_WINDOW_DAYS)
    return (
        KindnessListing.objects.fulfilled()
        .filter(Q(fulfilled_at__isnull=True) | Q(fulfilled_at__gte=since))
        .select_related("category")
        .prefetch_related(_images_prefetch())
        .order_by("-fulfilled_at", "-updated_at")
    )


def get_user_offers(*, user_id: int) -> QuerySet[KindnessOffer]:
    """اعلام‌های آمادگیِ خودِ کاربر، با خلاصهٔ آگهی."""
    return (
        KindnessOffer.objects.filter(user_id=user_id)
        .select_related("listing", "listing__category")
        .order_by("-created_at")
    )


def get_user_offer_for_listing(*, user_id: int, listing: KindnessListing) -> KindnessOffer | None:
    """اعلام آمادگی فعلی این کاربر روی این آگهی (برای حالت «ثبت شدهٔ شما»)."""
    return KindnessOffer.objects.filter(user_id=user_id, listing=listing).first()


def get_board_stats() -> dict[str, int]:
    """عددِ تأثیر عمومی؛ برای ویجت homepage و سرصفحهٔ دیوار."""
    now = timezone.now()
    board = KindnessListing.objects.published()
    fulfilled = KindnessListing.objects.filter(status=ListingStatus.FULFILLED)
    return {
        "open_listings": board.count(),
        "urgent_listings": board.filter(urgency=Urgency.URGENT).count(),
        "fulfilled_total": fulfilled.count(),
        "fulfilled_30d": fulfilled.filter(fulfilled_at__gte=now - timedelta(days=30)).count(),
        "volunteers_total": KindnessOffer.objects.values("user").annotate(n=Count("pk")).count(),
        "active_categories": KindnessCategory.objects.count(),
    }

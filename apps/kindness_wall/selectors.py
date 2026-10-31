"""لایهٔ خواندنی (selectors) دیوار مهربانی — کوئری‌های بهینه و یک‌جاشده.

هیچ view ای نباید از صفر queryset بسازد؛ همه‌چیز از اینجا عبور می‌کند تا
prefetchها و شمارنده‌های annotated یک‌بار و درست تعریف شوند.
"""

from __future__ import annotations

from datetime import timedelta

from django.db.models import (
    Case,
    Count,
    F,
    IntegerField,
    Prefetch,
    Q,
    QuerySet,
    Value,
    When,
)
from django.db.models.functions import Coalesce
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


# ══════════════════════════════════════════════════════════════════════════
#  نیازهای مشابه — صفحهٔ جزئیات
# ══════════════════════════════════════════════════════════════════════════
# پیش از این، «نیازهای مشابه» با یک درخواست به فهرستِ عمومی و فیلترِ سمتِ
# فرانت ساخته می‌شد؛ نتیجه: (۱) خودِ آگهیِ جاری هم می‌آمد و در فرانت حذف
# می‌شد، (۲) اگر دسته کم‌جمعیت بود، بخش خالی می‌ماند، (۳) ربط واقعی نداشت —
# فقط «هر چه در همان دسته بود».
#
# این‌جا یک کوئریِ واحد با «امتیازِ ربط» می‌سازیم که هم قابلِ توضیح است و هم
# ارزان (بدونِ N+1 و بدونِ حلقهٔ پایتونی):
#
#   ۵ → همان دسته **و** همان شهر   (نزدیک‌ترین نیاز از نظرِ موضوع و مکان)
#   ۴ → همان دسته                  (موضوع یکی است)
#   ۳ → همان استان، دستهٔ دیگر     (هم‌سایه‌ها؛ برای اهداکننده مهم است)
#   ۲ → سراسری (بدونِ استان)        (در هر نقطه قابلِ برآورده‌شدن)
#   ۱ → بقیه                        (پر کردنِ حداقلِ نتیجه)
#
# بعد از امتیاز، همان ترتیبِ مرجعِ تخته اعمال می‌شود (ویژه‌ها اول، بعد
# تازه‌ترین) تا خروجی با بقیهٔ صفحه هم‌خانواده بماند.

RELATED_RELEVANCE_MAX = 5


def get_related_listings(*, listing: KindnessListing, limit: int = 4) -> QuerySet[KindnessListing]:
    """آگهی‌های هم‌ربط با یک نیاز، به‌ترتیبِ ربط (بدونِ خودِ آگهی).

    `limit` توسط لایهٔ view کلمپ می‌شود؛ این‌جا فقط یک عددِ سالم لازم است.
    """
    safe_limit = max(1, min(int(limit), 12))

    relevance_cases = []
    if (listing.city or "").strip():
        relevance_cases.append(
            When(
                Q(category_id=listing.category_id) & Q(city__iexact=listing.city.strip()),
                then=Value(5),
            )
        )
    relevance_cases.append(When(Q(category_id=listing.category_id), then=Value(4)))
    if (listing.province or "").strip():
        relevance_cases.append(When(Q(province__iexact=listing.province.strip()), then=Value(3)))
    relevance_cases.append(When(Q(province__isnull=True) | Q(province=""), then=Value(2)))

    annotations = {
        "relevance": Case(*relevance_cases, default=Value(1), output_field=IntegerField())
    }
    # مهلتِ نزدیک‌تر برای همان سطحِ ربط اولویت دارد: نیازِ فوری‌تر زودتر باید
    # دیده شود. `expires_at=None` با Coalesce به «دورترین» نگاشت می‌شود تا
    # آگهیِ بدونِ انقضا آخر صف بایستد، نه اول.
    annotations["days_to_expiry"] = Coalesce(
        F("expires_at"),
        Value(timezone.now() + timedelta(days=3650)),
    )

    return (
        _optimize_board_queryset(KindnessListing.objects.published().exclude(pk=listing.pk))
        .annotate(**annotations)
        .order_by(
            "-relevance",
            "days_to_expiry",
            *BOARD_ORDER_BY,
        )[:safe_limit]
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

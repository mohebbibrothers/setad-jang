"""لایهٔ نوشتاری (services) دیوار مهربانی — تنها دروازهٔ تغییر وضعیت‌ها.

انتشار/تمدید/برطرف‌سازی/بایگانی و ثبت اعلام آمادگی همه از اینجا می‌گذرند تا
قاعدهٔ سیاست (حداقل یک راه تماس برای انتشار؛ فقط آگهی جاری قابل اعلام
آمادگی؛ upsert یکتا به ازای کاربر) یک‌جا و آزمون‌پذیر بماند.
"""

from __future__ import annotations

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import F
from django.utils import timezone

from apps.kindness_wall.choices import DEFAULT_LISTING_TTL_DAYS, ListingStatus, OfferStatus
from apps.kindness_wall.models import KindnessCategory, KindnessListing, KindnessOffer
from apps.kindness_wall.validators import validate_at_least_one_contact


class KindnessWallServiceError(Exception):
    """خطای لایهٔ سرویس با پیام خوانای فارسی برای کاربر/ادمین."""


class KindnessListingStateError(KindnessWallServiceError):
    """گذار وضعیت نامعتبر برای آگهی."""


class KindnessOfferError(KindnessWallServiceError):
    """قاعدهٔ اعلام آمادگی نقض شده است."""


class KindnessCategoryGuardError(KindnessWallServiceError):
    """حذف/غیرفعال‌سازی دسته به دلیل وابستگی داده ممکن نیست."""


def listing_ttl_days() -> int:
    """TTL پیش‌فرض آگهی از settings؛ fallback به ثابت اپ."""
    return int(getattr(settings, "KINDNESS_LISTING_TTL_DAYS", DEFAULT_LISTING_TTL_DAYS))


@transaction.atomic
def set_category_active(*, category: KindnessCategory, active: bool) -> KindnessCategory:
    """فعال/غیرفعال کردن دسته با نگهبان «دیوار خالی نشود»."""
    if not active and category.listings.filter(status=ListingStatus.PUBLISHED).exists():
        raise KindnessCategoryGuardError(
            "این دسته آگهی جاری دارد؛ ابتدا آگهی‌هایش را برطرف/بایگانی کنید."
        )
    category.is_active = active
    category.save(update_fields=["is_active", "updated_at"])
    return category


def _assert_publishable(listing: KindnessListing) -> None:
    """هر مسیر انتشار باید از همین یک بررسی عبور کند."""
    missing: list[str] = []
    if not (listing.title or "").strip():
        missing.append("عنوان")
    if not (listing.description or "").strip():
        missing.append("شرح نیاز")
    if listing.category_id is None:
        missing.append("دسته")
    if missing:
        raise KindnessWallServiceError(
            "این موارد برای انتشار کامل نیستند: " + "، ".join(missing) + "."
        )
    try:
        validate_at_least_one_contact(listing.channel_values())
    except ValidationError as exc:
        raise KindnessWallServiceError(exc.messages[0]) from exc


@transaction.atomic
def publish_listing(*, listing: KindnessListing) -> KindnessListing:
    """انتشار روی دیوار؛ TTL در صورت نبود تنظیم می‌شود."""
    _assert_publishable(listing)
    now = timezone.now()
    listing.status = ListingStatus.PUBLISHED
    if listing.published_at is None:
        listing.published_at = now
    if listing.expires_at is None or listing.expires_at <= now:
        listing.expires_at = now + timezone.timedelta(days=listing_ttl_days())
    listing.save(update_fields=["status", "published_at", "expires_at", "updated_at"])
    return listing


@transaction.atomic
def renew_listing(*, listing: KindnessListing) -> KindnessListing:
    """تمدید انقضا از همین لحظه (نه از انقضای قبلی) — دیوار همیشه تازه بماند."""
    if listing.status not in {ListingStatus.PUBLISHED, ListingStatus.EXPIRED}:
        raise KindnessListingStateError("فقط آگهی جاری یا منقضی قابل تمدید است.")
    now = timezone.now()
    listing.status = ListingStatus.PUBLISHED
    listing.expires_at = now + timezone.timedelta(days=listing_ttl_days())
    listing.renew_count = listing.renew_count + 1
    if listing.published_at is None:
        listing.published_at = now
    listing.save(
        update_fields=["status", "expires_at", "renew_count", "published_at", "updated_at"]
    )
    return listing


@transaction.atomic
def fulfill_listing(*, listing: KindnessListing, note: str = "") -> KindnessListing:
    """«نیاز برطرف شد» — خروج افتخارآمیز از دیوار به بایگانی داستان‌ها."""
    if listing.status not in {ListingStatus.PUBLISHED, ListingStatus.EXPIRED}:
        raise KindnessListingStateError("فقط آگهی جاری یا منقضی قابل ثبت برطرف‌شدن است.")
    listing.status = ListingStatus.FULFILLED
    listing.fulfilled_at = timezone.now()
    if note.strip():
        listing.fulfillment_note = note.strip()
    listing.save(update_fields=["status", "fulfilled_at", "fulfillment_note", "updated_at"])
    return listing


@transaction.atomic
def archive_listing(*, listing: KindnessListing) -> KindnessListing:
    """بایگانی دستی (بدون حذف فیزیکی؛ slug هم آزاد نمی‌شود تا لینکها نمیرند)."""
    listing.status = ListingStatus.ARCHIVED
    listing.save(update_fields=["status", "updated_at"])
    return listing


@transaction.atomic
def revert_to_draft(*, listing: KindnessListing) -> KindnessListing:
    """بازگرداندن هر وضعیتی به پیش‌نویس (ویرایش ادمین پیش از انتشار مجدد)."""
    listing.status = ListingStatus.DRAFT
    listing.save(update_fields=["status", "updated_at"])
    return listing


@transaction.atomic
def set_featured(*, listing: KindnessListing, featured: bool) -> KindnessListing:
    """ویژه/ثبیت بالای دیوار."""
    listing.is_featured = featured
    listing.save(update_fields=["is_featured", "updated_at"])
    return listing


def bump_listing_view_count(*, listing: KindnessListing) -> None:
    """شمارش بازدید با F() مستقیم — عمداً بدون save تا سیگنال کش شعله‌ور نشود."""
    KindnessListing.all_objects.filter(pk=listing.pk).update(view_count=F("view_count") + 1)


def expire_due_listings() -> int:
    """منقضی‌کردن دسته‌ای آگهی‌های جاریِ گذشته از ``expires_at`` (اجرای تسک beat)."""
    now = timezone.now()
    stale_ids = list(
        KindnessListing.objects.filter(
            status=ListingStatus.PUBLISHED, expires_at__lte=now
        ).values_list("pk", flat=True)[:1000]
    )
    if not stale_ids:
        return 0
    updated = KindnessListing.all_objects.filter(pk__in=stale_ids).update(
        status=ListingStatus.EXPIRED, updated_at=now
    )
    return int(updated)


@transaction.atomic
def submit_offer(
    *, listing: KindnessListing, user, message: str = ""
) -> tuple[KindnessOffer, bool]:
    """اعلام آمادگی؛ upsert یکتا به‌ازای (آگهی، کاربر).

    Returns:
        (offer, created): ``created=False`` یعنی پیام قبلی به‌روز شد.
    """
    if not listing.is_public:
        raise KindnessOfferError("این آگهی روی دیوار نیست؛ اعلام آمادگی معنایی ندارد.")
    offer = KindnessOffer.objects.filter(listing=listing, user=user).first()
    if offer is None:
        # سیاست v2: اعلام آمادگی فقط ثبت می‌شود؛ هماهنگی نهایی خارج از اپ و
        # از طریق راه‌های تماس خودِ آگهی انجام می‌شود (بدون انبار اعلان/مچینگ).
        offer = KindnessOffer.objects.create(
            listing=listing, user=user, message=(message or "").strip()
        )
        return offer, True
    if offer.status != OfferStatus.NEW:
        raise KindnessOfferError(
            "اعلام آمادگی شما بررسی شده است؛ برای پیگیری مستقیم از راه‌های تماس آگهی استفاده کنید."
        )
    offer.message = (message or "").strip()
    offer.save(update_fields=["message", "updated_at"])
    return offer, False


@transaction.atomic
def withdraw_offer(*, offer: KindnessOffer, user) -> None:
    """انصراف داوطلب — فقط تا پیش از بررسی ادمین."""
    if offer.user_id != user.pk:
        raise KindnessOfferError("فقط صاحب اعلام آمادگی می‌تواند آن را پس بگیرد.")
    if offer.status != OfferStatus.NEW:
        raise KindnessOfferError("این اعلام آمادگی بررسی شده و قابل پس‌گرفتن نیست.")
    offer.delete()


@transaction.atomic
def review_offer(*, offer: KindnessOffer, admin, status: str, note: str = "") -> KindnessOffer:
    """ثبت نتیجهٔ پیگیری ادمین روی یک اعلام آمادگی.

    داوطلب نتیجه را در «اعلام‌های من» می‌بیند؛ سیاست v2 اعلان درون‌اپی برای
    این مسیر ندارد (هماهنگی اصلی تلفنی/پیامی و خارج از اپ است).
    """
    if status not in OfferStatus.values:
        raise KindnessWallServiceError("وضعیت اعلام آمادگی نامعتبر است.")
    offer.status = status
    offer.handled_by = admin
    offer.handled_at = timezone.now()
    if note.strip():
        offer.admin_note = note.strip()
    offer.save(update_fields=["status", "handled_by", "handled_at", "admin_note", "updated_at"])
    return offer

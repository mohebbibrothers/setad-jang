"""لایهٔ نوشتاری (services) دیوار مهربانی — تنها دروازهٔ تغییر وضعیت‌ها.

انتشار/تمدید/برطرف‌سازی/بایگانی و ثبت اعلام آمادگی همه از اینجا می‌گذرند تا
قاعدهٔ سیاست (حداقل یک راه تماس برای انتشار؛ فقط آگهی جاری قابل اعلام
آمادگی؛ upsert یکتا به ازای کاربر) یک‌جا و آزمون‌پذیر بماند.
"""

from __future__ import annotations

import contextlib
import hashlib
import logging
import re

from django.conf import settings
from django.core.cache import cache
from django.core.exceptions import ValidationError
from django.db import IntegrityError, OperationalError, ProgrammingError, transaction
from django.db.models import F
from django.utils import timezone

from apps.core.cache import make_cache_key
from apps.core.client_ip import get_client_ip
from apps.kindness_wall.choices import DEFAULT_LISTING_TTL_DAYS, ListingStatus, OfferStatus
from apps.kindness_wall.models import (
    KindnessCategory,
    KindnessListing,
    KindnessListingView,
    KindnessOffer,
)
from apps.kindness_wall.validators import validate_at_least_one_contact

logger = logging.getLogger(__name__)


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


# ══════════════════════════════════════════════════════════════════════════
#  شمارشِ بازدیدِ امن (dedupe + throttle)
# ══════════════════════════════════════════════════════════════════════════
# قرارداد پیشین: هر بار که صفحهٔ جزئیات رندر می‌شد — حتی revalidate یا
# prefetchِ سروری — شمارنده یک واحد بالا می‌رفت. نتیجه: عددی بی‌معنا (یک
# بازدیدِ واقعی می‌توانست صدها شمارش بسازد) و ناتوانی در تفکیکِ «آدم» از
# «کرالر».
#
# قرارداد جدید: شمارش از سمتِ **مرورگر** با یک beacon سبک انجام می‌شود و
# تابعِ زیر پنجرهٔ dedupe دارد:
#   • هر بیننده (کاربرِ واردشده یا اثرِ انگشت‌نگاریِ IP+UA) در هر پنجره فقط
#     **یک** شمارش تولید می‌کند؛
#   • کلیدِ dedupe با `cache.add` نوشته می‌شود که در Redis/LocMem اتمیک است،
#     پس دو درخواستِ هم‌زمان هم دوبار نمی‌شمارند؛
#   • خطای cache هرگز مسیرِ کاربر را نمی‌شکند: در بدترین حالت «شمارش انجام
#     شد» فرض می‌شود (fail-open برای تجربه، با لاگ) چون از دست دادنِ یک
#     شمارشِ آماری بسیار کم‌هزینه‌تر از خطای ۵۰۰ برای بازدیدکننده است؛
#   • کارکنان/ادمین هرگز شمارش نمی‌شوند (پیش‌نمایشِ ادمین آمار را آلوده
#     نمی‌کند).

#: پنجرهٔ dedupe پیش‌فرض — شش ساعت. «بازدیدِ مجددِ همان آدم در همان روز»
#: دوباره شمرده نمی‌شود، ولی بازگشتِ فردا یک بازدیدِ تازه است.
DEFAULT_VIEW_DEDUPE_SECONDS = 6 * 60 * 60


def _view_dedupe_window() -> int:
    """پنجرهٔ dedupe از تنظیمات (قابل تغییر بدونِ کد)."""
    raw = getattr(settings, "KINDNESS_VIEW_DEDUPE_SECONDS", DEFAULT_VIEW_DEDUPE_SECONDS)
    try:
        value = int(raw)
    except (TypeError, ValueError):
        return DEFAULT_VIEW_DEDUPE_SECONDS
    return value if value > 0 else DEFAULT_VIEW_DEDUPE_SECONDS


#: شناسهٔ بینندهٔ کلاینتی: کاراکترهای امن، طولِ معقول. مقدار توسط خودِ مرورگر
#: (localStorage) ساخته و فرستاده می‌شود تا dedupe به IP/پروکسی وابسته نباشد.
_CLIENT_VIEWER_ID_RE = re.compile(r"^[A-Za-z0-9_-]{8,64}$")


def viewer_fingerprint(*, request) -> str:
    """اثرِ یکتای بیننده برای dedupe — هرگز خودِ IP/UA خام ذخیره نمی‌شود.

    ترتیبِ اعتماد (پایدارترین اول):

    ۱) **کاربرِ واردشده** → شناسهٔ کاربر. مستقل از دستگاه و شبکه.
    ۲) **شناسهٔ کلاینتی** (`X-Viewer-Id`) → UUIDِ تصادفی که مرورگر یک‌بار
       می‌سازد و در localStorage نگه می‌دارد.

       ⚠️ چرا این لازم شد (یافتهٔ آزمونِ زنده روی production): پیش‌تر اثرِ
       مهمان از هشِ «IP + User-Agent» ساخته می‌شد. ترافیک از لبهٔ Vercel
       می‌آید و `REMOTE_ADDR`ی که به جنگو می‌رسد **IPِ خروجیِ Vercel** است که
       بین درخواست‌ها تغییر می‌کند (`NUM_PROXIES=0` هم عمداً XFF را معتبر
       نمی‌داند). نتیجه: یک مرورگر در هر درخواست «بینندهٔ تازه» به نظر
       می‌رسید و شمارنده چند برابر می‌شد. شناسهٔ کلاینتی این وابستگی را کامل
       حذف می‌کند: یک مرورگر = یک شناسه، مستقل از IP، پردازه و شبکه.

    ۳) **هشِ IP+UA** → فقط پشتیبان برای کلاینت‌هایی که هدر را نمی‌فرستند
       (مثلاً درخواستِ مستقیم به API). همان‌جا هم IP خام ذخیره نمی‌شود.

    نکتهٔ امنیتی: هدرِ شناسه قابلِ جعل است، ولی جعلِ آن فقط روی **dedupe**
    اثر دارد (شمارشِ آماری) و نه دسترسی/داده. سقفِ throttleِ beacon
    (`kindness_view_anon`) جلوی بادکردنِ عمدیِ عدد را می‌گیرد؛ و چون شمارش
    یک سیگنالِ نرم است، این مبادله (دقتِ بالا برای کاربرِ عادی، سقفِ سخت برای
    مهاجم) پذیرفتنی است.
    """
    user = getattr(request, "user", None)
    if user is not None and getattr(user, "is_authenticated", False):
        return f"u{user.pk}"

    meta = getattr(request, "META", {}) or {}
    client_id = str(meta.get("HTTP_X_VIEWER_ID", "") or "").strip()
    if _CLIENT_VIEWER_ID_RE.match(client_id):
        # پیشوندِ «c» = client؛ هشِ شناسه تا طولِ ردیف کوتاه و ثابت بماند.
        digest = hashlib.sha256(client_id.encode()).hexdigest()[:20]
        return f"c{digest}"

    ip = get_client_ip(request) or "unknown"
    ua = str(meta.get("HTTP_USER_AGENT", ""))[:180]
    digest = hashlib.sha256(f"{ip}|{ua}".encode()).hexdigest()[:16]
    return f"g{digest}"


def view_window_index(*, now=None) -> int:
    """شمارهٔ پنجرهٔ جاری = floor(timestamp / طولِ پنجره).

    چرا «شماره» و نه «بازهٔ تاریخ»؟ چون با تغییرِ طولِ پنجره در تنظیمات، همهٔ
    شماره‌ها به‌طور طبیعی جابه‌جا می‌شوند و نیازی به مهاجرت/پاک‌سازی نیست.
    """
    moment = now or timezone.now()
    window = _view_dedupe_window()
    return int(moment.timestamp()) // window


def _try_mark_view(*, listing: KindnessListing, fingerprint: str, window: int) -> bool | None:
    """ثبتِ اتمیکِ اثرِ بازدید در دیتابیس.

    برمی‌گرداند:
      • ``True``  → این بیننده در این پنجره تازه شمرده شد
      • ``False`` → قبلاً شمرده شده بود (constraint یکتا جلوی درجِ دوم را گرفت)
      • ``None``  → **لایهٔ دیتابیس در دسترس نیست** (مثلاً جدولِ مهاجرت اعمال
        نشده). این حالت عمداً از «قبلاً شمرده شده» جدا است تا caller بتواند
        به لایهٔ کش عقب‌نشینی کند و هرگز ۵۰۰ ندهد.
    """
    try:
        with transaction.atomic():
            _mark, created = KindnessListingView.objects.get_or_create(
                listing=listing,
                viewer_key=fingerprint,
                window_start=window,
            )
            return created
    except IntegrityError:
        # درجِ هم‌زمان از پردازهٔ دیگر — همان محدودیتِ یکتا کارِ خودش را کرد.
        return False
    except (OperationalError, ProgrammingError):
        # جدولِ اثرِ بازدید در دسترس نیست (مهاجرت اعمال نشده / دیتابیسِ قدیمی).
        # این یک نقصِ عملیاتی است، نه خطای کاربر: لاگ می‌کنیم و با کش ادامه
        # می‌دهیم تا شمارنده هرگز صفحه/درخواست را نشکند.
        logger.warning(
            "جدولِ اثرِ بازدید در دسترس نیست (kindness_wall.0007 اعمال نشده؟) — dedupe موقتاً روی کش",
            exc_info=True,
        )
        return None
    except Exception:
        logger.exception("ثبتِ اثرِ بازدیدِ آگهی %s ناموفق بود", listing.pk)
        return None


def register_listing_view(*, listing: KindnessListing, request) -> tuple[bool, int]:
    """ثبتِ یک بازدیدِ **یکتا**؛ برمی‌گرداند (شمارش‌شد؟, عددِ تازه).

    سه لایه، به‌ترتیبِ اعتماد:
      ۱) **دیتابیس** (منبعِ حقیقت): constraint یکتا روی (آگهی، بیننده،
         پنجره). درجِ دوم — حتی از پردازهٔ دیگر یا هم‌زمان — رد می‌شود.
      ۲) **کش** (مسیرِ سریع): اگر همین پردازه بداند این بیننده شمرده شده،
         بدونِ لمسِ دیتابیس برمی‌گردد. صرفاً بهینه‌سازی.
      ۳) **پشتیبانِ کش** (fail-safe): اگر لایهٔ دیتابیس در دسترس نبود،
         `cache.add` اتمیکِ همان پردازه تنها ضامنِ موجود است. dedupe بینِ
         پردازه‌ها کامل نیست، ولی شمارنده کار می‌کند و هیچ درخواستی ۵۰۰
         نمی‌شود — و به‌محضِ اعمالِ مهاجرت، لایهٔ اول خودکار برمی‌گردد.
    """
    window = view_window_index()
    fingerprint = viewer_fingerprint(request=request)

    # ── مسیرِ سریع: همین پردازه قبلاً این بیننده را در همین پنجره دیده است.
    fast_key = make_cache_key("kindness:view_seen", listing.pk, window, fingerprint)
    with contextlib.suppress(Exception):
        if cache.get(fast_key):
            return False, _current_view_count(listing)

    db_result = _try_mark_view(listing=listing, fingerprint=fingerprint, window=window)

    if db_result is None:
        # پشتیبان: dedupe فقط در همین پردازه (بهترین تلاش).
        cache_ok = False
        with contextlib.suppress(Exception):
            cache_ok = bool(cache.add(fast_key, 1, timeout=_view_dedupe_window()))
        counted = cache_ok
    else:
        counted = db_result

    if counted:
        try:
            bump_listing_view_count(listing=listing)
        except Exception:
            logger.exception("افزایشِ شمارندهٔ بازدیدِ آگهی %s ناموفق بود", listing.pk)

    # ثبتِ مسیرِ سریع (بدونِ اثر بر درستیِ شمارش)
    with contextlib.suppress(Exception):
        cache.set(fast_key, 1, timeout=_view_dedupe_window())

    return counted, _current_view_count(listing)


def _current_view_count(listing: KindnessListing) -> int:
    """عددِ تازهٔ بازدید از دیتابیس (تک‌ستونی و ارزان)."""
    fresh = (
        KindnessListing.all_objects.filter(pk=listing.pk)
        .values_list("view_count", flat=True)
        .first()
    )
    return int(fresh or 0)


def purge_stale_listing_views(*, keep_windows: int = 2) -> int:
    """پاک‌سازیِ اثرهای بازدیدِ قدیمی؛ برمی‌گرداند تعدادِ ردیف‌های حذف‌شده.

    دو پنجرهٔ گذشته نگه داشته می‌شود تا پنجرهٔ جاری و قبلی (که ممکن است هنوز
    در حالِ محاسبه باشد) دست‌نخورده بمانند. این تابع از تسکِ دوره‌ای صدا زده
    می‌شود تا جدول در طولِ سال کوچک بماند.
    """
    threshold = view_window_index() - max(1, int(keep_windows))
    deleted, _details = KindnessListingView.objects.filter(window_start__lt=threshold).delete()
    if deleted:
        logger.info("پاک‌سازیِ اثرهای بازدید: %s ردیف حذف شد", deleted)
    return int(deleted)


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

"""Enum‌ها و ثبات‌های سیاست‌محورِ «دیوار مهربانی» (نسخه ۲).

سیاست نسخه ۲: تنها *ادمین* نویسندهٔ محتواست — دسته‌بندی‌ها و آگهی‌های
«نیاز» را او می‌سازد؛ کاربران عمومی فقط می‌بینند، جست‌وجو می‌کنند و از
راه‌های ارتباطیِ *در همان آگهی* با صاحب نیاز تماس می‌گیرند. به همین دلیل
هیچ مسیر نگاشتِ محتوا برای کاربر عادی وجود ندارد و مجموعهٔ enum‌ها به
حداقلِ معنادار رسیده است.
"""

from __future__ import annotations

from django.db import models


class ListingStatus(models.TextChoices):
    """چرخهٔ حیات یک آگهی نیاز در دیوار."""

    DRAFT = "draft", "پیش‌نویس"
    PUBLISHED = "published", "جاری روی دیوار"
    FULFILLED = "fulfilled", "برطرف‌شده"
    EXPIRED = "expired", "منقضی‌شده"
    ARCHIVED = "archived", "بایگانی‌شده"

    @classmethod
    def board_statuses(cls) -> tuple[str, ...]:
        """وضعیت‌هایی که روی تختهٔ عمومی دیده می‌شوند."""
        return (cls.PUBLISHED,)


class Urgency(models.TextChoices):
    """اولویتِ نیاز؛ روی چیدمان تخته و برچسب کارت اثر می‌گذارد."""

    NORMAL = "normal", "عادی"
    URGENT = "urgent", "فوری"


class OfferStatus(models.TextChoices):
    """وضعیت اعلام آمادگیِ کاربر برای کمک در یک آگهی."""

    NEW = "new", "جدید"
    CONTACTED = "contacted", "تماس گرفته شد"
    DECLINED = "declined", "رد شد"


class ContactChannelKind(models.TextChoices):
    """نوعِ راه ارتباطی قابل قبول برای هر آگهی."""

    PHONE = "phone", "شماره تماس"
    BALE = "bale", "بله"
    EITAA = "eitaa", "ایتا"
    TELEGRAM = "telegram", "تلگرام"
    RUBIKA = "rubika", "روبیکا"
    INSTAGRAM = "instagram", "اینستاگرام"


#: نگاشت یکتای «نام فیلد روی مدل → (کد کانال، برچسب فارسی، لینک وب)».
#: همهٔ لایه‌ها (سریالایزر، اکسل، فرم ادمین، export) از همین یک جدول
#: خوانده می‌شوند؛ افزودن کانال جدید = یک سطر اینجا + یک فیلد روی مدل.
#: ``url_prefix`` برای کانال‌هایی است که لینک عمومیِ معتبر دارند؛ ``bale``
#: عمداً خالی است چون دامنهٔ لینک پروفایلِ عمومیِ رسمیِ مستقری ندارد و
#: مقدار خام همان آیدی به کاربر نشان داده می‌شود.
CONTACT_CHANNEL_REGISTRY: tuple[tuple[str, str, str, str], ...] = (
    ("contact_phone", "phone", "شماره تماس", "tel:"),
    ("contact_bale", "bale", "آیدی بله", ""),
    ("contact_eitaa", "eitaa", "آیدی ایتا", "https://eitaa.com/"),
    ("contact_telegram", "telegram", "آیدی تلگرام", "https://t.me/"),
    ("contact_rubika", "rubika", "آیدی روبیکا", "https://rubika.ir/"),
    ("contact_instagram", "instagram", "آیدی اینستاگرام", "https://instagram.com/"),
)

#: تنظیمات کشِ تخته — TTL پیش‌فرض هر آگهی پس از انتشار (روز).
DEFAULT_LISTING_TTL_DAYS = 45

#: تعداد پیش‌فرض و سقفِ «نیازهای مشابه» در صفحهٔ جزئیات.
#: پیش‌فرض ۴ = یک ردیفِ کامل در گریدِ سه‌ستونهٔ دسکتاپ (۳) + یک یتیمِ خوش‌نشین،
#: و در موبایل ۴ کارتِ پشتِ‌هم. سقف ۱۲ عمداً کم است تا پاسخ سبک بماند و
#: صفحهٔ جزئیات هرگز به یک فهرستِ موازی تبدیل نشود.
RELATED_DEFAULT_LIMIT = 4
RELATED_MAX_LIMIT = 12

#: سقف تصاویر هر آگهی (سنگینی مدیا روی هاست اشتراکی + سرعت صفحه).
MAX_IMAGES_PER_LISTING = 8

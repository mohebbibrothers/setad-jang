"""زیرسیستمِ جغرافیای خانه (geo) — استان/شهر به‌عنوان یک منبعِ حقیقتِ واحد.

چرا این پکیج وجود دارد؟
────────────────────────
پیش از این، «استان» و «شهر» در `KindnessListing` دو `CharField` آزاد بودند؛ ادمین
هر چیزی می‌توانست تایپ کند («تهران»، «طهران»، «تهران ۱»، «ت هران»). نتیجه:

  • فیلترِ فرانت (`?city=…` با `iexact`) برای همان آگهی هرگز نتیجه نمی‌داد؛
  • لیستِ شهرهای دراپ‌دانِ فرانت با دادهٔ واقعیِ ادمین هم‌خوان نبود؛
  • هیچ اعتبارسنجی‌ای جلوی اشتباهِ تایپی را نمی‌گرفت.

راه‌حل: یک دیتاستِ رسمیِ بسته‌بندی‌شده (`data/iran-places.json` — ۳۱ استان و
۱٬۴۵۸ شهر، منبعِ رسمی ۱۴۰۴) به‌عنوان تنها منبعِ نام‌ها، با API عمومی و ویجتِ
وابستهٔ ادمین. نامِ استان/شهرِ ورودی با همین دیتاست اعتبارسنجی و نرمال می‌شود،
پس آنچه ادمین انتخاب می‌کند دقیقاً همان چیزی است که در فیلترِ فرانت وجود دارد.

روستا/محله: دیتاستِ رسمیِ روستاها ~۳۲MB است و عمداً در مخزن نیست. با تنظیمِ
`IRAN_LOCALITIES_JSON` (مسیر فایلِ JSON با ساختار
`{"استان": ["روستا۱", ...]}` یا لیستِ تخت) بدون هیچ تغییرِ کدی فعال می‌شود؛
تا آن زمان، فیلدِ «روستا/محله» متنِ آزادِ اختیاری است.
"""

from apps.core.geo.dataset import (
    PROVINCE_CHOICES,
    PROVINCE_NAMES,
    PROVINCE_TEL_PREFIXES,
    cities_of,
    is_known_city,
    is_known_province,
    localities_of,
    normalize_city,
    normalize_province,
    places_catalog,
    province_index,
    validate_place_pair,
)
from apps.core.geo.validators import validate_iran_place

__all__ = [
    "PROVINCE_CHOICES",
    "PROVINCE_NAMES",
    "PROVINCE_TEL_PREFIXES",
    "cities_of",
    "is_known_city",
    "is_known_province",
    "localities_of",
    "normalize_city",
    "normalize_province",
    "places_catalog",
    "province_index",
    "validate_iran_place",
    "validate_place_pair",
]

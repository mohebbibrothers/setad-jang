"""
Identity-aware throttling primitives shared by every app.

انگیزهٔ این ماژول یک باگ امنیتی واقعی است:

`rest_framework.throttling.AnonRateThrottle.get_cache_key()` وقتی کاربر
احراز هویت شده باشد `None` برمی‌گرداند و DRF آن throttle را کاملاً skip
می‌کند. بنابراین هر endpointی که همزمان `IsAuthenticated` باشد و throttle
آن از `AnonRateThrottle` ارث ببرد، عملاً **بدون هیچ محدودیتی** اجرا می‌شود.

کلاس‌های این ماژول تضمین می‌کنند که:

1. `get_cache_key()` هرگز `None` برنمی‌گرداند — یعنی throttle هرگز
   bypass نمی‌شود، نه برای anonymous و نه برای authenticated.
2. bucket کاربر احراز هویت‌شده و bucket IP از هم جدا هستند، پس یک
   کاربر لاگین‌کرده نمی‌تواند سهمیهٔ anonymousها را مصرف کند و برعکس.
3. مقادیر حساس (شماره موبایل/ایمیل) هرگز به‌صورت plaintext وارد
   cache key نمی‌شوند؛ با `salted_hmac` امضا و کوتاه می‌شوند.

سه محور throttle در دسترس است و می‌توان آن‌ها را روی هم گذاشت:

- `IdentityRateThrottle`  → «چه کسی» درخواست می‌دهد (user یا IP)
- `ClientIPRateThrottle`  → «از کجا» درخواست می‌دهد (همیشه IP)
- `TargetRateThrottle`    → «برای چه کسی» درخواست می‌دهد (گیرندهٔ پیام)

محور سوم چیزی است که جلوی SMS-bombing را می‌گیرد: مهاجم می‌تواند اکانت
و IP عوض کند، ولی نمی‌تواند شمارهٔ قربانی را عوض کند.
"""

from __future__ import annotations

from typing import Any

from django.utils.crypto import salted_hmac
from rest_framework.throttling import SimpleRateThrottle

from apps.core.client_ip import get_client_ip as _resolve_client_ip

# فضای نام امضای HMAC برای cache keyهای throttle
_THROTTLE_HMAC_SALT = "apps.core.throttling.target"

# طول دایجست کوتاه‌شده در cache key (۱۶ بایت = ۱۲۸ بیت، کافی برای عدم برخورد)
_TARGET_DIGEST_LENGTH = 32


def digest_throttle_target(value: str) -> str:
    """
    ساخت دایجست پایدار و غیرقابل بازگشت از یک مقدار حساس برای cache key.

    از `salted_hmac` با SECRET_KEY استفاده می‌شود تا:
    - شمارهٔ موبایل/ایمیل هرگز plaintext در Redis ذخیره نشود.
    - کسی که فقط به Redis دسترسی دارد نتواند لیست مخاطبان را enumerate کند.

    ``algorithm`` عمداً صریح است: از Django 6.1 پیش‌فرضِ ``salted_hmac``
    منسوخ شده (در 7.0 از sha1 به sha256 تغییر می‌کند) و بدون این پارامتر،
    خروجی تابع به نسخهٔ Django وابسته می‌شد. این keyها کاملاً ephemeral
    هستند (عمر throttle چند ثانیه/دقیقه) و هیچ مقدار ماندگاری برای تطبیق
    ندارند، پس تغییر الگوریتم هیچ سوییچ compatibility نمی‌خواهد.
    """
    return salted_hmac(_THROTTLE_HMAC_SALT, value, algorithm="sha256").hexdigest()[
        :_TARGET_DIGEST_LENGTH
    ]


class NonBypassableRateThrottle(SimpleRateThrottle):
    """
    پایهٔ تمام throttleهایی که اجازه ندارند هرگز skip شوند.

    برخلاف `AnonRateThrottle`/`UserRateThrottle` که در شرایط خاص
    `None` برمی‌گردانند، این کلاس همیشه یک کلید معتبر تولید می‌کند.
    زیرکلاس‌ها فقط `get_bucket_ident()` را پیاده می‌کنند.
    """

    #: پیشوند bucket برای جدا نگه‌داشتن محورهای مختلف throttle از هم
    bucket_prefix = "any"

    cache_format = "throttle_%(prefix)s_%(scope)s_%(ident)s"

    def get_ident(self, request: Any) -> str:
        """تعیین IP کلاینت به‌صورت fail-closed (یافتهٔ P1 ممیزی).

        عمداً DRF را override می‌کنیم: ``SimpleRateThrottle.get_ident`` وقتی
        ``NUM_PROXIES`` تنظیم نشده باشد (حالت پیش‌فرض این پروژه پیش از این
        رفع)، ``X-Forwarded-For`` ورودی را **بدون راستی‌آزمایی** می‌پذیرد —
        یعنی مهاجم با یک header، هم سهمیهٔ throttle را دور می‌زند و هم IP
        جعلی وارد audit/لاگ‌ها می‌کند. حتی با ``NUM_PROXIES=k`` تنظیم‌شده،
        DRF برای زنجیرهٔ کوتاه‌تر سراغ چپ‌ترین (جعل‌پذیرترین) مقدار می‌رود.

        قرارداد جایگزین (``apps.core.client_ip.get_client_ip``):
        NUM_PROXIES=0 (پیش‌فرض) → فقط REMOTE_ADDR؛ NUM_PROXIES=k → k-امین
        مقدار از راستِ XFF و فقط وقتی زنجیره به‌اندازهٔ کافی بلند است؛
        هر حالت معیوب → REMOTE_ADDR (نه header).
        """
        return _resolve_client_ip(request) or ""

    def get_bucket_ident(self, request: Any, view: Any) -> str:
        """
        شناسهٔ bucket برای این درخواست.

        زیرکلاس باید این متد را override کند. پیاده‌سازی پایه عمداً خطا
        می‌دهد تا یک زیرکلاس ناقص به‌صورت بی‌صدا throttle را غیرفعال نکند.
        """
        raise RuntimeError(f"{type(self).__name__} باید get_bucket_ident را پیاده‌سازی کند.")

    def get_cache_key(self, request: Any, view: Any) -> str | None:
        """ساخت cache key؛ هرگز None برنمی‌گرداند مگر bucket عمداً حذف شده باشد."""
        ident = self.get_bucket_ident(request, view)
        if not ident:
            return None
        return self.cache_format % {
            "prefix": self.bucket_prefix,
            "scope": self.scope,
            "ident": ident,
        }


class IdentityRateThrottle(NonBypassableRateThrottle):
    """
    محدودیت بر اساس هویت درخواست‌دهنده.

    - کاربر احراز هویت‌شده → bucket اختصاصی همان کاربر (`u<pk>`)
    - کاربر ناشناس        → bucket آدرس IP (`a<ip>`)

    این کلاس جایگزین مستقیم `AnonRateThrottle` است بدون حفرهٔ bypass آن.
    """

    bucket_prefix = "id"

    def get_bucket_ident(self, request: Any, view: Any) -> str:
        """برگرداندن شناسهٔ کاربر در صورت احراز هویت، وگرنه IP کلاینت."""
        user = getattr(request, "user", None)
        if user is not None and getattr(user, "is_authenticated", False):
            return f"u{user.pk}"
        return f"a{self.get_ident(request)}"


class ClientIPRateThrottle(NonBypassableRateThrottle):
    """
    محدودیت همیشگی بر اساس IP کلاینت، مستقل از وضعیت احراز هویت.

    این لایه برای جلوگیری از enumeration به کار می‌رود: مهاجمی که چند
    اکانت دارد هم نمی‌تواند از یک IP بیش از سهمیه درخواست بفرستد.
    """

    bucket_prefix = "ip"

    def get_bucket_ident(self, request: Any, view: Any) -> str:
        """برگرداندن IP کلاینت طبق قرارداد fail-closed پروژه.

        (یافتهٔ P1 ممیزی): این متد از ``apps.core.client_ip`` استفاده
        می‌کند، نه ``SimpleRateThrottle.get_ident`` — قرارداد DRF وقتی
        ``NUM_PROXIES`` تنظیم نشده XFF ورودی را معتبر می‌داند (جعل‌پذیر).
        """
        return str(self.get_ident(request))


class TargetRateThrottle(NonBypassableRateThrottle):
    """
    محدودیت بر اساس «گیرندهٔ» عملیات، نه درخواست‌دهنده.

    این تنها محوری است که جلوی SMS/Email bombing را واقعاً می‌گیرد:
    مهاجم می‌تواند IP و اکانت عوض کند، ولی شمارهٔ قربانی ثابت است.

    اگر هیچ فیلد هدفی در body پیدا نشود، `None` برگردانده می‌شود و این
    throttle کنار می‌رود؛ در آن حالت محورهای identity/IP همچنان فعال‌اند
    و درخواست بدون هدف در لایهٔ serializer رد خواهد شد.
    """

    bucket_prefix = "tgt"

    #: نام فیلدهایی که ممکن است هدف ارسال را در body حمل کنند
    target_fields: tuple[str, ...] = ()

    def get_target_value(self, request: Any) -> str:
        """استخراج اولین مقدار غیرخالی از فیلدهای هدف در body درخواست."""
        try:
            data = request.data
        except Exception:
            return ""
        if not hasattr(data, "get"):
            return ""
        for field in self.target_fields:
            value = data.get(field)
            if isinstance(value, str) and value.strip():
                return value.strip().casefold()
        return ""

    def get_bucket_ident(self, request: Any, view: Any) -> str:
        """برگرداندن دایجست امن هدف، یا رشتهٔ خالی در نبود هدف."""
        target = self.get_target_value(request)
        if not target:
            return ""
        return digest_throttle_target(target)

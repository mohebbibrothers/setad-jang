"""سیاست رمز عبور ستاد جنگ — یافتهٔ P2-۸ فاز ۸ ممیزی.

چرا چهار validator پیش‌فرض جانگو کافی نبود:
    طول ۸ +سیاههِ انگلیسیِ General + ممنوعیتِ عددیِ خالص، هیچ‌کدام
    الگوهای واقعیِ کاربر ایرانی را نمی‌گیرند: «Qwer1234» (runهای صفحه‌کلید)،
    «Ali1366» (تولد فینگلیش)، «besat@2024» (نامِ پلتفرم + سال) و
    «Khoda!123» همه زیر سنسورِ پیش‌فرض رد می‌شوند. برای پلتفرمی که پول
    خیریه و سند R4J جابه‌جا می‌کند، رمزِ قابل‌حدس‌زدن یعنی کلِ زنجیرهٔ
    امنیتی (OTP/جست/پنل) دور زده‌شده.

چه اضافه می‌کند (کنار پیش‌فرض‌های جانگو، جایگزین آن‌ها نمی‌شود):
    1. طولِ کف ۱۰ (تنظیم‌پذیر) — بالاتر از ۸ پیش‌فرض.
    2. حداقل ۳ کلاسِ کاراکتر از ۴ کلاس (کوچک/بزرگ/رقم/نماد).
    3. ردِ runهای monotonic و تکراری (1234، abcd، qwer، aaaa) با طول≥۴ —
       الگوریتمِ خطیِ سبک، بدون وابستگیِ خارجی.
    4.سیاههِ بومی: فایل `data/weak_passwords.txt` (رایج‌های انگلیسی +
       فارسیِ فینگلیش + نام‌های خودِ پلتفرم). Normalization قبل از مقایسه:
       ارقام فارسی/عربی→ASCII، حذفِ جداکننده‌های پرکاربرد (`._-@!` و فاصله)
       و lowercase — تا «B e s a t!2024» هم به «besat2024» نگاشت شود.
    5. ممنوعیتِ زیررشته‌ایِ «نامِ پلتفرم/سازمان» و تولدهای ۱۳xx/۱۴xx
       (الگوی مسلطِ رمزهای ایرانی) هرچند در دلِ رمزِ «قوی‌نما».

قراردادِ enqueue: اینجا در `AUTH_PASSWORD_VALIDATORS` ثبت می‌شود، پس هر
مسیری که `django.contrib.auth.password_validation.validate_password` را
صدا می‌زند (هر شش serializer رمز‌ساز پروژه) خودکار پوشش داده می‌شود.
`create_superuser`/ادمن هم از همین لیست عبور می‌کنند — یعنی policy یکسان
برای کاربر و ادمین، بدونِ post-hoc.
"""

from __future__ import annotations

import itertools
import re
import unicodedata
from pathlib import Path
from typing import Final

from django.conf import settings
from django.core.exceptions import ValidationError

# ============================================================
# Constants
# ============================================================

_MIN_LENGTH: Final[int] = 10
_MIN_CHARACTER_CLASSES: Final[int] = 3
_MAX_MONOTONIC_RUN: Final[int] = 4

#: ارقام فارسی/عربی → ASCII (unicode NFKC این کار را برای بیشترشان می‌کند،
#: ولی لیستِ صریح مطمئن‌تر است و با تغییر behavior خودِ unicodedata در
#: نسخه‌های بعدیِ Python نمی‌شکند).
_DIGIT_TRANSLATION: Final[dict[int, str]] = {
    ord(c): str(d) for d, c in enumerate("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩")
}

#: کاراکترهایی که کاربر ایرانی به‌عنوان «جداکنندهٔ تزیینی» وسطِ کلمات
#: می‌گذارد؛ برای مقایسه باسیاهه حذف می‌شوند تا «b3s@t 2024» فرار نکند.
_NOISE_CHARS: Final[str] = " ._-!@#$%^&*+=~`'\"\\/|:;<>()[]{}"

#: ردیف‌های اصلیِ صفحه‌کلید انگلیسی — «QwerTyui!» الگویِ monotonic نیست
#: (فاصلهٔ کدهای کاراکتری یکسان نیست) ولی کلاسیک‌ترین الگویِ انسانی است؛
#: پس زیررشتهٔ ۴تاییِ هر ردیف (به هر دو جهت) رد می‌شود.
_KEYBOARD_ROWS: Final[tuple[str, ...]] = ("qwertyuiop", "asdfghjkl", "zxcvbnm")

#: الگویِ تولدهای شمسیِ رایج (۱۳۰۰ تا ۱۳۹۹) — در رمزهای ایرانی تقریباً
#: همیشه یا سالِ تولد است یا کدِ ملیِ ناقص؛ هر دو سیگنالِ قابل‌حدس‌زدن‌بودن.
_SOLAR_BIRTH_YEAR: Final[re.Pattern[str]] = re.compile(r"13[0-9]{2}")

#: توکن‌های سازمانی که هرگز نباید در رمز ظاهر شوند (حتی به‌عنوان زیررشته).
_PLATFORM_TOKENS: Final[tuple[str, ...]] = ("setadjang", "setad", "jang", "besat")

_BLACKLIST_PATH: Final[Path] = (
    Path(str(getattr(settings, "BASE_DIR", ".")))
    / "apps"
    / "authentication"
    / "data"
    / "weak_passwords.txt"
)


# ============================================================
# Helpers
# ============================================================


def _normalize_for_policy(raw: str) -> str:
    """نگاشتِ رمز به شکلِ مقایسه‌پذیر: NFKC + ارقام ASCII + حذفِ نویز + lowercase.

    عمداً lossy است: فقط برای *مقایسه* به‌کار می‌رود، هرگز برای ذخیره یا
    مقایسهٔ رمزِ واقعی. دو رمزِ متفاوت می‌تواند یک normalize بگیرد و این
    در جهتِ سخت‌گیری است (false-positiveِ reject می‌دهد، never false-negative).
    """
    text = unicodedata.normalize("NFKC", raw)
    text = text.translate(_DIGIT_TRANSLATION)
    text = "".join(ch for ch in text if ch not in _NOISE_CHARS)
    return text.casefold()


def _run_length(value: str) -> int:
    """بلندترین run از کاراکترهای یکسان.

    خطی روی رشته، ولی چون normalize نویزها را حذف کرده، «aaaa@1234» هم
    به‌درستی ۴ می‌شود (نه با شمارشِ خامِ رشتهٔ ورودی).
    """
    longest = 1
    current = 1
    for prev, nxt in itertools.pairwise(value):
        current = current + 1 if nxt == prev else 1
        longest = max(longest, current)
    return longest


def _monotonic_run_length(value: str) -> int:
    """بلندترین run با تفاضلِ ثابتِ کدهای کاراکتری (1234، abcd، qwer، 9753).

    آستانه روی ۴ تنظیم شده چون «abc»/«123» در وسطِ رمزهای تصادفیِ طولانی
    تقریباً اجتناب‌ناپذیرند و هدفِ ما الگوهایِ *عمدیِ* صفحه‌کلید/توالی است،
    نه تصادفِ آماری.
    """
    if len(value) < _MAX_MONOTONIC_RUN:
        return len(value)
    longest = 1
    for step in (1, -1):
        current = 1
        for prev, nxt in itertools.pairwise(value):
            if ord(nxt) - ord(prev) == step:
                current += 1
                longest = max(longest, current)
            else:
                current = 1
    return longest


def _on_keyboard_row(value: str, *, min_len: int = _MAX_MONOTONIC_RUN) -> bool:
    """آیا زیررشته‌ای به طول min_len از ردیفِ صفحه‌کلید (هر دو جهت) در رمز هست؟"""
    for row in _KEYBOARD_ROWS:
        for direction in (row, row[::-1]):
            for i in range(len(value) - min_len + 1):
                if value[i : i + min_len] in direction:
                    return True
    return False


def _load_blacklist() -> frozenset[str]:
    """بارگذاریِ lazyسیاهه؛ فایلِ نبود =سیاههِ خالی (soft-failِ مستند).

    lazy + module-level cache: در فرآیندهایِ وبِ بلندمدت یک‌بار خوانده می‌شود.
    در تست‌ها با monkeypatch روی `_BLACKLIST` قابلِ override است.
    """
    try:
        raw = _BLACKLIST_PATH.read_text(encoding="utf-8")
    except OSError:
        return frozenset()
    return frozenset(
        line.strip() for line in raw.splitlines() if line.strip() and not line.startswith("#")
    )


_BLACKLIST: frozenset[str] | None = None


def _blacklist() -> frozenset[str]:
    """دسترسیِ cached بهسیاهه با راهِ override برای تست."""
    global _BLACKLIST
    if _BLACKLIST is None:
        _BLACKLIST = _load_blacklist()
    return _BLACKLIST


# ============================================================
# Validator
# ============================================================


class BesatPasswordPolicyValidator:
    """سیاستِ ترکیبیِ رمز عبور (کلاس‌ها + الگو +سیاههِ بومی).

    امضای استانداردِ validatorهای جانگو را پیاده می‌کند تا هم از مسیر
    `validate_password()` (پوششِ هر شش serializer پروژه) و هم از
    `createsuperuser` درست صدا زده شود.
    """

    def __init__(self, *, min_length: int | None = None) -> None:
        """min_length فقط برای تست override شده؛ در prod از ثابتِ ماژول."""
        self._min_length = min_length if min_length is not None else _MIN_LENGTH

    def validate(self, password: str, user: object | None = None) -> None:
        """Raise ValidationError اگر رمز هر یک از پنج قرارداد را نقض کند."""
        if not password:
            raise ValidationError("رمز عبور نمی‌تواند خالی باشد.", code="password_empty")

        normalized = _normalize_for_policy(password)

        if len(password) < self._min_length:
            raise ValidationError(
                f"رمز عبور باید حداقل {self._min_length} نویسه باشد.",
                code="password_too_short",
            )

        has_lower = any(c.islower() for c in password)
        has_upper = any(c.isupper() for c in password)
        has_digit = any(c.isdigit() for c in password)
        has_symbol = any(not c.isalnum() and not c.isspace() for c in password)
        classes = sum((has_lower, has_upper, has_digit, has_symbol))
        if classes < _MIN_CHARACTER_CLASSES:
            raise ValidationError(
                "رمز عبور باید حداقل شامل سه دسته از چهار دستهٔ "
                "حرف کوچک، حرف بزرگ، رقم و نماد باشد.",
                code="password_missing_char_classes",
            )

        if _run_length(normalized) >= _MAX_MONOTONIC_RUN or (
            _monotonic_run_length(normalized) >= _MAX_MONOTONIC_RUN
        ):
            raise ValidationError(
                "رمز عبور نباید شامل توالی یا تکرارِ قابل‌پیش‌بینیِ کاراکتر "
                "مانند «۱۲۳۴»، «abcd» یا «aaaa» باشد.",
                code="password_sequential",
            )

        if _on_keyboard_row(normalized):
            raise ValidationError(
                "رمز عبور نباید شامل دنبالهٔ صفحه‌کلید (مثل «qwer» یا «asdf») باشد.",
                code="password_keyboard_row",
            )

        if _SOLAR_BIRTH_YEAR.search(normalized):
            raise ValidationError(
                "رمز عبور نباید شامل سالِ تولد (الگوی ۱۳xx) باشد.",
                code="password_birth_year_pattern",
            )

        for token in _PLATFORM_TOKENS:
            if token in normalized:
                raise ValidationError(
                    "رمز عبور نباید شامل نامِ پلتفرم یا سازمان باشد.",
                    code="password_platform_token",
                )

        if normalized in _blacklist():
            raise ValidationError(
                "این رمز عبور در فهرستِ رمزهای رایج/لو‌رفته قرار دارد.",
                code="password_common",
            )

    def get_help_text(self) -> str:
        """راهنمایِ user-facing (فارسی) برای پیام‌های فرم."""
        return (
            f"رمز شما باید حداقل {_MIN_LENGTH} نویسه، دارای سه دستهٔ کاراکتری، "
            "بدونِ توالی/تکرارِ قابل‌پیش‌بینی و بدونِ سالِ تولد یا نامِ "
            "پلتفرم باشد و از رمزهای رایج نباشد."
        )

"""
Identifier Normalizers — pure functions for canonicalizing user input.

این ماژول فقط شامل توابع pure است: ورودی → خروجی، بدون I/O، بدون DB،
بدون external call. این یعنی این لایه fast, deterministic و کاملاً
test-friendly است.

اصول طراحی:
- Iran-first: شماره‌های ایرانی (محلی، با یا بدون 0 یا +98) با dominant
  detection اولویت دارند، ولی فرمت بین‌المللی E.164 هم پذیرفته می‌شود.
- Email handling: lowercase، trimmed، RFC-compliant validation سبک.
- Attack-safe: ورودی‌های مشکوک (طول غیرعادی، کاراکترهای ناشناخته)
  سریعاً reject می‌شوند با ValidationError.
- Stateless: هر تابع pure است؛ این یعنی به‌راحتی parallelizable است
  و در آینده می‌توان روی این لایه caching یا batching اضافه کرد.

نکته در مورد phone validation:
- این لایه فقط format normalization می‌کند (آیا شماره ساختار درستی دارد).
- بررسی واقعی بودن شماره (active بودن، VoIP بودن، carrier بودن، ...)
  وظیفه‌ی یک Provider جداست (در آینده، اگر خواستیم، مثلاً با Twilio Lookup).
- این separation of concerns در صنعت استاندارد است.
"""

from __future__ import annotations

import re
from typing import Literal

from django.core.exceptions import ValidationError

# ============================================================
# Constants
# ============================================================

# Phone limits — defensive, جلوگیری از ورودی attack-like.
_PHONE_MIN_RAW_LENGTH = 10  # کمتر از این نمی‌تواند یک شماره معتبر باشد
_PHONE_MAX_RAW_LENGTH = 20  # بیشتر از این مشکوک است
_PHONE_MAX_DIGITS = 15  # E.164 حداکثر 15 رقم تعریف می‌کند

# Email limits — RFC 5321 حداکثر 254 برای local+@+domain ولی defensive کوتاه‌تر.
_EMAIL_MAX_LENGTH = 254

# Iran country code prefix (E.164).
_IRAN_E164_PREFIX = "+98"

# الگوهای regex — compiled یک‌بار در زمان import.
_IRAN_LOCAL_PHONE_PATTERN = re.compile(r"^9\d{9}$")  # مثلاً 9120000000 (بدون 0 شروع)
_E164_PATTERN = re.compile(r"^\+\d{10,15}$")  # E.164 standard

# Email regex سبک ولی محکم (نه full-RFC، چون unnecessary complexity).
_EMAIL_PATTERN = re.compile(
    r"^[a-z0-9._%+\-]+@[a-z0-9.\-]+\.[a-z]{2,}$",
    re.IGNORECASE,
)


# ============================================================
# Identifier kind
# ============================================================

IdentifierKind = Literal["email", "phone"]


def detect_identifier_kind(value: str) -> IdentifierKind:
    """
    تشخیص نوع identifier بر اساس شکل ورودی.

    Returns:
        "email" یا "phone"

    Raises:
        ValidationError: اگر ورودی نه شکل ایمیل دارد نه شکل شماره.
    """
    if not isinstance(value, str):
        raise ValidationError("شناسه باید رشته باشد.")

    stripped = value.strip()
    if not stripped:
        raise ValidationError("شناسه نمی‌تواند خالی باشد.")

    # اگر کاراکتر @ دارد، احتمالاً ایمیل است.
    if "@" in stripped:
        return "email"

    # اگر فقط رقم و + دارد، احتمالاً شماره است.
    digits_and_plus = set(stripped) <= set("0123456789+ -()")
    if digits_and_plus:
        return "phone"

    raise ValidationError(
        "نوع شناسه قابل تشخیص نیست. لطفاً ایمیل یا شماره موبایل معتبر وارد کنید.",
    )


# ============================================================
# Phone normalization
# ============================================================


def normalize_phone(value: str) -> str:
    """
    نرمالایز کردن شماره موبایل به فرمت E.164 (مثلاً "+989120000000").

    ورودی‌های پذیرفته‌شده:
    - "09120000000"           → "+989120000000"
    - "9120000000"            → "+989120000000"
    - "989120000000"          → "+989120000000"
    - "+989120000000"         → "+989120000000"
    - "+98 912 000 0000"      → "+989120000000"  (whitespace ها حذف می‌شوند)
    - "+98-912-000-0000"      → "+989120000000"  (- و () حذف می‌شوند)
    - "00989120000000"        → "+989120000000"  (00 جایگزین + برای international)
    - "+1234567890"           → "+1234567890"    (غیر ایرانی هم قبول می‌شود)

    Raises:
        ValidationError: شماره invalid یا attack-suspicious.
    """
    if not isinstance(value, str):
        raise ValidationError("شماره موبایل باید رشته باشد.")

    raw = value.strip()
    if not raw:
        raise ValidationError("شماره موبایل نمی‌تواند خالی باشد.")

    if len(raw) > _PHONE_MAX_RAW_LENGTH:
        raise ValidationError("شماره موبایل بیش از حد طولانی است.")

    # حذف کاراکترهای فرمت‌بندی رایج: فاصله، -، (، )
    cleaned = re.sub(r"[\s\-()]+", "", raw)

    if len(cleaned) < _PHONE_MIN_RAW_LENGTH:
        raise ValidationError("شماره موبایل بسیار کوتاه است.")

    # جایگزینی 00 ابتدای شماره با + (شکل بین‌المللی قدیمی)
    if cleaned.startswith("00"):
        cleaned = "+" + cleaned[2:]

    # حالت 1: شماره‌ی محلی ایران (با 0 شروع، مثلاً 09120000000)
    if cleaned.startswith("0") and not cleaned.startswith("00"):
        local_part = cleaned[1:]
        if _IRAN_LOCAL_PHONE_PATTERN.match(local_part):
            return f"{_IRAN_E164_PREFIX}{local_part}"
        raise ValidationError("شماره موبایل ایرانی نامعتبر است.")

    # حالت 2: شماره‌ی محلی ایران بدون 0 (مثلاً 9120000000)
    if _IRAN_LOCAL_PHONE_PATTERN.match(cleaned):
        return f"{_IRAN_E164_PREFIX}{cleaned}"

    # حالت 3: شماره با country code بدون +
    # (مثلاً 989120000000 → +989120000000)
    if cleaned.isdigit() and len(cleaned) > 10:
        candidate = "+" + cleaned
        if _E164_PATTERN.match(candidate) and len(cleaned) <= _PHONE_MAX_DIGITS:
            return candidate

    # حالت 4: شماره با + (E.164)
    if cleaned.startswith("+") and _E164_PATTERN.match(cleaned):
        return cleaned

    raise ValidationError("فرمت شماره موبایل نامعتبر است.")


# ============================================================
# Email normalization
# ============================================================


def normalize_email(value: str) -> str:
    """
    نرمالایز کردن ایمیل به فرمت canonical:
    - lowercase
    - trimmed
    - validation سبک RFC-compatible

    Raises:
        ValidationError: ایمیل invalid یا attack-suspicious.
    """
    if not isinstance(value, str):
        raise ValidationError("ایمیل باید رشته باشد.")

    raw = value.strip()
    if not raw:
        raise ValidationError("ایمیل نمی‌تواند خالی باشد.")

    if len(raw) > _EMAIL_MAX_LENGTH:
        raise ValidationError("ایمیل بیش از حد طولانی است.")

    lowered = raw.lower()

    # فقط یک @ باید وجود داشته باشد.
    if lowered.count("@") != 1:
        raise ValidationError("فرمت ایمیل نامعتبر است.")

    if not _EMAIL_PATTERN.match(lowered):
        raise ValidationError("فرمت ایمیل نامعتبر است.")

    return lowered


# ============================================================
# Combined helper
# ============================================================


def normalize_identifier(value: str) -> tuple[IdentifierKind, str]:
    """
    تشخیص نوع identifier + نرمالایز کردن همزمان.

    Returns:
        (kind, normalized_value)

    Raises:
        ValidationError: اگر ورودی نه email معتبر است نه phone معتبر.
    """
    kind = detect_identifier_kind(value)
    if kind == "email":
        return "email", normalize_email(value)
    return "phone", normalize_phone(value)

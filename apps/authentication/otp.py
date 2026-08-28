"""
OTP Service Layer — pure business logic for one-time codes.

این ماژول لایه‌ی business مرکزی OTP است:
- generate_and_send_otp(): تولید + hashing + ذخیره + ارسال از طریق Provider Pattern
- verify_otp(): مقایسه‌ی constant-time + attempt tracking + replay protection

اصول طراحی:
- Constant-time comparison با hmac.compare_digest برای جلوگیری از timing attacks
- Secret-keyed hash (با SECRET_KEY) — حتی اگر DB لو رفت، OTPها بدون secret
  قابل reverse engineering نیستند
- Cooldown per (identifier, purpose) — جلوگیری از abuse
- Per-OTP attempt limit — جلوگیری از brute-force
- Replay protection — OTP بعد از verify موفق فوراً invalid می‌شود
- One-active-per-purpose — OTPهای قبلی همان (identifier, purpose) با
  ساخت OTP جدید invalidate می‌شوند

نکته‌ی delivery (Phase F):
- این لایه از `providers.py` استفاده می‌کند تا OTP را بفرستد.
- به لطف transaction.atomic، اگر ارسال (Email/SMS) قطع باشد و خطا بدهد،
  کل ساخت OTP و باطل‌کردن قبلی‌ها Rollback می‌شود (ACID Guarantee).
"""

from __future__ import annotations

import hashlib
import hmac
import logging
import secrets
import time
from dataclasses import dataclass
from datetime import datetime, timedelta

from django.conf import settings
from django.core.cache import cache
from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import F
from django.utils import timezone
from django.utils.crypto import salted_hmac

from .choices import OTPPurpose
from .logging_utils import mask_identifier
from .models import OTPCode, PrimaryIdentifierKind
from .providers import OTPDeliveryProviderError, get_otp_provider

logger = logging.getLogger("apps.authentication")


# ============================================================
# Configuration (with sane defaults)
# ============================================================

# این مقادیر عمداً از طریق تابع خوانده می‌شوند و نه به‌صورت ثابتِ سطح ماژول.
# ثابت سطح ماژول در زمان import مقدار می‌گیرد، یعنی نه با override_settings در
# تست قابل تغییر است و نه با تنظیمات محیطی در production.
_OTP_DEFAULTS = {
    # طول ۶ رقم استاندارد صنعتی است. با ۵ رقم فضای جستجو فقط ۱۰۰٬۰۰۰ حالت
    # است که هم brute-force آنلاین را ارزان‌تر می‌کند و هم در صورت افشای
    # SECRET_KEY، شکستن offline کل جدول را به چند ثانیه کاهش می‌دهد.
    "AUTH_OTP_CODE_LENGTH": 6,
    "AUTH_OTP_TTL_SECONDS": 5 * 60,
    "AUTH_OTP_MAX_ATTEMPTS": 5,
    "AUTH_OTP_COOLDOWN_SECONDS": 60,
}


def _otp_setting(name: str) -> int:
    """Read an OTP tunable from settings at call time, with a safe default."""
    return int(getattr(settings, name, _OTP_DEFAULTS[name]))


# ============================================================
# Exceptions
# ============================================================


class OTPError(Exception):
    """Base exception برای errorهای OTP."""


class OTPCooldownActive(OTPError):
    """در حال cooldown — کاربر باید صبر کند."""

    def __init__(self, seconds_remaining: int) -> None:
        self.seconds_remaining = seconds_remaining
        super().__init__(f"باید {seconds_remaining} ثانیه دیگر صبر کنید.")


class OTPNotFound(OTPError):
    """هیچ OTP فعالی برای این (identifier, purpose) وجود ندارد."""


class OTPExpired(OTPError):
    """OTP منقضی شده است."""


class OTPInvalidCode(OTPError):
    """کد وارد شده اشتباه است."""


class OTPTooManyAttempts(OTPError):
    """تعداد تلاش‌های اشتباه از حد مجاز بیشتر شده — OTP باطل شد."""


class OTPDeliveryError(OTPError):
    """ارسال OTP از طریق Provider با شکست مواجه شد."""


# ============================================================
# Result dataclass
# ============================================================


@dataclass(frozen=True)
class OTPGenerationResult:
    """خروجی تولید OTP."""

    otp: OTPCode
    code_plain: str  # فقط در dev/test برای debug؛ در production هرگز نباید log شود
    expires_in_seconds: int


# ============================================================
# Internal helpers
# ============================================================


def _generate_code() -> str:
    """تولید یک کد عددی تصادفی با طول تنظیم‌شده (پیش‌فرض ۶ رقم)."""
    length = _otp_setting("AUTH_OTP_CODE_LENGTH")
    code_int = secrets.randbelow(10**length)
    return str(code_int).zfill(length)


def _generate_salt() -> str:
    """نمک تصادفی مخصوص یک رکورد OTP (۱۶ بایت → ۳۲ کاراکتر hex)."""
    return secrets.token_hex(16)


def _hash_code(
    code: str,
    *,
    salt: str,
    identifier_kind: str,
    identifier_value: str,
    purpose: str,
) -> str:
    """HMAC-SHA256 روی کد، مقید به نمک اختصاصی رکورد و کانتکست آن.

    پیاده‌سازی قبلی فقط ``HMAC(SECRET_KEY, code)`` بود. دو ضعف داشت:

    1. **بدون نمک اختصاصی.** کد ``12345`` همیشه دقیقاً همان هش را تولید
       می‌کرد. کسی که فقط دسترسی *خواندن* به دیتابیس دارد (بکاپ، replica،
       اپراتور) می‌توانست بدون دانستن SECRET_KEY، تمام رکوردهایی که کد
       یکسان داشتند را به هم مرتبط کند و روی فراوانی‌شان تحلیل آماری
       انجام دهد. حالا هر رکورد نمک ۱۶ بایتی خودش را دارد.
    2. **بدون مقیدسازی به کانتکست.** هش یک OTP از purpose «ورود» با هش
       همان کد برای purpose «تغییر شماره» یکسان بود. حالا کانتکست داخل
       payload می‌آید تا هش هر رکورد فقط در جای خودش معنا داشته باشد.

    جداکنندهٔ ``|`` امن است چون هیچ‌کدام از اجزا نمی‌توانند آن را در خود
    داشته باشند (نمک hex، کد رقمی، purpose و kind از choices ثابت).
    """
    secret = settings.SECRET_KEY.encode("utf-8")
    payload = f"{salt}|{identifier_kind}|{identifier_value}|{purpose}|{code}".encode()
    return hmac.new(secret, payload, hashlib.sha256).hexdigest()


def _hash_code_legacy(code: str) -> str:
    """طرح هش قدیمی — فقط برای تأیید OTPهایی که پیش از این تغییر صادر شده‌اند.

    رکوردهای قدیمی ``code_salt`` خالی دارند. چون TTL هر OTP پنج دقیقه است،
    این مسیر حداکثر برای یک بازهٔ کوتاه پس از deploy فعال می‌ماند و پس از
    آن می‌توان حذفش کرد (به همراه شاخهٔ فراخوانی‌اش در ``verify_otp``).
    """
    return hmac.new(
        settings.SECRET_KEY.encode("utf-8"),
        code.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()


def _expected_hash_for(otp: OTPCode, code: str) -> str:
    """هش مورد انتظار برای یک رکورد، با احترام به طرح هش همان رکورد."""
    if not otp.code_salt:
        return _hash_code_legacy(code)
    return _hash_code(
        code,
        salt=otp.code_salt,
        identifier_kind=otp.identifier_kind,
        identifier_value=otp.identifier_value,
        purpose=otp.purpose,
    )


def _cooldown_key(*, identifier_kind: str, identifier_value: str, purpose: str) -> str:
    """کلید cooldown، با شناسهٔ هش‌شده تا مقدار خام وارد کش نشود."""
    digest = salted_hmac(
        "apps.authentication.otp.cooldown",
        f"{identifier_kind}|{identifier_value}|{purpose}",
    ).hexdigest()
    return f"auth:otp:cooldown:{digest}"


def _reserve_cooldown_slot(
    *,
    identifier_kind: str,
    identifier_value: str,
    purpose: str,
    cooldown_seconds: int,
) -> int | None:
    """Atomically claim the cooldown window; return remaining seconds if taken.

    بررسی cooldown قبلاً فقط با خواندن آخرین OTP از دیتابیس انجام می‌شد و
    بلافاصله بعدش رکورد جدید ساخته می‌شد. این یک الگوی کلاسیک
    read-then-write است: دو درخواست همزمان هر دو «هیچ OTP فعالی نیست» را
    می‌بینند و هر دو کد می‌سازند و می‌فرستند. یعنی cooldown که تنها سد
    مقابل اسپم پیامک (و هزینهٔ مستقیم ریالی) است، دقیقاً زیر همان باری که
    برایش ساخته شده بی‌اثر می‌شود.

    ``cache.add`` روی ردیس اتمیک است (``SET NX``) و همین اتمی بودن، پنجرهٔ
    مسابقه را می‌بندد. بررسی دیتابیس هم سر جایش می‌ماند: کش مرجع نیست، فقط
    سد اول است. اگر کش پاک شود بدترین حالت این است که به رفتار قبلی
    برگردیم، نه اینکه cooldown کاملاً از بین برود.

    Returns:
        ``None`` اگر نوبت گرفته شد؛ در غیر این صورت ثانیه‌های باقی‌مانده.
    """
    key = _cooldown_key(
        identifier_kind=identifier_kind,
        identifier_value=identifier_value,
        purpose=purpose,
    )
    claimed_at = time.time()
    if cache.add(key, claimed_at, timeout=cooldown_seconds):
        return None

    started_at = cache.get(key)
    if started_at is None:
        # درست بین add و get منقضی شد؛ یک تلاش دیگر.
        if cache.add(key, claimed_at, timeout=cooldown_seconds):
            return None
        return cooldown_seconds

    remaining = int(cooldown_seconds - (time.time() - float(started_at)))
    return max(remaining, 1)


def _release_cooldown_slot(*, identifier_kind: str, identifier_value: str, purpose: str) -> None:
    """آزادسازی نوبت cooldown وقتی ساخت/ارسال OTP به نتیجه نرسید.

    بدون این، یک شکست گذرای provider کاربر را یک دورهٔ کامل cooldown
    قفل می‌کرد در حالی که هیچ کدی دریافت نکرده بود.
    """
    cache.delete(
        _cooldown_key(
            identifier_kind=identifier_kind,
            identifier_value=identifier_value,
            purpose=purpose,
        )
    )


def _normalize_identifier_kind(value: str) -> str:
    """اعتبارسنجی identifier_kind."""
    if value not in (PrimaryIdentifierKind.EMAIL, PrimaryIdentifierKind.PHONE):
        raise ValidationError(f"نوع شناسه نامعتبر: {value}")
    return value


def _normalize_purpose(value: str) -> str:
    """اعتبارسنجی purpose."""
    valid_purposes = {choice.value for choice in OTPPurpose}
    if value not in valid_purposes:
        raise ValidationError(f"هدف OTP نامعتبر: {value}")
    return value


def _get_latest_active_otp(
    *,
    identifier_kind: str,
    identifier_value: str,
    purpose: str,
) -> OTPCode | None:
    """
    آخرین OTP فعال (نه used، نه expired) برای این (identifier, purpose).

    "فعال" یعنی: is_used=False و expires_at > now.
    """
    now = timezone.now()
    return (
        OTPCode.objects.filter(
            identifier_kind=identifier_kind,
            identifier_value=identifier_value,
            purpose=purpose,
            is_used=False,
            expires_at__gt=now,
        )
        .order_by("-created_at")
        .first()
    )


def _mark_otp_used(otp: OTPCode) -> bool:
    """
    OTP را با conditional update اتمیک استفاده‌شده کن.

    Returns:
        True اگر همین فراخوانی OTP را invalidate کرد؛ False اگر OTP قبلاً توسط
        request/process دیگری استفاده شده بود. این guard replay همزمان را می‌بندد.
    """
    updated = OTPCode.objects.filter(pk=otp.pk, is_used=False).update(
        is_used=True,
        updated_at=timezone.now(),
    )
    if updated:
        otp.is_used = True
    return bool(updated)


def _increment_otp_attempts(otp: OTPCode) -> int:
    """
    افزایش attempts روی OTP با F-expression و conditional update.

    این تابع race-safe است: increment در دیتابیس انجام می‌شود و فقط اگر OTP هنوز
    active باشد اعمال می‌گردد. اگر OTP همزمان استفاده شده باشد، OTPNotFound
    raise می‌شود تا caller آن را مثل replay/invalidated flow هندل کند.
    """
    with transaction.atomic():
        updated = OTPCode.objects.filter(pk=otp.pk, is_used=False).update(
            attempts=F("attempts") + 1,
            updated_at=timezone.now(),
        )
        if not updated:
            raise OTPNotFound("کدی برای این درخواست یافت نشد. لطفاً درخواست جدید بدهید.")
        otp.refresh_from_db(fields=["attempts", "is_used", "updated_at"])
        return int(otp.attempts or 0)


# ============================================================
# Public API
# ============================================================


@transaction.atomic
def _persist_new_otp(
    *,
    identifier_kind: str,
    identifier_value: str,
    purpose: str,
    code_hash: str,
    code_salt: str,
    expires_at: datetime,
) -> OTPCode:
    """ساخت رکورد OTP جدید در یک transaction کوتاه و بدون I/O خارجی."""
    return OTPCode.objects.create(
        identifier_kind=identifier_kind,
        identifier_value=identifier_value,
        purpose=purpose,
        code_hash=code_hash,
        code_salt=code_salt,
        expires_at=expires_at,
        attempts=0,
        is_used=False,
    )


@transaction.atomic
def _commit_otp_delivery(*, otp: OTPCode) -> None:
    """
    نهایی‌سازی پس از ارسال موفق: باطل کردن OTPهای قبلیِ همان هدف.

    این کار عمداً *بعد* از ارسال انجام می‌شود. اگر قبل از ارسال انجام
    می‌شد و ارسال شکست می‌خورد، کاربر هم کد قبلی‌اش را از دست می‌داد و هم
    کد جدیدی دریافت نمی‌کرد.
    """
    OTPCode.objects.filter(
        identifier_kind=otp.identifier_kind,
        identifier_value=otp.identifier_value,
        purpose=otp.purpose,
        is_used=False,
    ).exclude(pk=otp.pk).update(is_used=True, updated_at=timezone.now())


@transaction.atomic
def _discard_undelivered_otp(*, otp: OTPCode) -> None:
    """
    جبران شکست ارسال: حذف رکورد OTPی که هرگز به دست کاربر نرسید.

    نتیجه‌ی نهایی دقیقاً همان چیزی است که rollback قبلی تولید می‌کرد —
    نه کد جدیدی می‌ماند و نه کد قبلی باطل شده است — ولی این بار بدون
    نگه‌داشتن یک transaction باز در طول تماس شبکه‌ای با provider.
    """
    OTPCode.objects.filter(pk=otp.pk).delete()


def generate_and_send_otp(
    *,
    identifier_kind: str,
    identifier_value: str,
    purpose: str,
) -> OTPGenerationResult:
    """
    تولید یک OTP جدید، ارسال از طریق Provider و باطل کردن کدهای قبلی.

    Args:
        identifier_kind: "email" یا "phone".
        identifier_value: ایمیل نرمالایز شده یا شماره E.164.
        purpose: یکی از OTPPurpose choices.

    Returns:
        OTPGenerationResult با OTP، code plain (فقط dev) و expires_in_seconds.

    Raises:
        ValidationError: اگر identifier_kind یا purpose نامعتبر باشد.
        OTPCooldownActive: اگر هنوز در cooldown باشد.
        OTPDeliveryError: اگر سرویس ارسال قطع باشد.

    معماری transaction:
        این تابع عمداً در سطح بیرونی atomic **نیست**. پیش‌تر بود، و این
        یعنی یک تماس HTTP با پنل پیامک (تا ۱۰ ثانیه timeout) در حالی
        انجام می‌شد که یک transaction باز PostgreSQL نگه داشته شده بود.
        زیر بار، این الگو connectionها را می‌بلعد و به کل سرویس سرایت می‌کند.

        الگوی فعلی:
          فاز ۱ — بررسی cooldown و ساخت رکورد OTP (atomic کوتاه).
          فاز ۲ — ارسال از طریق provider (بدون هیچ transaction بازی).
          فاز ۳ — در موفقیت: باطل کردن کدهای قبلی (atomic کوتاه).
                  در شکست: حذف رکورد ارسال‌نشده (atomic کوتاه).

        وضعیت نهایی دیتابیس در هر دو مسیر با رفتار قبلی یکسان است.
    """
    identifier_kind = _normalize_identifier_kind(identifier_kind)
    purpose = _normalize_purpose(purpose)

    cooldown_seconds = _otp_setting("AUTH_OTP_COOLDOWN_SECONDS")
    ttl_seconds = _otp_setting("AUTH_OTP_TTL_SECONDS")

    # 1) Cooldown — ابتدا رزرو اتمیک، سپس بررسی حالت پایدار دیتابیس.
    remaining = _reserve_cooldown_slot(
        identifier_kind=identifier_kind,
        identifier_value=identifier_value,
        purpose=purpose,
        cooldown_seconds=cooldown_seconds,
    )
    if remaining is not None:
        logger.info(
            "OTP cooldown active (reservation) for identifier=%s purpose=%s remaining=%ds",
            mask_identifier(identifier_value, identifier_kind=identifier_kind),
            purpose,
            remaining,
        )
        raise OTPCooldownActive(seconds_remaining=remaining)

    latest = _get_latest_active_otp(
        identifier_kind=identifier_kind,
        identifier_value=identifier_value,
        purpose=purpose,
    )
    if latest is not None:
        elapsed = (timezone.now() - latest.created_at).total_seconds()
        if elapsed < cooldown_seconds:
            _release_cooldown_slot(
                identifier_kind=identifier_kind,
                identifier_value=identifier_value,
                purpose=purpose,
            )
            remaining = int(cooldown_seconds - elapsed)
            logger.info(
                "OTP cooldown active for identifier=%s purpose=%s remaining=%ds",
                mask_identifier(identifier_value, identifier_kind=identifier_kind),
                purpose,
                remaining,
            )
            raise OTPCooldownActive(seconds_remaining=remaining)

    # 2) Generate new code + per-record salt + hash
    code_plain = _generate_code()
    code_salt = _generate_salt()
    code_hash = _hash_code(
        code_plain,
        salt=code_salt,
        identifier_kind=identifier_kind,
        identifier_value=identifier_value,
        purpose=purpose,
    )
    expires_at = timezone.now() + timedelta(seconds=ttl_seconds)

    # 3) Persist (atomic کوتاه). رکورد جدید بلافاصله جدیدترین OTP فعال
    #    می‌شود، پس درخواست‌های موازی روی همین هدف در cooldown می‌افتند.
    otp = _persist_new_otp(
        identifier_kind=identifier_kind,
        identifier_value=identifier_value,
        purpose=purpose,
        code_hash=code_hash,
        code_salt=code_salt,
        expires_at=expires_at,
    )

    # 4) Delivery via Provider Pattern — خارج از هر transaction
    try:
        provider = get_otp_provider(channel=identifier_kind)
        provider.send(
            recipient=identifier_value,
            code=code_plain,
            purpose=purpose,
        )
    except OTPDeliveryProviderError as exc:
        _discard_undelivered_otp(otp=otp)
        _release_cooldown_slot(
            identifier_kind=identifier_kind,
            identifier_value=identifier_value,
            purpose=purpose,
        )
        logger.error(
            "Provider delivery failed identifier=%s purpose=%s error=%s",
            mask_identifier(identifier_value, identifier_kind=identifier_kind),
            purpose,
            exc,
        )
        raise OTPDeliveryError(
            "متأسفانه در ارسال کد خطایی رخ داد. لطفاً چند دقیقه دیگر تلاش کنید.",
        ) from exc
    except Exception:
        _discard_undelivered_otp(otp=otp)
        _release_cooldown_slot(
            identifier_kind=identifier_kind,
            identifier_value=identifier_value,
            purpose=purpose,
        )
        raise

    # 5) کد رسید → حالا کدهای قبلی همان هدف باطل می‌شوند
    _commit_otp_delivery(otp=otp)

    logger.info(
        "OTP generated and handed to provider identifier=%s purpose=%s expires_at=%s",
        mask_identifier(identifier_value, identifier_kind=identifier_kind),
        purpose,
        expires_at.isoformat(),
    )

    return OTPGenerationResult(
        otp=otp,
        code_plain=code_plain,
        expires_in_seconds=ttl_seconds,
    )


def verify_otp(
    *,
    identifier_kind: str,
    identifier_value: str,
    purpose: str,
    code: str,
) -> OTPCode:
    """
    تأیید کد OTP و invalidate آن.

    Args:
        identifier_kind: "email" یا "phone".
        identifier_value: ایمیل نرمالایز شده یا شماره E.164.
        purpose: یکی از OTPPurpose choices.
        code: کد ورودی از کاربر.

    Returns:
        OTPCode object که verified شد (is_used=True پس از این).

    Raises:
        ValidationError: اگر identifier_kind یا purpose نامعتبر باشد.
        OTPNotFound: اگر OTP فعالی برای این (identifier, purpose) وجود ندارد.
        OTPExpired: اگر OTP منقضی شده.
        OTPInvalidCode: اگر کد اشتباه است (و attempts افزایش یافت).
        OTPTooManyAttempts: اگر از حد مجاز attempt گذشته (OTP باطل شد).

    Note:
        این تابع عمداً در سطح بیرونی atomic نیست. side-effects هر failure
        path (افزایش attempts، invalidate) در atomic block کوتاه خودش
        انجام می‌شود تا با raise exception بعدی rollback نشود. این جلوی
        یک critical bug را می‌گیرد: brute-force bypass via rollback.
    """
    identifier_kind = _normalize_identifier_kind(identifier_kind)
    purpose = _normalize_purpose(purpose)

    if not isinstance(code, str) or not code.strip():
        raise OTPInvalidCode("کد نمی‌تواند خالی باشد.")

    otp = (
        OTPCode.objects.filter(
            identifier_kind=identifier_kind,
            identifier_value=identifier_value,
            purpose=purpose,
            is_used=False,
        )
        .order_by("-created_at")
        .first()
    )

    if otp is None:
        logger.info(
            "OTP verify failed (not found) for identifier=%s purpose=%s",
            mask_identifier(identifier_value, identifier_kind=identifier_kind),
            purpose,
        )
        raise OTPNotFound("کدی برای این درخواست یافت نشد. لطفاً درخواست جدید بدهید.")

    # Check expiry
    if otp.is_expired:
        if not _mark_otp_used(otp):
            raise OTPNotFound("کدی برای این درخواست یافت نشد. لطفاً درخواست جدید بدهید.")
        logger.info(
            "OTP verify failed (expired) for identifier=%s purpose=%s",
            mask_identifier(identifier_value, identifier_kind=identifier_kind),
            purpose,
        )
        raise OTPExpired("کد منقضی شده است. لطفاً درخواست جدید بدهید.")

    # Check attempts before any work
    max_attempts = _otp_setting("AUTH_OTP_MAX_ATTEMPTS")
    if otp.attempts >= max_attempts:
        if not _mark_otp_used(otp):
            raise OTPNotFound("کدی برای این درخواست یافت نشد. لطفاً درخواست جدید بدهید.")
        logger.warning(
            "OTP invalidated due to max attempts for identifier=%s purpose=%s",
            mask_identifier(identifier_value, identifier_kind=identifier_kind),
            purpose,
        )
        raise OTPTooManyAttempts(
            "تعداد تلاش‌های اشتباه از حد مجاز گذشته است. لطفاً درخواست جدید بدهید.",
        )

    # Compare hashes (constant-time)
    expected_hash = _expected_hash_for(otp, code)
    if not hmac.compare_digest(otp.code_hash, expected_hash):
        # افزایش attempts با F-expression انجام می‌شود تا concurrent wrong attempts
        # هم lost-update ایجاد نکنند. اگر این attempt حد نهایی را رد کند، OTP با یک
        # conditional update جدا invalidate می‌شود.
        next_attempt_count = _increment_otp_attempts(otp)

        if next_attempt_count >= max_attempts:
            _mark_otp_used(otp)
            logger.warning(
                "OTP invalidated on attempt %d for identifier=%s purpose=%s",
                next_attempt_count,
                mask_identifier(identifier_value, identifier_kind=identifier_kind),
                purpose,
            )
            raise OTPTooManyAttempts(
                "تعداد تلاش‌های اشتباه از حد مجاز گذشته است. لطفاً درخواست جدید بدهید.",
            )

        logger.info(
            "OTP verify failed (wrong code) attempt=%d for identifier=%s purpose=%s",
            next_attempt_count,
            mask_identifier(identifier_value, identifier_kind=identifier_kind),
            purpose,
        )
        raise OTPInvalidCode("کد وارد شده اشتباه است.")

    # Success: replay protection with conditional update for concurrent double-submit.
    if not _mark_otp_used(otp):
        raise OTPNotFound("کدی برای این درخواست یافت نشد. لطفاً درخواست جدید بدهید.")
    logger.info(
        "OTP verified successfully for identifier=%s purpose=%s",
        mask_identifier(identifier_value, identifier_kind=identifier_kind),
        purpose,
    )
    return otp

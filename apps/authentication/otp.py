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
from dataclasses import dataclass
from datetime import timedelta

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import F
from django.utils import timezone

from .choices import OTPPurpose
from .logging_utils import mask_identifier
from .models import OTPCode, PrimaryIdentifierKind
from .providers import OTPDeliveryProviderError, get_otp_provider

logger = logging.getLogger("apps.authentication")


# ============================================================
# Configuration (with sane defaults)
# ============================================================

_OTP_CODE_LENGTH = 5
_OTP_TTL_SECONDS = 5 * 60  # 5 دقیقه
_OTP_MAX_ATTEMPTS = 5
_OTP_COOLDOWN_SECONDS = 60


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
    """تولید یک کد عددی random با طول _OTP_CODE_LENGTH."""
    max_value = 10**_OTP_CODE_LENGTH
    code_int = secrets.randbelow(max_value)
    return str(code_int).zfill(_OTP_CODE_LENGTH)


def _hash_code(code: str) -> str:
    """
    تولید SHA-256 hash از (SECRET_KEY + code).

    استفاده از SECRET_KEY به‌عنوان salt یعنی حتی اگر DB لو رفت،
    مهاجم نمی‌تواند بدون دسترسی به SECRET_KEY یک code را reverse engineer کند.
    """
    secret = settings.SECRET_KEY.encode("utf-8")
    payload = code.encode("utf-8")
    return hmac.new(secret, payload, hashlib.sha256).hexdigest()


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


def _invalidate_old_otps(
    *,
    identifier_kind: str,
    identifier_value: str,
    purpose: str,
) -> None:
    """تمام OTPهای قبلی همان (identifier, purpose) را invalidate کن."""
    OTPCode.objects.filter(
        identifier_kind=identifier_kind,
        identifier_value=identifier_value,
        purpose=purpose,
        is_used=False,
    ).update(is_used=True, updated_at=timezone.now())


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
def generate_and_send_otp(
    *,
    identifier_kind: str,
    identifier_value: str,
    purpose: str,
) -> OTPGenerationResult:
    """
    تولید یک OTP جدید، invalidate کردن قبلی‌ها، و ارسال از طریق Provider.

    Args:
        identifier_kind: "email" یا "phone".
        identifier_value: ایمیل نرمالایز شده یا شماره E.164.
        purpose: یکی از OTPPurpose choices.

    Returns:
        OTPGenerationResult با OTP، code plain (فقط dev) و expires_in_seconds.

    Raises:
        ValidationError: اگر identifier_kind یا purpose نامعتبر باشد.
        OTPCooldownActive: اگر هنوز در cooldown باشد.
        OTPDeliveryError: اگر سرویس ارسال قطع باشد (باعث Rollback کل تراکنش می‌شود).

    Note:
        atomic در سطح بیرونی است. اگر ارسال fail شود، ساختِ OTP هم در DB
        ذخیره نمی‌شود و سیستم clean می‌ماند.
    """
    identifier_kind = _normalize_identifier_kind(identifier_kind)
    purpose = _normalize_purpose(purpose)

    # 1) Cooldown check
    latest = _get_latest_active_otp(
        identifier_kind=identifier_kind,
        identifier_value=identifier_value,
        purpose=purpose,
    )
    if latest is not None:
        elapsed = (timezone.now() - latest.created_at).total_seconds()
        if elapsed < _OTP_COOLDOWN_SECONDS:
            remaining = int(_OTP_COOLDOWN_SECONDS - elapsed)
            logger.info(
                "OTP cooldown active for identifier=%s purpose=%s remaining=%ds",
                mask_identifier(identifier_value, identifier_kind=identifier_kind),
                purpose,
                remaining,
            )
            raise OTPCooldownActive(seconds_remaining=remaining)

    # 2) Invalidate previous OTPs (one active per purpose policy)
    _invalidate_old_otps(
        identifier_kind=identifier_kind,
        identifier_value=identifier_value,
        purpose=purpose,
    )

    # 3) Generate new code + hash
    code_plain = _generate_code()
    code_hash = _hash_code(code_plain)
    expires_at = timezone.now() + timedelta(seconds=_OTP_TTL_SECONDS)

    # 4) Save to DB
    otp = OTPCode.objects.create(
        identifier_kind=identifier_kind,
        identifier_value=identifier_value,
        purpose=purpose,
        code_hash=code_hash,
        expires_at=expires_at,
        attempts=0,
        is_used=False,
    )

    # 5) Delivery via Provider Pattern
    try:
        provider = get_otp_provider(channel=identifier_kind)
        provider.send(
            recipient=identifier_value,
            code=code_plain,
            purpose=purpose,
        )
    except OTPDeliveryProviderError as exc:
        logger.error(
            "Provider delivery failed identifier=%s purpose=%s error=%s",
            mask_identifier(identifier_value, identifier_kind=identifier_kind),
            purpose,
            exc,
        )
        raise OTPDeliveryError(
            "متأسفانه در ارسال کد خطایی رخ داد. لطفاً چند دقیقه دیگر تلاش کنید.",
        ) from exc

    logger.info(
        "OTP generated and handed to provider identifier=%s purpose=%s expires_at=%s",
        mask_identifier(identifier_value, identifier_kind=identifier_kind),
        purpose,
        expires_at.isoformat(),
    )

    return OTPGenerationResult(
        otp=otp,
        code_plain=code_plain,
        expires_in_seconds=_OTP_TTL_SECONDS,
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
    if otp.attempts >= _OTP_MAX_ATTEMPTS:
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
    expected_hash = _hash_code(code)
    if not hmac.compare_digest(otp.code_hash, expected_hash):
        # افزایش attempts با F-expression انجام می‌شود تا concurrent wrong attempts
        # هم lost-update ایجاد نکنند. اگر این attempt حد نهایی را رد کند، OTP با یک
        # conditional update جدا invalidate می‌شود.
        next_attempt_count = _increment_otp_attempts(otp)

        if next_attempt_count >= _OTP_MAX_ATTEMPTS:
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

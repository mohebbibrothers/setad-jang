"""
Business services for registration, login, OTP, and identifier management.
"""

from __future__ import annotations

import logging
from collections.abc import Mapping
from datetime import timedelta
from typing import Any, Final

from django.contrib.auth import authenticate
from django.core.cache import cache
from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Q
from django.http import HttpRequest
from django.utils import timezone
from rest_framework_simplejwt.exceptions import TokenError
from rest_framework_simplejwt.token_blacklist.models import BlacklistedToken, OutstandingToken
from rest_framework_simplejwt.tokens import RefreshToken

from .choices import AuthRiskSeverity, AuthRiskSignalType, AuthRiskStatus, OTPPurpose, UserRole
from .constants import LAST_SEEN_TOUCH_SECONDS, SESSION_ID_CLAIM
from .logging_utils import mask_identifier
from .models import (
    LEGACY_FINGERPRINT_ALGORITHM,
    AuthRiskSignal,
    AuthSession,
    OTPCode,
    PrimaryIdentifierKind,
    Profile,
    User,
)
from .normalizers import normalize_email, normalize_phone
from .otp import (
    OTPCooldownActive,
    OTPDeliveryError,
    OTPError,
    OTPExpired,
    OTPInvalidCode,
    OTPNotFound,
    OTPTooManyAttempts,
    generate_and_send_otp as generate_identifier_otp,
    verify_otp as verify_identifier_otp,
)

logger = logging.getLogger("apps.authentication")


# مقدار نگهبان برای «این نشست لغو شده». چون لغو نشست در این سامانه برگشت‌ناپذیر
# است (هیچ مسیری is_revoked را دوباره False نمی‌کند)، کش کردن این حالت امن است.
_SESSION_STATE_REVOKED = "revoked"

BASIC_USER_UPDATABLE_FIELDS: Final[frozenset[str]] = frozenset(
    {
        "first_name",
        "last_name",
    }
)
ADMIN_USER_UPDATABLE_FIELDS: Final[frozenset[str]] = frozenset(
    {
        "first_name",
        "last_name",
        "is_active",
        "is_email_verified",
    }
)


# ============================================================
# Custom service-level exceptions
# ============================================================


class AuthServiceError(Exception):
    """Base exception برای service layer احراز هویت."""


class IdentifierAlreadyExists(AuthServiceError):
    """این شناسه قبلاً در سیستم ثبت شده است."""


class IdentifierNotFound(AuthServiceError):
    """کاربری با این شناسه یافت نشد."""


class InvalidCredentials(AuthServiceError):
    """رمز عبور یا شناسه اشتباه است."""


class AccountNotVerified(AuthServiceError):
    """حساب کاربری هنوز تأیید نشده است."""


class AccountInactive(AuthServiceError):
    """حساب کاربری غیرفعال است."""


class OTPServiceError(AuthServiceError):
    """خطا در سرویس OTP — اطلاعات بیشتر در exc chain."""

    def __init__(self, message: str, *, original: Exception | None = None) -> None:
        super().__init__(message)
        self.original = original


class IdentifierAlreadyVerified(AuthServiceError):
    """این شناسه قبلاً برای همین حساب تأیید شده است."""


class IdentifierChannelAlreadyOccupied(AuthServiceError):
    """در این channel قبلاً identifier دیگری روی همین حساب ثبت شده است."""


class IdentifierNotAttached(AuthServiceError):
    """این channel هنوز به حساب متصل نشده است."""


class IdentifierNotVerified(AuthServiceError):
    """این channel به حساب متصل شده ولی هنوز verify نشده است."""


# ============================================================
# Internal helpers
# ============================================================


def _get_client_ip(*, request: HttpRequest) -> str | None:
    """Extract client IP address from request headers."""
    x_forwarded_for = request.META.get("HTTP_X_FORWARDED_FOR")
    if x_forwarded_for:
        return x_forwarded_for.split(",")[0].strip()

    return request.META.get("REMOTE_ADDR")


def _normalize_identifier_by_kind(
    *,
    identifier_kind: str,
    identifier_value: str,
) -> str:
    """
    Defensive normalization based on identifier kind.

    Note:
    - service layer should remain robust even if called outside DRF serializers
    - format validation beyond normalization is intentionally delegated to serializers
    """
    if identifier_kind == PrimaryIdentifierKind.EMAIL:
        return normalize_email(identifier_value)

    if identifier_kind == PrimaryIdentifierKind.PHONE:
        return normalize_phone(identifier_value)

    raise ValueError(f"Unsupported identifier_kind: {identifier_kind}")


def _get_identifier_state_for_user(
    *,
    user: User,
    identifier_kind: str,
) -> tuple[str | None, bool]:
    """
    Return current identifier value and verified state for a given user/channel.
    """
    if identifier_kind == PrimaryIdentifierKind.EMAIL:
        return user.email, user.is_email_verified

    if identifier_kind == PrimaryIdentifierKind.PHONE:
        return user.phone_number, user.is_phone_verified

    raise ValueError(f"Unsupported identifier_kind: {identifier_kind}")


def _identifier_exists_for_other_user(
    *,
    identifier_kind: str,
    identifier_value: str,
    exclude_user_id: int,
) -> bool:
    """
    Check whether an identifier belongs to another user.
    """
    queryset = User.all_objects.exclude(pk=exclude_user_id)

    if identifier_kind == PrimaryIdentifierKind.EMAIL:
        return queryset.filter(email__iexact=identifier_value).exists()

    if identifier_kind == PrimaryIdentifierKind.PHONE:
        return queryset.filter(phone_number=identifier_value).exists()

    raise ValueError(f"Unsupported identifier_kind: {identifier_kind}")


def _ensure_identifier_can_be_added_or_verified(
    *,
    user: User,
    identifier_kind: str,
    identifier_value: str,
) -> str:
    """
    Validate whether a secondary identifier can be attached/re-verified.

    Supported cases:
    - channel missing on user                                 -> allowed
    - exact same identifier already attached but unverified   -> allowed

    Rejected cases:
    - exact same identifier already verified                  -> already verified
    - different identifier already exists in same channel     -> replace not supported
    - identifier belongs to another user                      -> duplicate
    """
    normalized_value = _normalize_identifier_by_kind(
        identifier_kind=identifier_kind,
        identifier_value=identifier_value,
    )

    current_value, current_verified = _get_identifier_state_for_user(
        user=user,
        identifier_kind=identifier_kind,
    )

    if current_value is not None:
        if current_value == normalized_value:
            if current_verified:
                raise IdentifierAlreadyVerified(
                    "این شناسه قبلاً برای حساب شما تأیید شده است.",
                )
            return normalized_value

        if identifier_kind == PrimaryIdentifierKind.EMAIL:
            raise IdentifierChannelAlreadyOccupied(
                "برای این حساب قبلاً یک ایمیل ثبت شده است. جایگزینی ایمیل در این endpoint پشتیبانی نمی‌شود.",
            )

        raise IdentifierChannelAlreadyOccupied(
            "برای این حساب قبلاً یک شماره موبایل ثبت شده است. جایگزینی شماره موبایل در این endpoint پشتیبانی نمی‌شود.",
        )

    if _identifier_exists_for_other_user(
        identifier_kind=identifier_kind,
        identifier_value=normalized_value,
        exclude_user_id=user.pk,
    ):
        raise IdentifierAlreadyExists("این شناسه قبلاً ثبت شده است.")

    return normalized_value


def _resolve_legacy_otp_identifier(*, user: User, purpose: str) -> tuple[str, str]:
    """
    Resolve identifier for legacy auth-v1 flows.
    """
    if purpose in {
        OTPPurpose.EMAIL_VERIFICATION,
        OTPPurpose.PASSWORD_RESET,
    }:
        if user.email:
            return PrimaryIdentifierKind.EMAIL, normalize_email(user.email)

        raise ValueError(
            "Legacy email OTP flow requires a user with a valid email identifier.",
        )

    if user.primary_identifier == PrimaryIdentifierKind.PHONE and user.phone_number:
        return PrimaryIdentifierKind.PHONE, normalize_phone(user.phone_number)

    if user.email:
        return PrimaryIdentifierKind.EMAIL, normalize_email(user.email)

    if user.phone_number:
        return PrimaryIdentifierKind.PHONE, normalize_phone(user.phone_number)

    raise ValueError("User has no resolvable identifier for OTP delivery.")


def _prepare_phone_number_update(*, user: User, phone_number: str | None) -> list[str]:
    """
    Prepare updates related to phone_number on the User model.
    """
    if phone_number is None:
        return []

    if phone_number == "":
        if user.primary_identifier == PrimaryIdentifierKind.PHONE and not user.email:
            raise ValidationError("برای این حساب حذف شماره موبایل مجاز نیست.")

        update_fields: list[str] = []

        if user.phone_number is not None:
            user.phone_number = None
            update_fields.append("phone_number")

        if user.is_phone_verified:
            user.is_phone_verified = False
            update_fields.append("is_phone_verified")

        return update_fields

    normalized_phone = normalize_phone(phone_number)

    if User.all_objects.filter(phone_number=normalized_phone).exclude(pk=user.pk).exists():
        raise ValidationError("این شماره موبایل قبلاً ثبت شده است.")

    update_fields: list[str] = []

    if user.phone_number != normalized_phone:
        user.phone_number = normalized_phone
        update_fields.append("phone_number")

        if user.is_phone_verified:
            user.is_phone_verified = False
            update_fields.append("is_phone_verified")

    return update_fields


def _issue_tokens(*, user: User) -> dict[str, str]:
    """Generate JWT access and refresh tokens for the user."""
    refresh = RefreshToken.for_user(user)
    return {
        "refresh": str(refresh),
        "access": str(refresh.access_token),
    }


def _create_auth_session(*, user: User, refresh_token: str, request: HttpRequest) -> AuthSession:
    """Create tracked auth session for an issued refresh token."""
    refresh = RefreshToken(refresh_token)
    ip = _get_client_ip(request=request)
    user_agent = request.META.get("HTTP_USER_AGENT", "")[:512]
    expires_at = None
    if refresh.get("exp"):
        expires_at = timezone.datetime.fromtimestamp(
            refresh["exp"], tz=timezone.get_current_timezone()
        )
    return AuthSession.objects.create(
        user=user,
        refresh_jti=str(refresh["jti"]),
        device_label=_build_device_label(user_agent=user_agent),
        user_agent=user_agent,
        ip_address=ip,
        request_id=request.headers.get("X-Request-ID", "")[:80],
        expires_at=expires_at,
        fingerprint_hash=AuthSession.build_fingerprint_hash(user_agent=user_agent, ip_address=ip),
    )


def _build_device_label(*, user_agent: str) -> str:
    """Build a concise device label from user agent without external parsing."""
    normalized = user_agent or "Unknown device"
    if "Mobile" in normalized or "Android" in normalized or "iPhone" in normalized:
        return "Mobile browser"
    if "Firefox" in normalized:
        return "Firefox browser"
    if "Chrome" in normalized:
        return "Chrome browser"
    if "Safari" in normalized:
        return "Safari browser"
    return normalized[:80]


def _build_login_result(*, user: User, request: HttpRequest) -> dict[str, Any]:
    """Build standard login result dict including IP tracking and session registry."""
    ip = _get_client_ip(request=request)
    if ip:
        user.last_login_ip = ip
        user.save(update_fields=["last_login_ip"])

    # نشست پیش از امضای توکن ساخته می‌شود تا شناسه‌اش (sid) داخلِ هر دو
    # توکن حک شود. SimpleJWT تمام claimهای غیررزرو را از refresh به access
    # کپی می‌کند و هنگام rotation هم حفظشان می‌کند — پیوندی پایدار که
    # لغوِ فوریِ نشست و «آخرین فعالیتِ واقعی» را ممکن می‌سازد.
    refresh = RefreshToken.for_user(user)
    session = _create_auth_session(user=user, refresh_token=str(refresh), request=request)
    refresh[SESSION_ID_CLAIM] = session.pk
    tokens = {
        "refresh": str(refresh),
        "access": str(refresh.access_token),
    }
    evaluate_auth_session_risk(session=session)
    return {
        "user": user,
        "tokens": tokens,
        "session": session,
    }


def create_auth_risk_signal(
    *,
    signal_type: str,
    severity: str,
    user: User,
    session: AuthSession | None = None,
    ip_address: str | None = None,
    description: str = "",
    metadata: dict[str, Any] | None = None,
) -> AuthRiskSignal:
    """Create auth risk signal unless an equivalent open signal already exists."""
    existing = AuthRiskSignal.objects.filter(
        signal_type=signal_type,
        status=AuthRiskStatus.OPEN,
        user=user,
        session=session,
        ip_address=ip_address,
    ).first()
    if existing is not None:
        return existing
    return AuthRiskSignal.objects.create(
        signal_type=signal_type,
        severity=severity,
        user=user,
        session=session,
        ip_address=ip_address,
        description=description,
        metadata=metadata or {},
    )


def evaluate_auth_session_risk(*, session: AuthSession) -> list[AuthRiskSignal]:
    """Evaluate risk created by a newly issued auth session."""
    signals: list[AuthRiskSignal] = []
    previous_sessions = AuthSession.objects.filter(user=session.user).exclude(pk=session.pk)
    # تطبیق دوگانهٔ اثرانگشت: هش فعلی (sha256) یا هش legacy (sha1).
    # نشست‌هایی که پیش از مهاجرت الگوریتم ساخته شده‌اند با sha1 ذخیره شده‌اند
    # و بدون این شاخه، اولین نشستِ جدیدِ هر کاربر بعد از deploy به‌اشتباه
    # «دستگاه جدید» علامت می‌خورد. بازتولید هش legacy معتبر است چون
    # ورودی‌هایش (user_agent حداکثر ۵۱۲ کاراکتر و ip_address) عیناً در خود
    # record ذخیره شده‌اند. با انقضای طبیعی نشست‌های قدیمی، این شاخه فراموش
    # می‌شود و بعداً می‌توان حذفش کرد.
    fingerprint_legacy_hash = AuthSession.build_fingerprint_hash(
        user_agent=session.user_agent,
        ip_address=session.ip_address,
        algorithm=LEGACY_FINGERPRINT_ALGORITHM,
    )
    if not previous_sessions.filter(
        Q(fingerprint_hash=session.fingerprint_hash) | Q(fingerprint_hash=fingerprint_legacy_hash)
    ).exists():
        signals.append(
            create_auth_risk_signal(
                signal_type=AuthRiskSignalType.NEW_DEVICE,
                severity=AuthRiskSeverity.MEDIUM,
                user=session.user,
                session=session,
                ip_address=session.ip_address,
                description="ورود از دستگاه/اثر انگشت مرورگر جدید شناسایی شد.",
                metadata={"device_label": session.device_label},
            )
        )
    if session.ip_address and not previous_sessions.filter(ip_address=session.ip_address).exists():
        signals.append(
            create_auth_risk_signal(
                signal_type=AuthRiskSignalType.NEW_IP,
                severity=AuthRiskSeverity.LOW,
                user=session.user,
                session=session,
                ip_address=session.ip_address,
                description="ورود از IP جدید شناسایی شد.",
                metadata={"device_label": session.device_label},
            )
        )
    return signals


def record_failed_login_risk(
    *,
    user: User | None,
    ip_address: str | None,
    window_minutes: int = 30,
    threshold: int = 5,
) -> AuthRiskSignal | None:
    """Create failed-login spike risk signal after repeated failures for known users."""
    if user is None:
        return None
    since = timezone.now() - timezone.timedelta(minutes=window_minutes)
    recent_failures = AuthRiskSignal.objects.filter(
        user=user,
        signal_type=AuthRiskSignalType.FAILED_LOGIN_SPIKE,
        created_at__gte=since,
        status=AuthRiskStatus.OPEN,
    ).count()
    # The audit log stores every failure; this signal escalates after repeated view-level calls.
    if recent_failures >= 1:
        return None
    from apps.audit_logs import actions as audit_actions
    from apps.audit_logs.models import AuditLog

    failure_count = AuditLog.objects.filter(
        user=user, action=audit_actions.LOGIN_FAILED, created_at__gte=since
    ).count()
    if failure_count < threshold:
        return None
    return create_auth_risk_signal(
        signal_type=AuthRiskSignalType.FAILED_LOGIN_SPIKE,
        severity=AuthRiskSeverity.HIGH,
        user=user,
        ip_address=ip_address,
        description="تعداد تلاش‌های ورود ناموفق در بازه کوتاه غیرعادی است.",
        metadata={"window_minutes": window_minutes, "failure_count": failure_count},
    )


@transaction.atomic
def review_auth_risk_signal(
    *, signal: AuthRiskSignal, reviewed_by: User, status: str, review_note: str = ""
) -> AuthRiskSignal:
    """Review/dismiss/escalate an authentication risk signal."""
    if status not in {AuthRiskStatus.REVIEWED, AuthRiskStatus.DISMISSED, AuthRiskStatus.ESCALATED}:
        raise AuthServiceError("وضعیت بررسی ریسک نامعتبر است.")
    locked = AuthRiskSignal.objects.select_for_update().get(pk=signal.pk)
    locked.status = status
    locked.reviewed_by = reviewed_by
    locked.reviewed_at = timezone.now()
    locked.review_note = review_note.strip()
    locked.save(update_fields=["status", "reviewed_by", "reviewed_at", "review_note", "updated_at"])
    return locked


def _map_otp_error_to_service_error(exc: Exception) -> OTPServiceError:
    """
    Map lower-level OTP exceptions to user-facing service errors.
    """
    if isinstance(exc, (OTPNotFound, OTPExpired)):
        return OTPServiceError(
            "کد نامعتبر یا منقضی شده است. لطفاً درخواست جدید بدهید.",
            original=exc,
        )

    if isinstance(exc, OTPInvalidCode):
        return OTPServiceError(
            "کد وارد شده اشتباه است.",
            original=exc,
        )

    if isinstance(exc, OTPTooManyAttempts):
        return OTPServiceError(
            "تعداد تلاش‌های اشتباه از حد مجاز گذشته است. لطفاً درخواست جدید بدهید.",
            original=exc,
        )

    if isinstance(exc, OTPCooldownActive):
        return OTPServiceError(
            f"لطفاً {exc.seconds_remaining} ثانیه دیگر تلاش کنید.",
            original=exc,
        )

    if isinstance(exc, OTPDeliveryError):
        return OTPServiceError(
            "در ارسال کد خطایی رخ داد. لطفاً چند دقیقه دیگر تلاش کنید.",
            original=exc,
        )

    return OTPServiceError(
        "در پردازش کد یکبارمصرف خطایی رخ داد.",
        original=exc,
    )


# ============================================================
# OTP Services — legacy-compatible wrappers
# ============================================================


@transaction.atomic
def create_and_send_otp(*, user: User, purpose: str) -> OTPCode:
    """
    Legacy-compatible OTP creation wrapper for auth-v1 views.
    """
    identifier_kind, identifier_value = _resolve_legacy_otp_identifier(
        user=user,
        purpose=purpose,
    )

    result = generate_identifier_otp(
        identifier_kind=identifier_kind,
        identifier_value=identifier_value,
        purpose=purpose,
    )

    logger.info(
        "Legacy OTP created user_id=%s identifier_kind=%s purpose=%s",
        user.pk,
        identifier_kind,
        purpose,
    )

    return result.otp


def verify_otp(*, user: User, code: str, purpose: str) -> bool:
    """
    Legacy-compatible OTP verification wrapper.
    """
    try:
        identifier_kind, identifier_value = _resolve_legacy_otp_identifier(
            user=user,
            purpose=purpose,
        )

        verify_identifier_otp(
            identifier_kind=identifier_kind,
            identifier_value=identifier_value,
            purpose=purpose,
            code=code,
        )
    except (OTPError, ValidationError, ValueError) as exc:
        logger.info(
            "Legacy OTP verification failed user_id=%s purpose=%s error=%s",
            user.pk,
            purpose,
            exc,
        )
        return False

    return True


# ============================================================
# JWT Services
# ============================================================


def generate_tokens_for_user(*, user: User) -> dict[str, str]:
    """Generate JWT access and refresh tokens for the user."""
    return _issue_tokens(user=user)


# ============================================================
# Legacy Auth Services — auth v1 compatibility
# ============================================================


@transaction.atomic
def register_user(
    *,
    email: str,
    password: str,
    first_name: str = "",
    last_name: str = "",
) -> User:
    """
    Register a new user and send legacy email verification OTP.
    """
    normalized_email = normalize_email(email)

    user = User.objects.create_user(
        email=normalized_email,
        password=password,
        first_name=first_name,
        last_name=last_name,
    )

    create_and_send_otp(user=user, purpose=OTPPurpose.EMAIL_VERIFICATION)

    logger.info(
        "User registered user_id=%s email=%s",
        user.pk,
        mask_identifier(user.email, identifier_kind=PrimaryIdentifierKind.EMAIL),
    )

    return user


def login_user(
    *,
    request: HttpRequest,
    email: str,
    password: str,
) -> dict[str, Any] | None:
    """
    Legacy email-based login.
    """
    try:
        normalized_email = normalize_email(email)
    except ValidationError:
        logger.info(
            "Login failed due to invalid email format input=%s",
            mask_identifier(email, identifier_kind=PrimaryIdentifierKind.EMAIL),
        )
        return None

    user = authenticate(
        request=request,
        username=normalized_email,
        password=password,
    )
    if not user:
        logger.info(
            "Login failed for identifier=%s",
            mask_identifier(normalized_email, identifier_kind=PrimaryIdentifierKind.EMAIL),
        )
        return None

    logger.info(
        "User logged in user_id=%s identifier=%s",
        user.pk,
        mask_identifier(normalized_email, identifier_kind=PrimaryIdentifierKind.EMAIL),
    )

    return _build_login_result(user=user, request=request)


@transaction.atomic
def verify_user_email(*, user: User, code: str) -> bool:
    """Verify user email using the new OTP engine through a legacy wrapper."""
    if not verify_otp(
        user=user,
        code=code,
        purpose=OTPPurpose.EMAIL_VERIFICATION,
    ):
        return False

    if not user.is_email_verified:
        user.is_email_verified = True
        user.save(update_fields=["is_email_verified"])

    logger.info(
        "User email verified user_id=%s email=%s",
        user.pk,
        mask_identifier(user.email, identifier_kind=PrimaryIdentifierKind.EMAIL),
    )
    return True


@transaction.atomic
def request_password_reset(*, user: User) -> OTPCode:
    """Create and send password reset OTP for legacy email-based flow."""
    otp = create_and_send_otp(user=user, purpose=OTPPurpose.PASSWORD_RESET)
    logger.info("Password reset OTP requested user_id=%s", user.pk)
    return otp


@transaction.atomic
def reset_password_with_otp(*, user: User, code: str, new_password: str) -> bool:
    """Reset user password if OTP is valid."""
    if not verify_otp(
        user=user,
        code=code,
        purpose=OTPPurpose.PASSWORD_RESET,
    ):
        return False

    user.set_password(new_password)
    user.save(update_fields=["password"])
    logger.info("Password reset completed user_id=%s", user.pk)
    return True


@transaction.atomic
def change_password(*, user: User, old_password: str, new_password: str) -> bool:
    """Change password after validating current password."""
    if not user.check_password(old_password):
        logger.info(
            "Password change failed due to invalid old password user_id=%s",
            user.pk,
        )
        return False

    user.set_password(new_password)
    user.save(update_fields=["password"])
    logger.info("Password changed user_id=%s", user.pk)
    return True


def logout_user(*, refresh_token: str) -> bool:
    """Blacklist the provided refresh token and revoke tracked session if present."""
    try:
        token = RefreshToken(refresh_token)
        token.blacklist()
        revoke_auth_session_by_jti(refresh_jti=str(token["jti"]), revoked_by=None)
        return True
    except TokenError:
        logger.warning("Invalid or blacklisted refresh token received during logout.")
        return False
    except Exception:
        logger.exception("Unexpected error happened during logout.")
        return False


@transaction.atomic
def revoke_auth_session(*, session: AuthSession, revoked_by: User | None = None) -> AuthSession:
    """Revoke tracked auth session and blacklist matching outstanding token when possible."""
    locked = AuthSession.objects.select_for_update().get(pk=session.pk)
    if locked.is_revoked:
        return locked
    locked.is_revoked = True
    locked.revoked_at = timezone.now()
    locked.revoked_by = revoked_by
    locked.save(update_fields=["is_revoked", "revoked_at", "revoked_by", "updated_at"])
    outstanding = OutstandingToken.objects.filter(jti=locked.refresh_jti).first()
    if outstanding is not None:
        BlacklistedToken.objects.get_or_create(token=outstanding)
    # کش را همین‌جا باطل می‌کنیم تا لغو نشست در اولین درخواست بعدی اثر کند
    # و منتظر انقضای TTL نمانیم.
    invalidate_session_validity_cache(sid=locked.pk, user_id=locked.user_id)
    return locked


def session_validity_cache_key(*, sid: Any, user_id: Any) -> str:
    """Cache key for the per-request session validity check."""
    return f"auth:session_state:{user_id}:{sid}"


def invalidate_session_validity_cache(*, sid: Any, user_id: Any) -> None:
    """Drop the cached verdict for one session.

    این تابع همان چیزی است که اجازه می‌دهد بدون از دست دادن «لغو فوری
    نشست»، نتیجهٔ بررسی را کش کنیم: به‌جای اتکا به انقضای TTL، لحظهٔ لغو
    صریحاً کش را باطل می‌کنیم.
    """
    cache.delete(session_validity_cache_key(sid=sid, user_id=user_id))


def validate_and_touch_session(*, user: User, token_claims: Mapping[str, Any]) -> bool:
    """
    Enforce the token↔session binding on an authenticated request.

    قرارداد:
        • توکنِ بدون claimای به نام sid (صادرشده پیش از این فیچر) → عبور
          بدون اعمال نشست (سازگاری با نشست‌های تاریخی).
        • نشستِ پاک‌شده یا لغوشده → False (مصرف‌کننده باید 401 بیندازد).
        • نشستِ سالم → True و last_seen_at با آستانه‌ی LAST_SEEN_TOUCH_SECONDS
          لمس می‌شود.

    چرا اینجا کش اضافه شد:
        این تابع در مسیر احراز هویت **هر درخواست** اجرا می‌شود. نسخهٔ قبلی
        همیشه یک SELECT به AuthSession می‌زد؛ یعنی هر API call احرازشده در
        کل سامانه یک کوئری ثابت هزینه داشت، صرفاً برای اینکه بفهمد نشست
        لغو نشده است.

        نکتهٔ حساس این است که کش کردنِ ساده با TTL، «لغو فوری نشست» را
        خراب می‌کند — و آن دقیقاً همان قابلیتی است که این کلاس برایش
        ساخته شده. پس به‌جای اتکا به TTL، از invalidate-on-write استفاده
        می‌کنیم: مسیرهای لغو نشست کلید کش را همان لحظه پاک می‌کنند، پس
        لغو همچنان در اولین درخواست بعدی اثر می‌گذارد.

        TTL فقط نقش تور ایمنی دارد و برابر همان پنجرهٔ لمس last_seen_at
        است؛ یعنی حتی اگر یک مسیر لغو از قلم بیفتد، حداکثر پس از
        LAST_SEEN_TOUCH_SECONDS ثانیه دوباره از دیتابیس خوانده می‌شود.

        اگر کش در دسترس نباشد، رفتار دقیقاً به حالت قبلی (خواندن از
        دیتابیس) برمی‌گردد — یعنی افت کارایی، نه افت امنیت.
    """
    sid = token_claims.get(SESSION_ID_CLAIM)
    if sid is None:
        return True

    now = timezone.now()
    cache_key = session_validity_cache_key(sid=sid, user_id=user.pk)
    cached = cache.get(cache_key)

    if cached == _SESSION_STATE_REVOKED:
        return False
    if cached is not None and (now.timestamp() - float(cached)) < LAST_SEEN_TOUCH_SECONDS:
        # نشست معتبر است و هنوز در پنجرهٔ لمس هستیم → صفر کوئری.
        return True

    session = (
        AuthSession.objects.only("is_revoked", "last_seen_at")
        .filter(pk=sid, user_id=user.pk)
        .first()
    )
    if session is None or session.is_revoked:
        cache.set(cache_key, _SESSION_STATE_REVOKED, timeout=LAST_SEEN_TOUCH_SECONDS)
        return False

    if now - session.last_seen_at >= timedelta(seconds=LAST_SEEN_TOUCH_SECONDS):
        AuthSession.objects.filter(pk=session.pk, is_revoked=False).update(last_seen_at=now)
        last_seen = now
    else:
        last_seen = session.last_seen_at

    cache.set(cache_key, last_seen.timestamp(), timeout=LAST_SEEN_TOUCH_SECONDS)
    return True


def revoke_auth_session_by_jti(
    *, refresh_jti: str, revoked_by: User | None = None
) -> AuthSession | None:
    """Revoke tracked session by refresh token JTI if it exists."""
    session = AuthSession.objects.filter(refresh_jti=refresh_jti).first()
    if session is None:
        return None
    return revoke_auth_session(session=session, revoked_by=revoked_by)


@transaction.atomic
def revoke_all_user_sessions(*, user: User, revoked_by: User | None = None) -> int:
    """Revoke all active sessions for one user and return affected count."""
    count = 0
    for session in AuthSession.objects.select_for_update().filter(user=user, is_revoked=False):
        revoke_auth_session(session=session, revoked_by=revoked_by)
        count += 1
    return count


# ============================================================
# Multi-Identifier Auth Services — Phase H.1
# ============================================================


def signup_request(
    *,
    identifier_kind: str,
    identifier_value: str,
) -> None:
    """
    Step 1 of identifier-first signup.
    """
    identifier_value = _normalize_identifier_by_kind(
        identifier_kind=identifier_kind,
        identifier_value=identifier_value,
    )

    try:
        generate_identifier_otp(
            identifier_kind=identifier_kind,
            identifier_value=identifier_value,
            purpose=OTPPurpose.SIGNUP,
        )
    except (OTPCooldownActive, OTPDeliveryError) as exc:
        logger.info(
            "Signup OTP failed identifier=%s error=%s",
            mask_identifier(identifier_value, identifier_kind=identifier_kind),
            exc,
        )
        raise _map_otp_error_to_service_error(exc) from exc

    logger.info(
        "Signup OTP sent identifier_kind=%s identifier=%s",
        identifier_kind,
        mask_identifier(identifier_value, identifier_kind=identifier_kind),
    )


@transaction.atomic
def signup_verify(
    *,
    identifier_kind: str,
    identifier_value: str,
    code: str,
    password: str,
    first_name: str = "",
    last_name: str = "",
    request: HttpRequest | None = None,
) -> dict[str, Any]:
    """
    Step 2 of identifier-first signup.
    """
    identifier_value = _normalize_identifier_by_kind(
        identifier_kind=identifier_kind,
        identifier_value=identifier_value,
    )

    try:
        verify_identifier_otp(
            identifier_kind=identifier_kind,
            identifier_value=identifier_value,
            purpose=OTPPurpose.SIGNUP,
            code=code,
        )
    except (OTPNotFound, OTPExpired, OTPInvalidCode, OTPTooManyAttempts) as exc:
        raise _map_otp_error_to_service_error(exc) from exc

    if identifier_kind == PrimaryIdentifierKind.EMAIL:
        if User.all_objects.filter(email__iexact=identifier_value).exists():
            raise IdentifierAlreadyExists("این شناسه قبلاً ثبت شده است.")
        user = User.objects.create_user(
            email=identifier_value,
            password=password,
            first_name=first_name,
            last_name=last_name,
            primary_identifier=PrimaryIdentifierKind.EMAIL,
            is_email_verified=True,
        )
    else:
        if User.all_objects.filter(phone_number=identifier_value).exists():
            raise IdentifierAlreadyExists("این شناسه قبلاً ثبت شده است.")
        user = User.objects.create_user(
            phone_number=identifier_value,
            password=password,
            first_name=first_name,
            last_name=last_name,
            primary_identifier=PrimaryIdentifierKind.PHONE,
            is_phone_verified=True,
        )

    logger.info(
        "User created via identifier signup user_id=%s identifier_kind=%s identifier=%s",
        user.pk,
        identifier_kind,
        mask_identifier(identifier_value, identifier_kind=identifier_kind),
    )

    if request is not None:
        return _build_login_result(user=user, request=request)

    return {
        "user": user,
        "tokens": _issue_tokens(user=user),
    }


def login_with_password(
    *,
    identifier_kind: str,
    identifier_value: str,
    password: str,
    request: HttpRequest,
) -> dict[str, Any]:
    """
    Multi-identifier password login.
    """
    from .selectors import get_user_by_identifier

    identifier_value = _normalize_identifier_by_kind(
        identifier_kind=identifier_kind,
        identifier_value=identifier_value,
    )

    user = get_user_by_identifier(
        identifier_kind=identifier_kind,
        identifier_value=identifier_value,
    )

    if user is None:
        logger.info(
            "Login failed (not found) identifier_kind=%s identifier=%s",
            identifier_kind,
            mask_identifier(identifier_value, identifier_kind=identifier_kind),
        )
        raise IdentifierNotFound("کاربری با این مشخصات یافت نشد.")

    if not user.is_active:
        logger.info(
            "Login failed (inactive) user_id=%s identifier=%s",
            user.pk,
            mask_identifier(identifier_value, identifier_kind=identifier_kind),
        )
        raise AccountInactive("حساب کاربری غیرفعال است.")

    if not user.check_password(password):
        logger.info(
            "Login failed (wrong password) user_id=%s identifier=%s",
            user.pk,
            mask_identifier(identifier_value, identifier_kind=identifier_kind),
        )
        raise InvalidCredentials("رمز عبور اشتباه است.")

    if not user.is_primary_identifier_verified:
        logger.info(
            "Login failed (not verified) user_id=%s identifier=%s",
            user.pk,
            mask_identifier(identifier_value, identifier_kind=identifier_kind),
        )
        raise AccountNotVerified("شناسه اصلی شما هنوز تأیید نشده است.")

    logger.info(
        "User logged in via password user_id=%s identifier_kind=%s",
        user.pk,
        identifier_kind,
    )

    return _build_login_result(user=user, request=request)


def login_otp_request(
    *,
    identifier_kind: str,
    identifier_value: str,
) -> None:
    """
    Request login OTP for an existing active user.
    """
    from .selectors import get_active_user_by_identifier

    identifier_value = _normalize_identifier_by_kind(
        identifier_kind=identifier_kind,
        identifier_value=identifier_value,
    )

    user = get_active_user_by_identifier(
        identifier_kind=identifier_kind,
        identifier_value=identifier_value,
    )

    if user is None:
        logger.info(
            "Login OTP request for non-existent/inactive identifier=%s (silently ignored)",
            mask_identifier(identifier_value, identifier_kind=identifier_kind),
        )
        return

    try:
        generate_identifier_otp(
            identifier_kind=identifier_kind,
            identifier_value=identifier_value,
            purpose=OTPPurpose.LOGIN,
        )
    except (OTPCooldownActive, OTPDeliveryError) as exc:
        raise _map_otp_error_to_service_error(exc) from exc

    logger.info(
        "Login OTP sent user_id=%s identifier_kind=%s",
        user.pk,
        identifier_kind,
    )


def login_otp_verify(
    *,
    identifier_kind: str,
    identifier_value: str,
    code: str,
    request: HttpRequest,
) -> dict[str, Any]:
    """
    Verify login OTP and return user + JWT tokens.
    """
    from .selectors import get_active_user_by_identifier

    identifier_value = _normalize_identifier_by_kind(
        identifier_kind=identifier_kind,
        identifier_value=identifier_value,
    )

    try:
        verify_identifier_otp(
            identifier_kind=identifier_kind,
            identifier_value=identifier_value,
            purpose=OTPPurpose.LOGIN,
            code=code,
        )
    except (OTPNotFound, OTPExpired, OTPInvalidCode, OTPTooManyAttempts) as exc:
        raise _map_otp_error_to_service_error(exc) from exc

    user = get_active_user_by_identifier(
        identifier_kind=identifier_kind,
        identifier_value=identifier_value,
    )

    if user is None:
        raise IdentifierNotFound("کاربری با این مشخصات یافت نشد.")

    logger.info(
        "User logged in via OTP user_id=%s identifier_kind=%s",
        user.pk,
        identifier_kind,
    )

    return _build_login_result(user=user, request=request)


def forgot_password_request(
    *,
    identifier_kind: str,
    identifier_value: str,
) -> None:
    """
    Request password reset OTP by identifier.
    """
    from .selectors import get_active_user_by_identifier

    identifier_value = _normalize_identifier_by_kind(
        identifier_kind=identifier_kind,
        identifier_value=identifier_value,
    )

    user = get_active_user_by_identifier(
        identifier_kind=identifier_kind,
        identifier_value=identifier_value,
    )

    if user is None:
        logger.info(
            "Password reset OTP request for non-existent identifier=%s (silently ignored)",
            mask_identifier(identifier_value, identifier_kind=identifier_kind),
        )
        return

    try:
        generate_identifier_otp(
            identifier_kind=identifier_kind,
            identifier_value=identifier_value,
            purpose=OTPPurpose.PASSWORD_RESET,
        )
    except (OTPCooldownActive, OTPDeliveryError) as exc:
        raise _map_otp_error_to_service_error(exc) from exc

    logger.info(
        "Password reset OTP sent user_id=%s identifier_kind=%s",
        user.pk,
        identifier_kind,
    )


@transaction.atomic
def forgot_password_confirm(
    *,
    identifier_kind: str,
    identifier_value: str,
    code: str,
    new_password: str,
) -> None:
    """
    Confirm password reset with OTP.
    """
    from .selectors import get_active_user_by_identifier

    identifier_value = _normalize_identifier_by_kind(
        identifier_kind=identifier_kind,
        identifier_value=identifier_value,
    )

    try:
        verify_identifier_otp(
            identifier_kind=identifier_kind,
            identifier_value=identifier_value,
            purpose=OTPPurpose.PASSWORD_RESET,
            code=code,
        )
    except (OTPNotFound, OTPExpired, OTPInvalidCode, OTPTooManyAttempts) as exc:
        raise _map_otp_error_to_service_error(exc) from exc

    user = get_active_user_by_identifier(
        identifier_kind=identifier_kind,
        identifier_value=identifier_value,
    )

    if user is None:
        raise IdentifierNotFound("کاربری با این مشخصات یافت نشد.")

    user.set_password(new_password)
    user.save(update_fields=["password"])

    logger.info(
        "Password reset confirmed via OTP user_id=%s identifier_kind=%s",
        user.pk,
        identifier_kind,
    )


# ============================================================
# Phase H.2 — Authenticated Identifier Management Services
# ============================================================


def identifier_add_request(
    *,
    user: User,
    identifier_kind: str,
    identifier_value: str,
) -> None:
    """
    Request OTP for attaching or re-verifying a secondary identifier.
    """
    normalized_value = _ensure_identifier_can_be_added_or_verified(
        user=user,
        identifier_kind=identifier_kind,
        identifier_value=identifier_value,
    )

    try:
        generate_identifier_otp(
            identifier_kind=identifier_kind,
            identifier_value=normalized_value,
            purpose=OTPPurpose.IDENTIFIER_ADD,
        )
    except (OTPCooldownActive, OTPDeliveryError) as exc:
        logger.info(
            "Identifier add OTP failed user_id=%s identifier_kind=%s identifier=%s error=%s",
            user.pk,
            identifier_kind,
            mask_identifier(normalized_value, identifier_kind=identifier_kind),
            exc,
        )
        raise _map_otp_error_to_service_error(exc) from exc

    logger.info(
        "Identifier add OTP sent user_id=%s identifier_kind=%s identifier=%s",
        user.pk,
        identifier_kind,
        mask_identifier(normalized_value, identifier_kind=identifier_kind),
    )


@transaction.atomic
def identifier_add_verify(
    *,
    user: User,
    identifier_kind: str,
    identifier_value: str,
    code: str,
) -> User:
    """
    Verify OTP and attach/verify the secondary identifier on the user.
    """
    normalized_value = _ensure_identifier_can_be_added_or_verified(
        user=user,
        identifier_kind=identifier_kind,
        identifier_value=identifier_value,
    )

    try:
        verify_identifier_otp(
            identifier_kind=identifier_kind,
            identifier_value=normalized_value,
            purpose=OTPPurpose.IDENTIFIER_ADD,
            code=code,
        )
    except (OTPNotFound, OTPExpired, OTPInvalidCode, OTPTooManyAttempts) as exc:
        raise _map_otp_error_to_service_error(exc) from exc

    # Re-check after OTP verify to guard against race conditions.
    normalized_value = _ensure_identifier_can_be_added_or_verified(
        user=user,
        identifier_kind=identifier_kind,
        identifier_value=normalized_value,
    )

    update_fields: list[str] = []

    if identifier_kind == PrimaryIdentifierKind.EMAIL:
        if user.email != normalized_value:
            user.email = normalized_value
            update_fields.append("email")

        if not user.is_email_verified:
            user.is_email_verified = True
            update_fields.append("is_email_verified")

    elif identifier_kind == PrimaryIdentifierKind.PHONE:
        if user.phone_number != normalized_value:
            user.phone_number = normalized_value
            update_fields.append("phone_number")

        if not user.is_phone_verified:
            user.is_phone_verified = True
            update_fields.append("is_phone_verified")

    else:
        raise ValueError(f"Unsupported identifier_kind: {identifier_kind}")

    if update_fields:
        user.save(update_fields=update_fields)

    logger.info(
        "Identifier attached/verified user_id=%s identifier_kind=%s identifier=%s updated_fields=%s",
        user.pk,
        identifier_kind,
        mask_identifier(normalized_value, identifier_kind=identifier_kind),
        update_fields,
    )

    return user


@transaction.atomic
def make_primary_identifier(
    *,
    user: User,
    identifier_kind: str,
) -> User:
    """
    Switch primary identifier to an attached + verified channel.
    """
    current_value, current_verified = _get_identifier_state_for_user(
        user=user,
        identifier_kind=identifier_kind,
    )

    if current_value is None:
        raise IdentifierNotAttached("این شناسه هنوز به حساب شما متصل نشده است.")

    if not current_verified:
        raise IdentifierNotVerified("این شناسه هنوز تأیید نشده است.")

    if user.primary_identifier == identifier_kind:
        logger.info(
            "Primary identifier already set user_id=%s identifier_kind=%s",
            user.pk,
            identifier_kind,
        )
        return user

    user.primary_identifier = identifier_kind
    user.save(update_fields=["primary_identifier"])

    logger.info(
        "Primary identifier changed user_id=%s identifier_kind=%s",
        user.pk,
        identifier_kind,
    )

    return user


# ============================================================
# Profile Services
# ============================================================


@transaction.atomic
def update_profile(*, profile: Profile, **fields: Any) -> Profile:
    """
    Update editable profile fields.

    Note: phone_number belongs to User, not Profile.
    """
    user = profile.user
    phone_number = fields.pop("phone_number", None)

    user_update_fields = _prepare_phone_number_update(
        user=user,
        phone_number=phone_number,
    )
    if user_update_fields:
        user.save(update_fields=user_update_fields)

    profile_update_fields = ["updated_at"]

    for key, value in fields.items():
        if value is not None and hasattr(profile, key):
            setattr(profile, key, value)
            profile_update_fields.append(key)

    profile.save(update_fields=profile_update_fields)

    logger.info(
        "Profile updated user_id=%s profile_id=%s",
        user.pk,
        profile.pk,
    )

    return profile


@transaction.atomic
def update_user_basic_info(*, user: User, **fields: Any) -> User:
    """Update basic editable fields of the current authenticated user."""
    update_fields: list[str] = []

    for key, value in fields.items():
        if key in BASIC_USER_UPDATABLE_FIELDS and value is not None:
            setattr(user, key, value)
            update_fields.append(key)

    if update_fields:
        user.save(update_fields=update_fields)
        logger.info(
            "User basic info updated user_id=%s fields=%s",
            user.pk,
            update_fields,
        )

    return user


# ============================================================
# Admin Services
# ============================================================


@transaction.atomic
def admin_update_user(*, user: User, **fields: Any) -> User:
    """Update editable user fields from admin panel."""
    update_fields: list[str] = []

    for key, value in fields.items():
        if key in ADMIN_USER_UPDATABLE_FIELDS and value is not None:
            setattr(user, key, value)
            update_fields.append(key)

    if update_fields:
        user.save(update_fields=update_fields)
        logger.info(
            "Admin updated user user_id=%s fields=%s",
            user.pk,
            update_fields,
        )

    return user


@transaction.atomic
def admin_change_user_role(*, user: User, role: str) -> User:
    """Change user role and sync staff flag accordingly."""
    user.role = role
    user.is_staff = role == UserRole.ADMIN
    user.save(update_fields=["role", "is_staff"])

    logger.info(
        "Admin changed user role user_id=%s role=%s is_staff=%s",
        user.pk,
        user.role,
        user.is_staff,
    )

    return user

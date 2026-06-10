"""
Business services for registration, login, OTP, and identifier management.
"""

from __future__ import annotations

import logging
from typing import Any, Final

from django.contrib.auth import authenticate
from django.core.exceptions import ValidationError
from django.db import transaction
from django.http import HttpRequest
from rest_framework_simplejwt.exceptions import TokenError
from rest_framework_simplejwt.tokens import RefreshToken

from .choices import OTPPurpose, UserRole
from .models import OTPCode, PrimaryIdentifierKind, Profile, User
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

    if (
        user.primary_identifier == PrimaryIdentifierKind.PHONE
        and user.phone_number
    ):
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
        if (
            user.primary_identifier == PrimaryIdentifierKind.PHONE
            and not user.email
        ):
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

    if (
        User.all_objects.filter(phone_number=normalized_phone)
        .exclude(pk=user.pk)
        .exists()
    ):
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


def _build_login_result(*, user: User, request: HttpRequest) -> dict[str, Any]:
    """Build standard login result dict including IP tracking."""
    ip = _get_client_ip(request=request)
    if ip:
        user.last_login_ip = ip
        user.save(update_fields=["last_login_ip"])

    return {
        "user": user,
        "tokens": _issue_tokens(user=user),
    }


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
        user.email,
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
        logger.info("Login failed due to invalid email format input=%s", email)
        return None

    user = authenticate(
        request=request,
        username=normalized_email,
        password=password,
    )
    if not user:
        logger.info("Login failed for identifier=%s", normalized_email)
        return None

    logger.info(
        "User logged in user_id=%s identifier=%s",
        user.pk,
        normalized_email,
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

    logger.info("User email verified user_id=%s email=%s", user.pk, user.email)
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
    """Blacklist the provided refresh token."""
    try:
        token = RefreshToken(refresh_token)
        token.blacklist()
        return True
    except TokenError:
        logger.warning("Invalid or blacklisted refresh token received during logout.")
        return False
    except Exception:
        logger.exception("Unexpected error happened during logout.")
        return False


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
    try:
        generate_identifier_otp(
            identifier_kind=identifier_kind,
            identifier_value=identifier_value,
            purpose=OTPPurpose.SIGNUP,
        )
    except (OTPCooldownActive, OTPDeliveryError) as exc:
        logger.info(
            "Signup OTP failed identifier=%s error=%s",
            identifier_value,
            exc,
        )
        raise _map_otp_error_to_service_error(exc) from exc

    logger.info(
        "Signup OTP sent identifier_kind=%s identifier=%s",
        identifier_kind,
        identifier_value,
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
        identifier_value,
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

    user = get_user_by_identifier(
        identifier_kind=identifier_kind,
        identifier_value=identifier_value,
    )

    if user is None:
        logger.info(
            "Login failed (not found) identifier_kind=%s identifier=%s",
            identifier_kind,
            identifier_value,
        )
        raise IdentifierNotFound("کاربری با این مشخصات یافت نشد.")

    if not user.is_active:
        logger.info(
            "Login failed (inactive) user_id=%s identifier=%s",
            user.pk,
            identifier_value,
        )
        raise AccountInactive("حساب کاربری غیرفعال است.")

    if not user.check_password(password):
        logger.info(
            "Login failed (wrong password) user_id=%s identifier=%s",
            user.pk,
            identifier_value,
        )
        raise InvalidCredentials("رمز عبور اشتباه است.")

    if not user.is_primary_identifier_verified:
        logger.info(
            "Login failed (not verified) user_id=%s identifier=%s",
            user.pk,
            identifier_value,
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

    user = get_active_user_by_identifier(
        identifier_kind=identifier_kind,
        identifier_value=identifier_value,
    )

    if user is None:
        logger.info(
            "Login OTP request for non-existent/inactive identifier=%s (silently ignored)",
            identifier_value,
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

    user = get_active_user_by_identifier(
        identifier_kind=identifier_kind,
        identifier_value=identifier_value,
    )

    if user is None:
        logger.info(
            "Password reset OTP request for non-existent identifier=%s (silently ignored)",
            identifier_value,
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
            normalized_value,
            exc,
        )
        raise _map_otp_error_to_service_error(exc) from exc

    logger.info(
        "Identifier add OTP sent user_id=%s identifier_kind=%s identifier=%s",
        user.pk,
        identifier_kind,
        normalized_value,
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
        normalized_value,
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

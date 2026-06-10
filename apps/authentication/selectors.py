from __future__ import annotations

from django.db.models import QuerySet
from django.utils import timezone

from .models import OTPCode, PrimaryIdentifierKind, Profile, User

# ============================================================
# Internal helpers
# ============================================================


def _get_user_queryset(*, include_inactive: bool) -> QuerySet[User]:
    """
    Base queryset برای lookup کاربر.

    - include_inactive=True  -> all_objects
    - include_inactive=False -> objects (فقط active)
    """
    manager = User.all_objects if include_inactive else User.objects
    return manager.select_related("profile")


def _filter_users_by_identifier(
    *,
    identifier_kind: str,
    identifier_value: str,
    include_inactive: bool,
) -> QuerySet[User]:
    """
    فیلتر کاربران بر اساس نوع شناسه.

    Notes:
    - email با iexact جستجو می‌شود
    - phone_number به‌صورت exact فرض می‌شود چون باید قبلاً normalize شده باشد
    """
    queryset = _get_user_queryset(include_inactive=include_inactive)

    if identifier_kind == PrimaryIdentifierKind.EMAIL:
        return queryset.filter(email__iexact=identifier_value)

    if identifier_kind == PrimaryIdentifierKind.PHONE:
        return queryset.filter(phone_number=identifier_value)

    raise ValueError(f"Unsupported identifier_kind: {identifier_kind}")


# ============================================================
# User Selectors
# ============================================================


def get_user_by_identifier(
    *,
    identifier_kind: str,
    identifier_value: str,
) -> User | None:
    """
    دریافت کاربر با هر شناسه (شامل inactive users).
    """
    return _filter_users_by_identifier(
        identifier_kind=identifier_kind,
        identifier_value=identifier_value,
        include_inactive=True,
    ).first()


def get_active_user_by_identifier(
    *,
    identifier_kind: str,
    identifier_value: str,
) -> User | None:
    """
    دریافت کاربر active با هر شناسه.
    """
    return _filter_users_by_identifier(
        identifier_kind=identifier_kind,
        identifier_value=identifier_value,
        include_inactive=False,
    ).first()


def get_user_by_email(email: str) -> User | None:
    """
    Legacy-compatible wrapper برای lookup کاربر با ایمیل
    (شامل inactive users).
    """
    return get_user_by_identifier(
        identifier_kind=PrimaryIdentifierKind.EMAIL,
        identifier_value=email,
    )


def get_active_user_by_email(email: str) -> User | None:
    """
    Legacy-compatible wrapper برای lookup کاربر active با ایمیل.
    """
    return get_active_user_by_identifier(
        identifier_kind=PrimaryIdentifierKind.EMAIL,
        identifier_value=email,
    )


def get_user_by_phone_number(phone_number: str) -> User | None:
    """
    دریافت کاربر با شماره موبایل نرمالایز شده (شامل inactive users).
    """
    return get_user_by_identifier(
        identifier_kind=PrimaryIdentifierKind.PHONE,
        identifier_value=phone_number,
    )


def get_active_user_by_phone_number(phone_number: str) -> User | None:
    """
    دریافت کاربر active با شماره موبایل نرمالایز شده.
    """
    return get_active_user_by_identifier(
        identifier_kind=PrimaryIdentifierKind.PHONE,
        identifier_value=phone_number,
    )


def get_user_by_id(user_id: int) -> User | None:
    return _get_user_queryset(include_inactive=True).filter(pk=user_id).first()


def get_all_users_for_admin() -> QuerySet[User]:
    return User.all_objects.select_related("profile").order_by("-date_joined", "-id")


# ============================================================
# OTP Selectors
# ============================================================


def get_latest_active_otp_by_identifier(
    *,
    identifier_kind: str,
    identifier_value: str,
    purpose: str,
) -> OTPCode | None:
    """
    آخرین OTP فعال برای یک identifier و purpose مشخص.

    "فعال" یعنی:
    - is_used=False
    - expires_at > now
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


def get_latest_valid_otp(user: User, purpose: str) -> OTPCode | None:
    """
    Legacy-compatible wrapper برای auth v1.

    تصمیم طراحی:
    - چون flowهای legacy فعلی email-centric هستند، اگر user.email وجود داشته باشد
      lookup روی email انجام می‌شود.
    - در غیر این صورت fallback روی phone_number انجام می‌شود.

    این تابع فقط برای حفظ سازگاری موقت auth v1 نگه داشته شده و
    flowهای جدید باید مستقیماً با identifier کار کنند.
    """
    if user.email:
        return get_latest_active_otp_by_identifier(
            identifier_kind=PrimaryIdentifierKind.EMAIL,
            identifier_value=user.email,
            purpose=purpose,
        )

    if user.phone_number:
        return get_latest_active_otp_by_identifier(
            identifier_kind=PrimaryIdentifierKind.PHONE,
            identifier_value=user.phone_number,
            purpose=purpose,
        )

    return None


# ============================================================
# Profile Selectors
# ============================================================


def get_profile_by_user(user: User) -> Profile | None:
    return Profile.objects.select_related("user").filter(user=user).first()

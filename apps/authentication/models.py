"""
Custom user, profile, and OTP models for multi-identifier authentication.
"""

from __future__ import annotations

from django.contrib.auth.models import AbstractBaseUser, PermissionsMixin
from django.db import models
from django.db.models import Q
from django.utils import timezone
from django.utils.crypto import salted_hmac

from apps.core.models import BaseModel

from .choices import (
    AuthRiskSeverity,
    AuthRiskSignalType,
    AuthRiskStatus,
    Gender,
    OTPPurpose,
    UserRole,
)
from .managers import UserAllManager, UserManager

# ============================================================
# Identifier kinds
# ============================================================


class PrimaryIdentifierKind(models.TextChoices):
    """نوع شناسه‌ی اصلی کاربر — آن چیزی که در ابتدا با آن signup کرده است."""

    EMAIL = "email", "ایمیل"
    PHONE = "phone", "شماره موبایل"


# ============================================================
# Utilities
# ============================================================


def avatar_upload_path(instance: Profile, filename: str) -> str:
    """avatar_upload_path helper for the authentication application."""
    return f"avatars/{instance.user_id}/{filename}"


# ============================================================
# User
# ============================================================


class User(AbstractBaseUser, PermissionsMixin):
    """
    کاربر سیستم — multi-identifier (email یا phone).
    """

    email = models.EmailField(
        unique=True,
        null=True,
        blank=True,
        verbose_name="ایمیل",
    )
    phone_number = models.CharField(
        max_length=20,
        unique=True,
        null=True,
        blank=True,
        verbose_name="شماره موبایل",
        help_text="در فرمت E.164 ذخیره می‌شود (مثلاً +989120000000).",
    )

    primary_identifier = models.CharField(
        max_length=10,
        choices=PrimaryIdentifierKind.choices,
        default=PrimaryIdentifierKind.EMAIL,
        verbose_name="شناسه اصلی",
        help_text="نوع شناسه‌ای که کاربر در ابتدا با آن ثبت‌نام کرده است.",
    )

    is_email_verified = models.BooleanField(default=False, verbose_name="ایمیل تأیید شده")
    is_phone_verified = models.BooleanField(default=False, verbose_name="شماره موبایل تأیید شده")

    first_name = models.CharField(max_length=100, blank=True, verbose_name="نام")
    last_name = models.CharField(max_length=100, blank=True, verbose_name="نام خانوادگی")

    role = models.CharField(
        max_length=20,
        choices=UserRole.choices,
        default=UserRole.USER,
        verbose_name="نقش",
    )
    is_active = models.BooleanField(default=True, verbose_name="فعال")
    is_staff = models.BooleanField(default=False, verbose_name="عضو ستاد")

    date_joined = models.DateTimeField(default=timezone.now, verbose_name="تاریخ عضویت")
    last_login_ip = models.GenericIPAddressField(
        blank=True, null=True, verbose_name="آخرین IP ورود"
    )

    objects = UserManager()
    all_objects = UserAllManager()

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = []

    class Meta:
        verbose_name = "کاربر"
        verbose_name_plural = "کاربران"
        ordering = ["-date_joined"]
        constraints = [
            models.CheckConstraint(
                name="user_must_have_email_or_phone",
                condition=(Q(email__isnull=False) | Q(phone_number__isnull=False)),
            ),
        ]

    def __str__(self) -> str:
        return self.primary_identifier_value or f"user#{self.pk}"

    @property
    def full_name(self) -> str:
        return f"{self.first_name} {self.last_name}".strip()

    @property
    def is_admin(self) -> bool:
        return self.role == UserRole.ADMIN

    @property
    def primary_identifier_value(self) -> str | None:
        if self.primary_identifier == PrimaryIdentifierKind.PHONE:
            return self.phone_number
        return self.email

    @property
    def is_primary_identifier_verified(self) -> bool:
        if self.primary_identifier == PrimaryIdentifierKind.PHONE:
            return self.is_phone_verified
        return self.is_email_verified

    @property
    def is_fully_verified(self) -> bool:
        """هم ایمیل تأیید شده، هم شماره موبایل."""
        return self.is_email_verified and self.is_phone_verified

    def soft_delete(self) -> None:
        self.is_active = False
        self.save(update_fields=["is_active"])

    def restore(self) -> None:
        self.is_active = True
        self.save(update_fields=["is_active"])


# ============================================================
# Profile
# ============================================================

#: فیلدهایی که برای «پروفایل کامل» الزامی هستند — مرجع رسمی برای
#: permissionهای high-trust مثل R4J bounty.
PROFILE_R4J_REQUIRED_FIELDS: tuple[str, ...] = (
    "national_code",
    "birth_date",
    "gender",
    "province",
    "city",
    "address",
)


class AuthSession(BaseModel):
    """Tracked user session/device entry for JWT refresh-token families."""

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="auth_sessions")
    refresh_jti = models.CharField(max_length=120, unique=True, db_index=True)
    device_label = models.CharField(max_length=160, blank=True)
    user_agent = models.CharField(max_length=512, blank=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    request_id = models.CharField(max_length=80, blank=True)
    is_revoked = models.BooleanField(default=False, db_index=True)
    revoked_at = models.DateTimeField(null=True, blank=True)
    revoked_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True, related_name="revoked_auth_sessions"
    )
    last_seen_at = models.DateTimeField(default=timezone.now, db_index=True)
    expires_at = models.DateTimeField(null=True, blank=True, db_index=True)
    fingerprint_hash = models.CharField(max_length=64, db_index=True, blank=True)

    class Meta:
        verbose_name = "نشست احراز هویت"
        verbose_name_plural = "نشست‌های احراز هویت"
        ordering = ["-last_seen_at", "-created_at"]
        indexes = [
            models.Index(fields=["user", "is_revoked", "-last_seen_at"]),
            models.Index(fields=["fingerprint_hash", "is_revoked"]),
        ]

    def __str__(self) -> str:
        return f"AuthSession user={self.user_id} revoked={self.is_revoked}"

    @staticmethod
    def build_fingerprint_hash(*, user_agent: str = "", ip_address: str | None = None) -> str:
        """Build a stable non-PII fingerprint hash from request metadata."""
        payload = f"{user_agent[:512]}|{ip_address or ''}"
        return salted_hmac("auth-session-fingerprint", payload).hexdigest()


class AuthRiskSignal(BaseModel):
    """Authentication/session risk signal for admin security review."""

    signal_type = models.CharField(max_length=40, choices=AuthRiskSignalType.choices, db_index=True)
    severity = models.CharField(
        max_length=20,
        choices=AuthRiskSeverity.choices,
        default=AuthRiskSeverity.MEDIUM,
        db_index=True,
    )
    status = models.CharField(
        max_length=20, choices=AuthRiskStatus.choices, default=AuthRiskStatus.OPEN, db_index=True
    )
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="auth_risk_signals")
    session = models.ForeignKey(
        AuthSession, on_delete=models.SET_NULL, null=True, blank=True, related_name="risk_signals"
    )
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    description = models.TextField(blank=True)
    metadata = models.JSONField(default=dict, blank=True)
    reviewed_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="reviewed_auth_risk_signals",
    )
    reviewed_at = models.DateTimeField(null=True, blank=True)
    review_note = models.TextField(blank=True)

    class Meta:
        verbose_name = "سیگنال ریسک احراز هویت"
        verbose_name_plural = "سیگنال‌های ریسک احراز هویت"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["signal_type", "status", "-created_at"]),
            models.Index(fields=["user", "status", "-created_at"]),
            models.Index(fields=["severity", "status", "-created_at"]),
        ]

    def __str__(self) -> str:
        return f"{self.signal_type}:{self.severity}:{self.status}"


class Profile(BaseModel):
    """
    پروفایل تکمیلی کاربر.
    """

    user = models.OneToOneField(
        User,
        on_delete=models.CASCADE,
        related_name="profile",
        verbose_name="کاربر",
    )
    national_code = models.CharField(max_length=10, blank=True, verbose_name="کد ملی")
    birth_date = models.DateField(blank=True, null=True, verbose_name="تاریخ تولد")
    gender = models.CharField(
        max_length=10,
        choices=Gender.choices,
        blank=True,
        verbose_name="جنسیت",
    )
    avatar = models.ImageField(
        upload_to=avatar_upload_path,
        blank=True,
        null=True,
        verbose_name="عکس پروفایل",
    )
    bio = models.TextField(blank=True, verbose_name="درباره من")
    province = models.CharField(max_length=100, blank=True, verbose_name="استان")
    city = models.CharField(max_length=100, blank=True, verbose_name="شهر")
    address = models.TextField(blank=True, verbose_name="آدرس")

    class Meta:
        verbose_name = "پروفایل"
        verbose_name_plural = "پروفایل‌ها"

    def __str__(self) -> str:
        return f"Profile of {self.user!s}"

    # ---- High-trust completeness checks ----

    @property
    def is_complete_for_r4j(self) -> bool:
        """
        بررسی اینکه آیا پروفایل برای عملیات high-trust مثل
        R4J bounty کامل است یا نه.
        """
        return not self.get_missing_r4j_fields()

    def get_missing_r4j_fields(self) -> list[str]:
        """
        لیست فیلدهای الزامی که هنوز پر نشده‌اند.

        مقدار خالی، None، یا blank همگی به‌عنوان «پر نشده» تلقی می‌شوند.
        """
        missing: list[str] = []
        for field in PROFILE_R4J_REQUIRED_FIELDS:
            value = getattr(self, field, None)
            if value is None or value == "":
                missing.append(field)
        return missing


# ============================================================
# OTP — Refactored (Phase D)
# ============================================================


class OTPCode(BaseModel):
    """
    کد یکبارمصرف — Phase D refactor.

    اصول طراحی:
    - OTP plain هرگز در DB ذخیره نمی‌شود (فقط hash).
    - یک identifier نمی‌تواند برای یک purpose خاص بیش از یک OTP فعال داشته باشد
      (در service layer قبلی‌ها invalidate می‌شوند).
    - بعد از 5 attempt اشتباه، OTP خودکار `is_used=True` می‌شود.
    - replay protection: بعد از موفقیت verify، فوراً `is_used=True` می‌شود.

    نکته در مورد defaults:
    - فیلدهای جدید با default خالی تعریف می‌شوند تا migration بتواند بدون
      prompt اجرا شود (داده‌های قدیمی OTP در migration RunPython پاک می‌شوند).
    """

    identifier_kind = models.CharField(
        max_length=10,
        choices=PrimaryIdentifierKind.choices,
        default=PrimaryIdentifierKind.EMAIL,
        verbose_name="نوع شناسه",
    )
    identifier_value = models.CharField(
        max_length=254,
        default="",
        verbose_name="مقدار شناسه",
        help_text="ایمیل نرمالایز شده یا شماره در فرمت E.164.",
    )
    purpose = models.CharField(
        max_length=30,
        choices=OTPPurpose.choices,
        verbose_name="هدف",
    )
    code_hash = models.CharField(
        max_length=64,
        default="",
        verbose_name="هش کد",
        help_text="HMAC-SHA256 روی (SECRET_KEY, salt|context|code) — کد plain هرگز ذخیره نمی‌شود.",
    )
    code_salt = models.CharField(
        max_length=32,
        default="",
        blank=True,
        verbose_name="نمک هش",
        help_text=(
            "نمک تصادفی مخصوص همین رکورد. بدون آن، کد یکسان همیشه هش یکسان "
            "تولید می‌کند و کسی که دسترسی خواندن به دیتابیس دارد می‌تواند "
            "OTPهای هم‌مقدار را در کل جدول به هم مرتبط کند."
        ),
    )
    expires_at = models.DateTimeField(verbose_name="زمان انقضا")
    attempts = models.PositiveSmallIntegerField(
        default=0,
        verbose_name="تعداد تلاش",
    )
    is_used = models.BooleanField(default=False, verbose_name="استفاده شده")

    class Meta:
        verbose_name = "کد یکبارمصرف"
        verbose_name_plural = "کدهای یکبارمصرف"
        ordering = ["-created_at"]
        indexes = [
            models.Index(
                fields=["identifier_kind", "identifier_value", "purpose", "is_used"],
                name="idx_otp_lookup_active",
            ),
            models.Index(
                fields=["expires_at"],
                name="idx_otp_expires_at",
            ),
        ]

    def __str__(self) -> str:
        return f"OTP for {self.identifier_value} ({self.purpose})"

    @property
    def is_expired(self) -> bool:
        return timezone.now() > self.expires_at

    @property
    def is_valid(self) -> bool:
        return not self.is_used and not self.is_expired

    def mark_as_used(self) -> None:
        self.is_used = True
        self.save(update_fields=["is_used", "updated_at"])

    def increment_attempts(self) -> None:
        self.attempts = (self.attempts or 0) + 1
        self.save(update_fields=["attempts", "updated_at"])

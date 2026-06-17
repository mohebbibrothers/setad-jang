"""
Enumeration choices used by the authentication domain.
"""

from django.db import models


class UserRole(models.TextChoices):
    """نقش کاربر در سیستم."""

    USER = "user", "کاربر عادی"
    ADMIN = "admin", "مدیر سیستم"


class OTPPurpose(models.TextChoices):
    """
    هدف استفاده از یک کد OTP.

    اصول:
    - هر purpose مستقل rate-limit و cooldown خودش را دارد.
    - یک identifier نمی‌تواند برای یک purpose خاص بیش از یک OTP فعال داشته باشد
      (در service layer، OTPهای قبلی همان purpose invalidate می‌شوند).
    - این enum با backward-compat نوشته شده: مقادیر قدیمی نگه‌داشته شده‌اند
      تا flowهای legacy نشکنند.
    """

    # ── Auth flows جدید (Phase D و بعدتر) ──────────────────
    SIGNUP = "signup", "ثبت‌نام"
    LOGIN = "login", "ورود"
    IDENTIFIER_ADD = "identifier_add", "افزودن شناسه جدید"

    # ── flowهای قدیمی (backward-compat) ────────────────────
    EMAIL_VERIFICATION = "email_verification", "تأیید ایمیل"
    PASSWORD_RESET = "password_reset", "بازیابی رمز عبور"


class AuthRiskSignalType(models.TextChoices):
    """Risk signals detected from authentication/session behavior."""

    NEW_DEVICE = "new_device", "دستگاه جدید"
    NEW_IP = "new_ip", "IP جدید"
    FAILED_LOGIN_SPIKE = "failed_login_spike", "افزایش تلاش ورود ناموفق"
    SESSION_REVOKE_SPIKE = "session_revoke_spike", "افزایش لغو نشست"


class AuthRiskSeverity(models.TextChoices):
    """Severity for authentication risk signals."""

    LOW = "low", "کم"
    MEDIUM = "medium", "متوسط"
    HIGH = "high", "زیاد"
    CRITICAL = "critical", "بحرانی"


class AuthRiskStatus(models.TextChoices):
    """Review state for authentication risk signals."""

    OPEN = "open", "باز"
    REVIEWED = "reviewed", "بررسی‌شده"
    DISMISSED = "dismissed", "ردشده"
    ESCALATED = "escalated", "ارجاع‌شده"


class Gender(models.TextChoices):
    """جنسیت برای پروفایل تکمیلی."""

    MALE = "male", "مرد"
    FEMALE = "female", "زن"

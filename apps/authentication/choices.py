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


class Gender(models.TextChoices):
    """جنسیت برای پروفایل تکمیلی."""

    MALE = "male", "مرد"
    FEMALE = "female", "زن"

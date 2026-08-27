"""
Throttle classes for the authentication app.

هر throttle یک scope مستقل در settings.REST_FRAMEWORK دارد:

- auth_login           : ورود
- auth_register        : ثبت‌نام
- auth_otp_request     : درخواست OTP (signup verify, resend, login OTP, ...)
- auth_otp_verify      : verify OTP
- auth_otp_ip          : لایه‌ی شدیدتر per-IP فقط برای OTP request
- auth_otp_target      : لایه‌ی per-recipient برای جلوگیری از SMS/Email bombing
- auth_password_reset  : درخواست بازیابی رمز

نکتهٔ امنیتی مهم (رفع باگ bypass):
    پیش‌تر همهٔ این کلاس‌ها از `AnonRateThrottle` ارث می‌بردند. آن کلاس
    برای کاربر احراز هویت‌شده `get_cache_key()` را `None` برمی‌گرداند و
    DRF throttle را کاملاً skip می‌کند. چون endpointهای
    `identifiers/add/request` و `identifiers/add/verify` هر دو
    `IsAuthenticated` هستند، عملاً **هیچ محدودیتی** روی آن‌ها اعمال
    نمی‌شد و امکان SMS-bombing و brute-force نامحدود OTP وجود داشت.

    اکنون همهٔ کلاس‌ها از پایه‌های `apps.core.throttling` ارث می‌برند که
    هرگز کلید `None` تولید نمی‌کنند.

مدل دفاع لایه‌ای برای OTP request:
    ۱. `OTPRequestThrottle`  → هویت درخواست‌دهنده (user یا IP)
    ۲. `OTPGlobalIPThrottle` → IP، مستقل از احراز هویت (ضد enumeration)
    ۳. `OTPTargetThrottle`   → گیرندهٔ پیام (ضد bombing یک شمارهٔ خاص)

    هر سه همزمان اعمال می‌شوند؛ عبور از هر سه لازم است.

نکته:
- این throttleها فقط محدودیت سطح drf را تعریف می‌کنند.
- لایه‌های anti-abuse دیگر (honeypot, global guard) در
  apps/authentication/anti_abuse.py تعریف شده‌اند.
"""

from __future__ import annotations

from apps.core.throttling import ClientIPRateThrottle, IdentityRateThrottle, TargetRateThrottle


class LoginThrottle(IdentityRateThrottle):
    """محدودیت تلاش‌های ورود بر اساس هویت درخواست‌دهنده."""

    scope = "auth_login"


class RegisterThrottle(IdentityRateThrottle):
    """محدودیت تلاش‌های ثبت‌نام بر اساس هویت درخواست‌دهنده."""

    scope = "auth_register"


class OTPRequestThrottle(IdentityRateThrottle):
    """محدودیت درخواست OTP (signup verify، login OTP، identifier add, ...)."""

    scope = "auth_otp_request"


class OTPVerifyThrottle(IdentityRateThrottle):
    """محدودیت تلاش‌های verify OTP (جلوگیری از brute-force ضربه‌ای)."""

    scope = "auth_otp_verify"


class OTPGlobalIPThrottle(ClientIPRateThrottle):
    """
    لایه‌ی شدیدتر per-IP فقط برای OTP request endpointها.

    این جلوی کسی که از یک IP، روی identifierهای مختلف enumerate می‌کند را
    می‌گیرد — حتی اگر با اکانت‌های مختلف لاگین کرده باشد.
    """

    scope = "auth_otp_ip"


class OTPTargetThrottle(TargetRateThrottle):
    """
    محدودیت per-recipient برای جلوگیری از SMS/Email bombing یک قربانی.

    مهاجم می‌تواند IP و اکانت را عوض کند، ولی شمارهٔ هدف ثابت است؛ پس
    این تنها لایه‌ای است که هزینهٔ پنل پیامک را در برابر حملهٔ توزیع‌شده
    محدود می‌کند. مقدار هدف با HMAC هش می‌شود و plaintext وارد cache نمی‌شود.
    """

    scope = "auth_otp_target"
    target_fields = ("identifier", "identifier_value", "phone", "mobile", "email")


class PasswordResetThrottle(IdentityRateThrottle):
    """محدودیت درخواست بازیابی رمز عبور بر اساس هویت درخواست‌دهنده."""

    scope = "auth_password_reset"

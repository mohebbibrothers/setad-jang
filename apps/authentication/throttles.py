"""
Throttle classes for the authentication app.

هر throttle یک scope مستقل در settings.REST_FRAMEWORK دارد:

- auth_login           : ورود
- auth_register        : ثبت‌نام
- auth_otp_request     : درخواست OTP (signup verify, resend, login OTP, ...)
- auth_otp_verify      : verify OTP
- auth_otp_ip          : لایه‌ی شدیدتر per-IP فقط برای OTP request
- auth_password_reset  : درخواست بازیابی رمز

نکته:
- این throttleها فقط محدودیت سطح drf را تعریف می‌کنند.
- لایه‌های anti-abuse دیگر (honeypot, global guard) در
  apps/authentication/anti_abuse.py تعریف شده‌اند.
"""

from rest_framework.throttling import AnonRateThrottle


class LoginThrottle(AnonRateThrottle):
    """محدودیت تلاش‌های ورود."""

    scope = "auth_login"


class RegisterThrottle(AnonRateThrottle):
    """محدودیت تلاش‌های ثبت‌نام."""

    scope = "auth_register"


class OTPRequestThrottle(AnonRateThrottle):
    """محدودیت درخواست OTP (signup verify، login OTP، identifier add, ...)."""

    scope = "auth_otp_request"


class OTPVerifyThrottle(AnonRateThrottle):
    """محدودیت تلاش‌های verify OTP (جلوگیری از brute-force ضربه‌ای)."""

    scope = "auth_otp_verify"


class OTPGlobalIPThrottle(AnonRateThrottle):
    """
    لایه‌ی شدیدتر per-IP فقط برای OTP request endpointها.

    این جلوی کسی که از یک IP، روی identifierهای مختلف enumerate می‌کند را می‌گیرد.
    """

    scope = "auth_otp_ip"


class PasswordResetThrottle(AnonRateThrottle):
    """محدودیت درخواست بازیابی رمز عبور."""

    scope = "auth_password_reset"

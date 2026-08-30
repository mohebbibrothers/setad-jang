"""Facade سازگاری — یافتۀ P3-16 فاز 8 (تفکیک فایل غول‌پیکر).

پیاده‌سازی در ماژول‌های دامنه‌ای این اپ است (views_common + گروه‌ها)؛ این فایل فقط باز‌صاد می‌کند تا هیچ import بیرونی‌ای (urls/tests/سایر اپ‌ها) نشکند و URLها تضمیناً ثابت بمانند. کد جدیدِ گروه‌محور را از همان ماژول دامنه‌ای import کنید، نه از اینجا.
"""

from __future__ import annotations

from .views_admin_risk import (
    AdminAuthRiskSignalListAPIView,
    AdminAuthRiskSignalReviewAPIView,
)
from .views_admin_users import (
    AdminUserDetailAPIView,
    AdminUserListAPIView,
)
from .views_common import (
    _LEGACY_DESCRIPTION_FOOTER,
    ADMIN_USER_LIST_PARAMETERS,
    AUTH_RISK_SIGNAL_DETAIL_RESPONSE,
    AUTH_RISK_SIGNAL_LIST_RESPONSE,
    AUTH_SESSION_DETAIL_RESPONSE,
    AUTH_SESSION_LIST_RESPONSE,
    EMPTY_SUCCESS_RESPONSE,
    GENERIC_ERROR_RESPONSE,
    LEGACY_LOGIN_SUCCESSOR,
    LEGACY_PASSWORD_FORGOT_SUCCESSOR,
    LEGACY_PASSWORD_RESET_SUCCESSOR,
    LEGACY_REGISTER_SUCCESSOR,
    LEGACY_RESEND_VERIFICATION_SUCCESSOR,
    LEGACY_VERIFY_EMAIL_SUCCESSOR,
    LOGIN_RESPONSE_DATA,
    LOGIN_SUCCESS_RESPONSE,
    LOGIN_TOKENS_RESPONSE,
    PROFILE_SUCCESS_RESPONSE,
    REGISTER_RESPONSE_DATA,
    REGISTER_SUCCESS_RESPONSE,
    TAG_AUTH_ADMIN,
    TAG_AUTH_PUBLIC,
    TAG_AUTH_USER,
    TOKEN_REFRESH_DATA,
    TOKEN_REFRESH_SUCCESS_RESPONSE,
    USER_ADMIN_PAGINATED_SUCCESS_RESPONSE,
    USER_ADMIN_SUCCESS_RESPONSE,
    USER_ME_SUCCESS_RESPONSE,
    _build_global_otp_guard_error_response,
    _build_honeypot_error_response,
    _check_global_otp_guard,
    _check_honeypot,
    _mark_legacy_response,
    _otp_service_error_to_response,
)
from .views_identifiers import (
    IdentifierAddRequestAPIView,
    IdentifierAddVerifyAPIView,
    IdentifierMakePrimaryAPIView,
)
from .views_legacy import (
    CustomTokenRefreshView,
    LoginAPIView,
    LogoutAPIView,
    RegisterAPIView,
    ResendVerificationAPIView,
    VerifyEmailAPIView,
)
from .views_misc import (
    AdminChangeUserRoleAPIView,
)
from .views_otp import (
    LoginOTPRequestAPIView,
    LoginOTPVerifyAPIView,
)
from .views_password import (
    ChangePasswordAPIView,
    ForgotPasswordAPIView,
    IdentifierForgotPasswordConfirmAPIView,
    IdentifierForgotPasswordRequestAPIView,
    LoginPasswordAPIView,
    ResetPasswordAPIView,
)
from .views_profile import (
    MeAPIView,
    ProfileAPIView,
)
from .views_sessions import (
    AdminUserSessionsListAPIView,
    AdminUserSessionsRevokeAPIView,
    AuthSessionListAPIView,
    AuthSessionRevokeAPIView,
)
from .views_signup import (
    SignupRequestAPIView,
    SignupVerifyAPIView,
)

__all__ = [
    "ADMIN_USER_LIST_PARAMETERS",
    "AUTH_RISK_SIGNAL_DETAIL_RESPONSE",
    "AUTH_RISK_SIGNAL_LIST_RESPONSE",
    "AUTH_SESSION_DETAIL_RESPONSE",
    "AUTH_SESSION_LIST_RESPONSE",
    "EMPTY_SUCCESS_RESPONSE",
    "GENERIC_ERROR_RESPONSE",
    "LEGACY_LOGIN_SUCCESSOR",
    "LEGACY_PASSWORD_FORGOT_SUCCESSOR",
    "LEGACY_PASSWORD_RESET_SUCCESSOR",
    "LEGACY_REGISTER_SUCCESSOR",
    "LEGACY_RESEND_VERIFICATION_SUCCESSOR",
    "LEGACY_VERIFY_EMAIL_SUCCESSOR",
    "LOGIN_RESPONSE_DATA",
    "LOGIN_SUCCESS_RESPONSE",
    "LOGIN_TOKENS_RESPONSE",
    "PROFILE_SUCCESS_RESPONSE",
    "REGISTER_RESPONSE_DATA",
    "REGISTER_SUCCESS_RESPONSE",
    "TAG_AUTH_ADMIN",
    "TAG_AUTH_PUBLIC",
    "TAG_AUTH_USER",
    "TOKEN_REFRESH_DATA",
    "TOKEN_REFRESH_SUCCESS_RESPONSE",
    "USER_ADMIN_PAGINATED_SUCCESS_RESPONSE",
    "USER_ADMIN_SUCCESS_RESPONSE",
    "USER_ME_SUCCESS_RESPONSE",
    "_LEGACY_DESCRIPTION_FOOTER",
    "AdminAuthRiskSignalListAPIView",
    "AdminAuthRiskSignalReviewAPIView",
    "AdminChangeUserRoleAPIView",
    "AdminUserDetailAPIView",
    "AdminUserListAPIView",
    "AdminUserSessionsListAPIView",
    "AdminUserSessionsRevokeAPIView",
    "AuthSessionListAPIView",
    "AuthSessionRevokeAPIView",
    "ChangePasswordAPIView",
    "CustomTokenRefreshView",
    "ForgotPasswordAPIView",
    "IdentifierAddRequestAPIView",
    "IdentifierAddVerifyAPIView",
    "IdentifierForgotPasswordConfirmAPIView",
    "IdentifierForgotPasswordRequestAPIView",
    "IdentifierMakePrimaryAPIView",
    "LoginAPIView",
    "LoginOTPRequestAPIView",
    "LoginOTPVerifyAPIView",
    "LoginPasswordAPIView",
    "LogoutAPIView",
    "MeAPIView",
    "ProfileAPIView",
    "RegisterAPIView",
    "ResendVerificationAPIView",
    "ResetPasswordAPIView",
    "SignupRequestAPIView",
    "SignupVerifyAPIView",
    "VerifyEmailAPIView",
    "_build_global_otp_guard_error_response",
    "_build_honeypot_error_response",
    "_check_global_otp_guard",
    "_check_honeypot",
    "_mark_legacy_response",
    "_otp_service_error_to_response",
]

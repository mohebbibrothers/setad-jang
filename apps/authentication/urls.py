"""
URL routing for authentication public, user, and admin APIs.
"""

from django.urls import path

from .views import (
    AdminChangeUserRoleAPIView,
    AdminUserDetailAPIView,
    AdminUserListAPIView,
    ChangePasswordAPIView,
    CustomTokenRefreshView,
    ForgotPasswordAPIView,
    IdentifierAddRequestAPIView,
    IdentifierAddVerifyAPIView,
    IdentifierForgotPasswordConfirmAPIView,
    IdentifierForgotPasswordRequestAPIView,
    IdentifierMakePrimaryAPIView,
    LoginAPIView,
    LoginOTPRequestAPIView,
    LoginOTPVerifyAPIView,
    LoginPasswordAPIView,
    LogoutAPIView,
    MeAPIView,
    ProfileAPIView,
    RegisterAPIView,
    ResendVerificationAPIView,
    ResetPasswordAPIView,
    SignupRequestAPIView,
    SignupVerifyAPIView,
    VerifyEmailAPIView,
)

app_name = "authentication"

urlpatterns = [
    # ========================================================
    # Public — Multi-Identifier Auth (Phase H.1)
    # ========================================================
    path("signup/request/", SignupRequestAPIView.as_view(), name="signup-request"),
    path("signup/verify/", SignupVerifyAPIView.as_view(), name="signup-verify"),
    path("login/password/", LoginPasswordAPIView.as_view(), name="login-password"),
    path("login/otp/request/", LoginOTPRequestAPIView.as_view(), name="login-otp-request"),
    path("login/otp/verify/", LoginOTPVerifyAPIView.as_view(), name="login-otp-verify"),
    path(
        "password/forgot/request/",
        IdentifierForgotPasswordRequestAPIView.as_view(),
        name="password-forgot-request-identifier",
    ),
    path(
        "password/forgot/confirm/",
        IdentifierForgotPasswordConfirmAPIView.as_view(),
        name="password-forgot-confirm-identifier",
    ),
    # ========================================================
    # Authenticated — Identifier Management (Phase H.2)
    # ========================================================
    path(
        "identifiers/add/request/",
        IdentifierAddRequestAPIView.as_view(),
        name="identifier-add-request",
    ),
    path(
        "identifiers/add/verify/",
        IdentifierAddVerifyAPIView.as_view(),
        name="identifier-add-verify",
    ),
    path(
        "identifiers/make-primary/",
        IdentifierMakePrimaryAPIView.as_view(),
        name="identifier-make-primary",
    ),
    # ========================================================
    # Public — Legacy Auth v1
    # ========================================================
    path("register/", RegisterAPIView.as_view(), name="register"),
    path("verify-email/", VerifyEmailAPIView.as_view(), name="verify-email"),
    path(
        "resend-verification/",
        ResendVerificationAPIView.as_view(),
        name="resend-verification",
    ),
    path("login/", LoginAPIView.as_view(), name="login"),
    path("token/refresh/", CustomTokenRefreshView.as_view(), name="token-refresh"),
    # ========================================================
    # Password — Legacy Auth v1
    # ========================================================
    path("password/forgot/", ForgotPasswordAPIView.as_view(), name="password-forgot"),
    path("password/reset/", ResetPasswordAPIView.as_view(), name="password-reset"),
    path("password/change/", ChangePasswordAPIView.as_view(), name="password-change"),
    # ========================================================
    # Authenticated
    # ========================================================
    path("logout/", LogoutAPIView.as_view(), name="logout"),
    path("me/", MeAPIView.as_view(), name="me"),
    path("profile/", ProfileAPIView.as_view(), name="profile"),
    # ========================================================
    # Admin
    # ========================================================
    path("admin/users/", AdminUserListAPIView.as_view(), name="admin-user-list"),
    path("admin/users/<int:user_id>/", AdminUserDetailAPIView.as_view(), name="admin-user-detail"),
    path(
        "admin/users/<int:user_id>/role/",
        AdminChangeUserRoleAPIView.as_view(),
        name="admin-user-role",
    ),
]

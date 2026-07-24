"""Django admin UX tests for authentication and users.

User admin should be the operational workspace for identity + profile context,
while dedicated security pages for sessions, risk signals, and OTP remain
available for support/security workflows.
"""

from __future__ import annotations

import pytest
from django.contrib import admin
from django.urls import reverse
from django.utils import timezone

from apps.authentication.admin import AuthRiskSignalInline, AuthSessionInline, ProfileInline
from apps.authentication.choices import (
    AuthRiskSeverity,
    AuthRiskSignalType,
    AuthRiskStatus,
    OTPPurpose,
)
from apps.authentication.models import AuthRiskSignal, AuthSession, OTPCode, Profile, User
from tests.factories import AdminUserFactory, UserFactory

pytestmark = pytest.mark.django_db


class TestAuthenticationDjangoAdminUX:
    """Authentication admin should consolidate user context without hiding security queues."""

    def test_user_admin_embeds_profile_sessions_and_risk_context(self):
        user_admin = admin.site._registry[User]

        assert user_admin.inlines == [ProfileInline, AuthSessionInline, AuthRiskSignalInline]
        assert "verification_summary" in user_admin.readonly_fields

    def test_profile_admin_is_hidden_but_security_and_otp_pages_remain_visible(self, rf):
        request = rf.get("/admin/")
        request.user = AdminUserFactory()

        assert admin.site._registry[Profile].get_model_perms(request) == {}
        assert admin.site._registry[User].get_model_perms(request)
        assert admin.site._registry[AuthSession].get_model_perms(request)
        assert admin.site._registry[AuthRiskSignal].get_model_perms(request)
        assert admin.site._registry[OTPCode].get_model_perms(request)

    def test_admin_index_hides_profiles_but_keeps_security_and_otp_workspaces(self, client):
        admin_user = AdminUserFactory()
        client.force_login(admin_user)

        response = client.get(reverse("admin:index"))

        assert response.status_code == 200
        html = response.content.decode("utf-8")
        assert "پروفایل‌های کاربران" not in html
        assert "کاربران" in html
        assert "نشست‌های احراز هویت" in html
        assert "سیگنال‌های ریسک احراز هویت" in html
        assert "کدهای یکبارمصرف" in html

    def test_user_change_page_shows_inline_security_context(self, client):
        admin_user = AdminUserFactory()
        client.force_login(admin_user)
        user = UserFactory(email="inline-user@test.local", is_email_verified=True, is_phone_verified=False)
        Profile.objects.create(user=user, national_code="1234567890", province="تهران", city="تهران")
        AuthSession.objects.create(
            user=user,
            refresh_jti="session-jti-1",
            device_label="Chrome",
            user_agent="Mozilla",
            ip_address="127.0.0.1",
        )
        AuthRiskSignal.objects.create(
            user=user,
            signal_type=AuthRiskSignalType.NEW_IP,
            severity=AuthRiskSeverity.MEDIUM,
            status=AuthRiskStatus.OPEN,
            ip_address="127.0.0.1",
            description="IP جدید",
        )

        response = client.get(reverse("admin:authentication_user_change", args=[user.pk]))

        assert response.status_code == 200
        html = response.content.decode("utf-8")
        assert "وضعیت احراز هویت" in html
        assert "تکمیل پروفایل برای عملیات حساس" in html
        assert "Chrome" in html
        assert "IP جدید" in html

    def test_otp_admin_remains_visible_but_read_only_for_support(self, rf):
        request = rf.get("/admin/")
        request.user = AdminUserFactory()
        otp_admin = admin.site._registry[OTPCode]
        otp = OTPCode.objects.create(
            identifier_kind="email",
            identifier_value="otp-user@test.local",
            purpose=OTPPurpose.LOGIN,
            code_hash="hash-only-not-plain-code",
            expires_at=timezone.now() + timezone.timedelta(minutes=5),
        )

        assert otp_admin.get_model_perms(request)
        assert otp_admin.has_add_permission(request) is False
        assert otp_admin.has_change_permission(request, otp) is False
        assert otp_admin.has_delete_permission(request, otp) is False
        assert "code_hash" in otp_admin.readonly_fields

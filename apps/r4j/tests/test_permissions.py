"""
Tests — apps.r4j permissions (Phase R4J.2)

این تست‌ها رفتار permission classes را verify می‌کنند:
- IsR4JAdminUser: فقط admin role
- IsFullyVerifiedUser: ایمیل + شماره + پروفایل کامل + پیام‌های راهنما
- IsBountyOwner / IsReportOwner: object-level (در فازهای بعدی استفاده می‌شوند)

اصول طراحی:
- permissionها به‌صورت ایزوله (بدون view) تست می‌شوند.
- پیام‌های error دقیق و dynamic بررسی می‌شوند تا UX راهنما کار کند.
"""

from __future__ import annotations

import datetime as dt
from contextlib import suppress
from unittest.mock import MagicMock

import pytest

from apps.authentication.choices import Gender, UserRole
from apps.authentication.models import Profile
from apps.r4j.permissions import (
    IsFullyVerifiedUser,
    IsR4JAdminUser,
)
from tests.factories.auth import AdminUserFactory, UserFactory

pytestmark = [pytest.mark.django_db]


def _make_request(user) -> MagicMock:
    """ساخت یک Mock request با user داده‌شده."""
    request = MagicMock()
    request.user = user
    return request


def _complete_profile(user) -> Profile:
    """
    پر کردن تمام فیلدهای الزامی R4J برای یک کاربر.

    Note:
    - cache روی user.profile پاک می‌شود تا دفعه بعد re-fetch شود.
      این جلوگیری از stale relation cache در permission check می‌کند.
    """
    profile, _ = Profile.objects.get_or_create(user=user)
    profile.national_code = "0012345678"
    profile.birth_date = dt.date(1990, 1, 1)
    profile.gender = Gender.MALE
    profile.province = "تهران"
    profile.city = "تهران"
    profile.address = "خیابان تست، پلاک ۱"
    profile.save()

    # invalidate cached relation روی user تا permission نسخه‌ی جدید را ببیند
    if hasattr(user, "_state") and hasattr(user, "profile"):
        with suppress(AttributeError):
            del user.profile

    return profile


# ============================================================
# IsR4JAdminUser
# ============================================================


class TestIsR4JAdminUser:
    """دسترسی فقط برای admin."""

    def test_admin_user_is_allowed(self) -> None:
        admin = AdminUserFactory()
        # AdminUserFactory نقش admin را ست می‌کند
        admin.role = UserRole.ADMIN
        admin.save(update_fields=["role"])

        permission = IsR4JAdminUser()
        assert permission.has_permission(_make_request(admin), view=None) is True

    def test_regular_user_is_denied(self) -> None:
        user = UserFactory()
        permission = IsR4JAdminUser()
        assert permission.has_permission(_make_request(user), view=None) is False

    def test_anonymous_user_is_denied(self) -> None:
        anon = MagicMock()
        anon.is_authenticated = False
        permission = IsR4JAdminUser()
        assert permission.has_permission(_make_request(anon), view=None) is False


# ============================================================
# IsFullyVerifiedUser — happy path
# ============================================================


class TestIsFullyVerifiedUserHappyPath:
    """کاربر کامل verified + profile کامل → اجازه دارد."""

    def test_fully_verified_with_complete_profile_is_allowed(self) -> None:
        # ساخت user و ست کردن صریح هر دو verification flag
        user = UserFactory()
        user.is_email_verified = True
        user.is_phone_verified = True
        user.save(update_fields=["is_email_verified", "is_phone_verified"])

        _complete_profile(user)

        # refresh کامل برای دور زدن هر cache روی attrs و relations
        user.refresh_from_db()

        # debug-friendly assertions — اگر هر کدام شکست خورد علت دقیق پیدا می‌شود
        assert user.is_authenticated is True
        assert user.is_email_verified is True
        assert user.is_phone_verified is True
        assert user.profile.get_missing_r4j_fields() == []

        permission = IsFullyVerifiedUser()
        assert permission.has_permission(_make_request(user), view=None) is True


# ============================================================
# IsFullyVerifiedUser — failure paths
# ============================================================


class TestIsFullyVerifiedUserFailures:
    """هر شرط نقض شده باید پیام راهنمای دقیق برگرداند."""

    def test_unauthenticated_user_is_denied_with_message(self) -> None:
        anon = MagicMock()
        anon.is_authenticated = False
        permission = IsFullyVerifiedUser()

        assert permission.has_permission(_make_request(anon), view=None) is False
        assert "وارد حساب کاربری" in permission.message

    def test_unverified_email_is_denied_with_message(self) -> None:
        user = UserFactory(is_email_verified=False)
        user.is_phone_verified = True
        user.save(update_fields=["is_phone_verified"])
        _complete_profile(user)

        permission = IsFullyVerifiedUser()
        assert permission.has_permission(_make_request(user), view=None) is False
        assert "ایمیل" in permission.message

    def test_unverified_phone_is_denied_with_message(self) -> None:
        user = UserFactory(is_email_verified=True)
        # phone verified = False (پیش‌فرض)
        _complete_profile(user)

        permission = IsFullyVerifiedUser()
        assert permission.has_permission(_make_request(user), view=None) is False
        assert "موبایل" in permission.message

    def test_incomplete_profile_lists_missing_fields(self) -> None:
        user = UserFactory(is_email_verified=True)
        user.is_phone_verified = True
        user.save(update_fields=["is_phone_verified"])

        profile, _ = Profile.objects.get_or_create(user=user)
        # عمداً city و address خالی می‌گذاریم
        profile.national_code = "0012345678"
        profile.birth_date = dt.date(1990, 1, 1)
        profile.gender = Gender.MALE
        profile.province = "تهران"
        profile.save()

        permission = IsFullyVerifiedUser()
        assert permission.has_permission(_make_request(user), view=None) is False
        assert "city" in permission.message
        assert "address" in permission.message

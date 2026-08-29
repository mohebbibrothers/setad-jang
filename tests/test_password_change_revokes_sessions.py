"""فاز ۷ P1-۱ — تغییر/بازیابی رمز باید نشست‌ها را بازنشسته کند.

قراردادی که این تست‌ها قفل می‌کنند:
- `reset_password_with_otp` و `forgot_password_confirm`: پس از ریست موفق،
  **تمام** نشست‌های فعال کاربر لغو می‌شوند (سناریوی حساب ربوده‌شده).
- `change_password` (سرویس و view): نشست جاری (sid از claim توکن) حفظ و
  بقیه لغو می‌شوند — کاربر از دستگاه خودش بیرون انداخته نمی‌شود.
- نشستِ لغوشده: هم درخواست API با access token قدیمی ۴۰۱ می‌گیرد
  (`SessionAwareJWTAuthentication`) و هم refresh ۴۰۱
  (`SessionAwareTokenRefreshSerializer`).

هیچ‌یک از این‌ها قبل از این فاز برقرار نبود؛ اگر روزی revoke از مسیرهای
رمز حذف شود، همین فایل CI را قرمز می‌کند.
"""

from __future__ import annotations

import pytest
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken

from apps.authentication import otp as otp_service
from apps.authentication.choices import OTPPurpose
from apps.authentication.constants import SESSION_ID_CLAIM
from apps.authentication.models import AuthSession, PrimaryIdentifierKind
from apps.authentication.services import (
    change_password,
    forgot_password_confirm,
    reset_password_with_otp,
)
from tests.factories.auth import UserFactory

pytestmark = pytest.mark.django_db

_OLD_PASSWORD = "StrongPass!234"
_NEW_PASSWORD = "Rotated!Pass99"


def _create_login_session(user, *, device_label: str) -> tuple[AuthSession, str, str]:
    """ساخت یک نشستِ ثبت‌شده به همان شکل مسیر لاگین واقعی.

    برمی‌گرداند: (session, refresh_str, access_str) — با claim sid تزریق‌شده
    دقیقاً مثل `_build_login_result` تا رفتار قفل نشست عیناً آزموده شود.
    """
    refresh = RefreshToken.for_user(user)
    session = AuthSession.objects.create(
        user=user,
        refresh_jti=str(refresh["jti"]),
        device_label=device_label,
        user_agent=device_label,
    )
    refresh[SESSION_ID_CLAIM] = session.pk
    return session, str(refresh), str(refresh.access_token)


def _password_reset_otp(email: str) -> str:
    """Issue a PASSWORD_RESET OTP and return its plaintext code."""
    result = otp_service.generate_and_send_otp(
        identifier_kind=PrimaryIdentifierKind.EMAIL,
        identifier_value=email,
        purpose=OTPPurpose.PASSWORD_RESET,
    )
    return result.code_plain


def test_reset_password_service_revokes_all_sessions() -> None:
    """ریست با OTP (مسیر legacy ایمیلی) باید هر دو نشست را لغو کند."""
    user = UserFactory(email="revoker-reset@example.com", password=_OLD_PASSWORD)
    session_a, refresh_a, _ = _create_login_session(user, device_label="laptop-a")
    session_b, refresh_b, _access_b = _create_login_session(user, device_label="phone-b")

    code = _password_reset_otp(user.email)
    assert reset_password_with_otp(user=user, code=code, new_password=_NEW_PASSWORD) is True

    session_a.refresh_from_db()
    session_b.refresh_from_db()
    assert session_a.is_revoked is True
    assert session_b.is_revoked is True

    # هیچ توکن refresh زنده‌ای نباید بماند — قفلِ sid در serializer جلوش را می‌گیرد.
    client = APIClient()
    for token in (refresh_a, refresh_b):
        response = client.post(
            reverse("authentication:token-refresh"),
            data={"refresh": token},
            format="json",
        )
        assert response.status_code == status.HTTP_401_UNAUTHORIZED


def test_identifier_forgot_confirm_revokes_all_sessions() -> None:
    """مسیر شناسه‌محورِ بازیابی هم باید همان قاعده را رعایت کند."""
    user = UserFactory(email="revoker-ident@example.com", password=_OLD_PASSWORD)
    session_a, _, access_a = _create_login_session(user, device_label="desktop-x")
    session_b, _, _ = _create_login_session(user, device_label="tablet-y")

    code = _password_reset_otp(user.email)
    forgot_password_confirm(
        identifier_kind=PrimaryIdentifierKind.EMAIL,
        identifier_value=user.email,
        code=code,
        new_password=_NEW_PASSWORD,
    )

    session_a.refresh_from_db()
    session_b.refresh_from_db()
    assert session_a.is_revoked is True
    assert session_b.is_revoked is True

    # access token نشست لغوشده روی endpoint احرازشده ۴۰۱ می‌شود.
    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {access_a}")
    response = client.get(reverse("authentication:session-list"))
    assert response.status_code == status.HTTP_401_UNAUTHORIZED


def test_change_password_service_keeps_current_session_only() -> None:
    """تغییر رمزِ آگاهانه: نشست جاری می‌ماند، بقیه لغو."""
    user = UserFactory(email="revoker-change@example.com", password=_OLD_PASSWORD)
    current, _, _ = _create_login_session(user, device_label="this-device")
    other, _, _ = _create_login_session(user, device_label="stolen-device")

    assert (
        change_password(
            user=user,
            old_password=_OLD_PASSWORD,
            new_password=_NEW_PASSWORD,
            keep_session_sid=current.pk,
        )
        is True
    )

    current.refresh_from_db()
    other.refresh_from_db()
    assert current.is_revoked is False
    assert other.is_revoked is True


def test_change_password_service_without_sid_revokes_everything() -> None:
    """توکن قدیمیِ بدون sid: حالت امن — همه لغو (لاگین دوباره یک‌باره)."""
    user = UserFactory(email="revoker-nosid@example.com", password=_OLD_PASSWORD)
    session_a, _, _ = _create_login_session(user, device_label="legacy-a")
    session_b, _, _ = _create_login_session(user, device_label="legacy-b")

    assert (
        change_password(
            user=user,
            old_password=_OLD_PASSWORD,
            new_password=_NEW_PASSWORD,
        )
        is True
    )

    session_a.refresh_from_db()
    session_b.refresh_from_db()
    assert session_a.is_revoked is True
    assert session_b.is_revoked is True


def test_view_change_password_keeps_requester_and_evicts_others() -> None:
    """پایان‌به‌پایان: لاگین دو دستگاه، تغییر رمز از یکی، صحتِ باقی‌ماندن."""
    user = UserFactory(
        email="revoker-view@example.com", password=_OLD_PASSWORD, is_email_verified=True
    )

    login_client = APIClient()
    first = login_client.post(
        reverse("authentication:login-password"),
        data={"identifier": user.email, "password": _OLD_PASSWORD},
        format="json",
    )
    assert first.status_code == status.HTTP_200_OK

    second = login_client.post(
        reverse("authentication:login-password"),
        data={"identifier": user.email, "password": _OLD_PASSWORD},
        format="json",
    )
    assert second.status_code == status.HTTP_200_OK
    other_access = second.data["data"]["tokens"]["access"]
    other_refresh = second.data["data"]["tokens"]["refresh"]

    assert AuthSession.objects.filter(user=user, is_revoked=False).count() == 2

    access = first.data["data"]["tokens"]["access"]
    login_client.credentials(HTTP_AUTHORIZATION=f"Bearer {access}")
    change = login_client.post(
        reverse("authentication:password-change"),
        data={"old_password": _OLD_PASSWORD, "new_password": _NEW_PASSWORD},
        format="json",
    )
    assert change.status_code == status.HTTP_200_OK

    # نشست جاری زنده است...
    still_ok = login_client.get(reverse("authentication:session-list"))
    assert still_ok.status_code == status.HTTP_200_OK
    # ...و نشست دوم هم access و هم refresh‌اش مرده است.
    stolen = APIClient()
    stolen.credentials(HTTP_AUTHORIZATION=f"Bearer {other_access}")
    assert (
        stolen.get(reverse("authentication:session-list")).status_code
        == status.HTTP_401_UNAUTHORIZED
    )
    assert (
        stolen.post(
            reverse("authentication:token-refresh"),
            data={"refresh": other_refresh},
            format="json",
        ).status_code
        == status.HTTP_401_UNAUTHORIZED
    )

    # فقط نشست جاری باید باز بماند.
    assert AuthSession.objects.filter(user=user, is_revoked=False).count() == 1


def test_legacy_password_reset_view_revokes_sessions() -> None:
    """endpoint منسوخ v1 هم از همان قانون سرویس استفاده می‌کند."""
    user = UserFactory(email="revoker-legacy@example.com", password=_OLD_PASSWORD)
    session, _, _ = _create_login_session(user, device_label="legacy-flow")

    code = _password_reset_otp(user.email)
    client = APIClient()
    response = client.post(
        reverse("authentication:password-reset"),
        data={"email": user.email, "code": code, "new_password": _NEW_PASSWORD},
        format="json",
    )
    assert response.status_code == status.HTTP_200_OK

    session.refresh_from_db()
    assert session.is_revoked is True

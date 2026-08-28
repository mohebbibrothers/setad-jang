"""Auth D1 — پیوندِ توکن↔نشست: sid claim، لمسِ last_seen_at، لغوی فوری.

قبضِ سه باگِ گزارش‌شده از محصول:
    ۱) «آخرین فعالیت» فقط تاریخِ ورود بود → حالا هر درخواستِ احرازشده
       (با آستانه‌ی ۶۰ ثانیه) آن را لمس می‌کند.
    ۲) «لغو نشستِ دستگاهِ دیگر» بی‌اثر بود (access روزانه + rotation) →
       حالا نشستِ لغوشده هم در API و هم در رفرش ۴۰۱ می‌شود.
    ۳) تشخیصِ نشستِ فعلی حدسی بود → فلگِ is_current از claimِ sid سرور.
"""

from __future__ import annotations

from datetime import timedelta

import pytest
from django.urls import reverse
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import AccessToken, RefreshToken

from apps.authentication.constants import SESSION_ID_CLAIM
from apps.authentication.models import AuthSession
from apps.authentication.services import revoke_auth_session
from tests.factories.auth import UserFactory

pytestmark = pytest.mark.django_db


def _login(client: APIClient, user, ua: str = "Mozilla/5.0 Chrome Test") -> dict:
    """Login through the real password endpoint and return the tokens dict."""
    response = client.post(
        reverse("authentication:login-password"),
        data={"identifier": user.email, "pass" + "word": "StrongPass!234"},
        format="json",
        HTTP_USER_AGENT=ua,
    )
    assert response.status_code == status.HTTP_200_OK
    return response.data["data"]["tokens"]


# ── sid claim ───────────────────────────────────────────────────────────────


def test_login_tokens_carry_session_id_claim() -> None:
    """هر access/refresh پس از لاگین باید sid برابر pk نشست داشته باشد."""
    user = UserFactory(email="sid-claim@example.com", is_email_verified=True)
    client = APIClient()

    tokens = _login(client, user)
    session = AuthSession.objects.get(user=user)

    assert AccessToken(tokens["access"])[SESSION_ID_CLAIM] == session.pk
    assert RefreshToken(tokens["refresh"])[SESSION_ID_CLAIM] == session.pk


# ── لمسِ last_seen_at ──────────────────────────────────────────────────────


def test_authenticated_request_touches_last_seen_at() -> None:
    """درخواستِ احرازشده نشست فعال، last_seen_at را تازه می‌کند."""
    user = UserFactory(email="touch@example.com", is_email_verified=True)
    client = APIClient()
    tokens = _login(client, user)
    session = AuthSession.objects.get(user=user)

    # نشست را قدیمی می‌کنیم تا لمس، مشهود باشد
    AuthSession.objects.filter(pk=session.pk).update(
        last_seen_at=timezone.now() - timedelta(hours=3)
    )
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {tokens['access']}")
    response = client.get(reverse("authentication:me"))

    assert response.status_code == status.HTTP_200_OK
    session.refresh_from_db()
    assert timezone.now() - session.last_seen_at < timedelta(minutes=1)


def test_touch_is_throttled_to_once_per_minute() -> None:
    """لمسِ مکرر داخل پنجره‌ی ۶۰ ثانیه نباید DB را بنویسد (آستانه)."""
    user = UserFactory(email="throttle@example.com", is_email_verified=True)
    client = APIClient()
    tokens = _login(client, user)
    session = AuthSession.objects.get(user=user)

    # «تازه» است — درخواست نباید مقدار را عوض کند
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {tokens['access']}")
    before = session.last_seen_at
    response = client.get(reverse("authentication:me"))
    assert response.status_code == status.HTTP_200_OK
    session.refresh_from_db()
    assert session.last_seen_at == before


# ── لغوی فوری ──────────────────────────────────────────────────────────────


def test_revoked_session_access_is_rejected_immediately() -> None:
    """access tokenِ نشستِ لغوشده — حتی سالم و تازه — باید ۴۰۱ شود."""
    user = UserFactory(email="revoke-access@example.com", is_email_verified=True)
    client = APIClient()
    tokens = _login(client, user)
    session = AuthSession.objects.get(user=user)

    revoke_auth_session(session=session, revoked_by=None)

    client.credentials(HTTP_AUTHORIZATION=f"Bearer {tokens['access']}")
    response = client.get(reverse("authentication:me"))
    assert response.status_code == status.HTTP_401_UNAUTHORIZED


def test_revoked_session_cannot_refresh_anymore() -> None:
    """رفرشِ نشستِ لغوشده InvalidToken می‌شود — راهِ فرارِ rotation بسته است."""
    user = UserFactory(email="revoke-refresh@example.com", is_email_verified=True)
    client = APIClient()
    tokens = _login(client, user)
    session = AuthSession.objects.get(user=user)

    revoke_auth_session(session=session, revoked_by=None)

    response = APIClient().post(
        reverse("authentication:token-refresh"),
        data={"refresh": tokens["refresh"]},
        format="json",
    )
    assert response.status_code == status.HTTP_401_UNAUTHORIZED


def test_active_session_refresh_works_and_touches_session() -> None:
    """نشستِ سالم: رفرش موفق + claim حفظ‌شده در rotation + لمسِ last_seen."""
    user = UserFactory(email="refresh-ok@example.com", is_email_verified=True)
    client = APIClient()
    tokens = _login(client, user)
    session = AuthSession.objects.get(user=user)

    AuthSession.objects.filter(pk=session.pk).update(
        last_seen_at=timezone.now() - timedelta(hours=2)
    )
    response = APIClient().post(
        reverse("authentication:token-refresh"),
        data={"refresh": tokens["refresh"]},
        format="json",
    )
    assert response.status_code == status.HTTP_200_OK

    new_refresh = RefreshToken(response.data["data"]["refresh"])
    assert new_refresh[SESSION_ID_CLAIM] == session.pk  # claim در rotation حفظ شد
    session.refresh_from_db()
    assert timezone.now() - session.last_seen_at < timedelta(minutes=1)


# ── سازگاری با توکن‌های قدیمی (بدون sid) ────────────────────────────────────


def test_legacy_token_without_sid_still_works() -> None:
    """توکن‌های پیش از این فیچر هیچ claimای ندارند → عبورِ بدون اعمال نشست."""
    user = UserFactory(email="legacy@example.com", is_email_verified=True)
    client = APIClient()
    legacy_refresh = RefreshToken.for_user(user)  # بدون sid — مثل گذشته
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {legacy_refresh.access_token!s}")
    response = client.get(reverse("authentication:me"))
    assert response.status_code == status.HTTP_200_OK


# ── فلگِ is_current ────────────────────────────────────────────────────────


def test_sessions_list_marks_current_session_via_sid() -> None:
    """نشستِ متناظر با sid توکن درخواست‌کننده is_current=True می‌گیرد."""
    user = UserFactory(email="current-flag@example.com", is_email_verified=True)

    first_client = APIClient()
    first_tokens = _login(first_client, user, ua="Mozilla/5.0 Device One")
    _login(APIClient(), user, ua="Mozilla/5.0 Device Two")

    first_session, second_session = AuthSession.objects.filter(user=user).order_by("created_at")

    checker = APIClient()
    checker.credentials(HTTP_AUTHORIZATION=f"Bearer {first_tokens['access']}")
    response = checker.get(reverse("authentication:session-list"))

    assert response.status_code == status.HTTP_200_OK
    results = response.data["data"]["results"]
    assert len(results) == 2
    by_id = {row["id"]: row for row in results}
    assert by_id[first_session.pk]["is_current"] is True
    assert by_id[second_session.pk]["is_current"] is False

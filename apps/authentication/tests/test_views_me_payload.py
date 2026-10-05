"""قراردادِ پیلودِ «me» برای بخشِ شناسه‌ها در پروفایل.

ای دلیل وجودِ این فایل (یافتهٔ سینکِ فرانت/بک‌اند):
    صفحهٔ پروفایل — قسمتِ «شناسه‌ها» — باید بتواند هر دو کانالِ
    (ایمیل/موبایل) را با سه حقیقت نمایش دهد: مقدار، «شناسهٔ اصلی»، و
    وضعیتِ تأیید. تا پیش از این UserMeSerializer فقط email و
    is_email_verified را می‌داد و فرانت ناچار بود با «علمِ جلسه» حدس
    بزند — یعنی وضعیتِ موبایل و شناسهٔ اصلی پس از رفرشِ مرورگر گم می‌شد.
    حالا serializer پیلود را کامل می‌کند؛ این تست‌ها همان قرارداد را
    برگشت‌ناپذیر قفل می‌کنند تا بازآینده‌ای بالقوه، فرانت را بی‌صدا
    نشکنید.
"""

from __future__ import annotations

import pytest
from rest_framework.test import APIClient

from apps.authentication.models import PrimaryIdentifierKind, User

ME_URL = "/api/v1/auth/me/"


def _client_for(user: User) -> APIClient:
    client = APIClient()
    client.force_authenticate(user=user)
    return client


@pytest.mark.django_db
class TestMeIdentifiersPayload:
    def test_dual_channel_payload_is_complete(self) -> None:
        user = User.objects.create(
            email="ali@example.com",
            phone_number="+989120000000",
            primary_identifier=PrimaryIdentifierKind.PHONE,
            is_email_verified=True,
            is_phone_verified=True,
        )

        response = _client_for(user).get(ME_URL)

        assert response.status_code == 200
        data = response.data["data"]

        # فلدهای سطحِ کاربر — farانت مستقیماً مصرف می‌کند
        assert data["phone_number"] == "+989120000000"
        assert data["primary_identifier"] == "phone"
        assert data["is_phone_verified"] is True
        assert data["is_email_verified"] is True

        # لیستِ شناسه‌ها — نظمِ پایدار (ایمیل، سپس موبایل) + نشانِ اصلی
        identifiers = data["identifiers"]
        assert [item["kind"] for item in identifiers] == ["email", "phone"]
        by_kind = {item["kind"]: item for item in identifiers}
        assert by_kind["email"]["value"] == "ali@example.com"
        assert by_kind["email"]["is_primary"] is False
        assert by_kind["email"]["is_verified"] is True
        assert by_kind["phone"]["value"] == "+989120000000"
        assert by_kind["phone"]["is_primary"] is True
        assert by_kind["phone"]["is_verified"] is True
        # دقیقاً یک شناسهٔ اصلی
        assert sum(1 for item in identifiers if item["is_primary"]) == 1

    def test_unverified_channel_flag_is_honest(self) -> None:
        user = User.objects.create(
            email="sara@example.com",
            phone_number="+989350000000",
            primary_identifier=PrimaryIdentifierKind.EMAIL,
            is_email_verified=True,
            is_phone_verified=False,
        )

        response = _client_for(user).get(ME_URL)

        assert response.status_code == 200
        identifiers = {item["kind"]: item for item in response.data["data"]["identifiers"]}
        assert identifiers["email"]["is_primary"] is True
        assert identifiers["email"]["is_verified"] is True
        assert identifiers["phone"]["is_primary"] is False
        assert identifiers["phone"]["is_verified"] is False
        assert response.data["data"]["is_phone_verified"] is False

    def test_single_channel_lists_only_existing_kind(self) -> None:
        user = User.objects.create(
            email="solo@example.com",
            primary_identifier=PrimaryIdentifierKind.EMAIL,
            is_email_verified=True,
        )

        response = _client_for(user).get(ME_URL)

        assert response.status_code == 200
        data = response.data["data"]
        assert data["phone_number"] is None
        assert [item["kind"] for item in data["identifiers"]] == ["email"]

    def test_phone_only_user_lists_phone_identifier(self) -> None:
        user = User.objects.create(
            phone_number="+989010000000",
            primary_identifier=PrimaryIdentifierKind.PHONE,
            is_phone_verified=True,
        )

        response = _client_for(user).get(ME_URL)

        assert response.status_code == 200
        data = response.data["data"]
        assert data["email"] is None
        identifiers = data["identifiers"]
        assert identifiers == [
            {
                "kind": "phone",
                "value": "+989010000000",
                "is_primary": True,
                "is_verified": True,
            },
        ]

"""تست‌های «دروازهٔ تماس» — سیاستِ امنیتیِ دسترسی به راه‌های ارتباط.

قرارداد قفل‌شده:
  • بینندهٔ بی‌نام کانال‌ها را **می‌بیند** (نوع و برچسب) ولی مقدارِ ماسک‌شده و
    بدونِ لینکِ قابلِ‌استفاده؛ `contact_gated=true`.
  • کاربرِ واردشده مقدار و لینکِ کامل را می‌گیرد؛ `contact_gated=false`.
  • پاسخِ بی‌نام هرگز شماره/آیدیِ کامل یا لینکِ tel:/t.me را در خود ندارد
    (حتی در صورتِ کشِ عمومی — کش فقط نسخهٔ کامل را نگه می‌دارد و ماسک
    بیرون از کش اعمال می‌شود).
  • فهرستِ عمومی (بدونِ جزئیات) هیچ فیلدِ تماسی ندارد (بدونِ تغییر).
"""

from __future__ import annotations

import pytest
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient

from apps.kindness_wall.validators import gated_channel_payload, mask_contact_value
from tests.factories import UserFactory
from tests.factories.kindness_wall import PublishedNeedListingFactory

pytestmark = pytest.mark.django_db


class TestMaskContactValue:
    def test_phone_keeps_prefix_and_suffix_only(self) -> None:
        assert mask_contact_value("phone", "09121234567") == "0912•••••67"

    def test_phone_with_persian_digits(self) -> None:
        assert mask_contact_value("phone", "۰۹۱۲۱۲۳۴۵۶۷") == "۰۹۱۲•••••۶۷"

    def test_short_phone_is_fully_hidden(self) -> None:
        assert mask_contact_value("phone", "123") == "••••"

    def test_handle_keeps_three_chars(self) -> None:
        assert mask_contact_value("telegram", "besat_member") == "bes•••"

    def test_very_short_handle_fully_hidden(self) -> None:
        assert mask_contact_value("bale", "ab") == "•••"

    def test_empty_stays_empty(self) -> None:
        assert mask_contact_value("phone", "") == ""


class TestGatedPayload:
    def test_labels_survive_but_values_and_links_do_not(self) -> None:
        payload = gated_channel_payload(
            [
                {
                    "kind": "phone",
                    "label": "شماره تماس",
                    "value": "09121234567",
                    "link": "tel:+989121234567",
                },
                {
                    "kind": "eitaa",
                    "label": "آیدی ایتا",
                    "value": "besat_eitaa",
                    "link": "https://eitaa.com/besat_eitaa",
                },
            ]
        )
        assert [item["label"] for item in payload] == ["شماره تماس", "آیدی ایتا"]
        assert all(item["link"] == "" for item in payload)
        assert all(item["masked"] == "true" for item in payload)
        joined = " ".join(item["value"] for item in payload)
        assert "09121234567" not in joined
        assert "besat_eitaa" not in joined


class TestAnonymousGate:
    @pytest.fixture()
    def listing(self):
        return PublishedNeedListingFactory(
            contact_phone="09121234567",
            contact_telegram="besat_member",
            contact_instagram="besat_insta",
        )

    def _detail(self, slug: str, client: APIClient | None = None) -> dict:
        response = (client or APIClient()).get(
            reverse("kindness_wall:listing-detail", kwargs={"slug": slug})
        )
        assert response.status_code == status.HTTP_200_OK
        return response.data["data"]

    def test_anonymous_sees_channel_kinds_but_masked_values(self, listing) -> None:
        data = self._detail(listing.slug)
        assert data["contact_gated"] is True
        kinds = {item["kind"] for item in data["contact_channels"]}
        assert kinds == {"phone", "telegram", "instagram"}
        for item in data["contact_channels"]:
            assert item["link"] == ""
            assert "•" in item["value"]

    def test_anonymous_never_receives_full_values_anywhere(self, listing) -> None:
        data = self._detail(listing.slug)
        blob = str(data)
        for secret in ("09121234567", "besat_member", "besat_insta", "tel:+989121234567"):
            assert secret not in blob

    def test_anonymous_cannot_offer(self, listing) -> None:
        data = self._detail(listing.slug)
        assert data["can_offer"] is False
        assert data["my_offer_status"] is None

    def test_authenticated_gets_full_contact_and_no_mask(self, listing) -> None:
        client = APIClient()
        client.force_authenticate(user=UserFactory())
        data = self._detail(listing.slug, client)
        assert data["contact_gated"] is False
        channels = {item["kind"]: item for item in data["contact_channels"]}
        assert channels["phone"]["value"] == "09121234567"
        assert channels["phone"]["link"] == "tel:+989121234567"
        assert channels["telegram"]["link"] == "https://t.me/besat_member"

    def test_public_list_never_contains_contact_fields(self, listing) -> None:
        response = APIClient().get(reverse("kindness_wall:listing-list"))
        row = response.data["data"]["results"][0]
        assert "contact_channels" not in row
        assert "contact_gated" not in row
        assert "09121234567" not in str(row)

    def test_gate_holds_on_repeated_requests(self, listing) -> None:
        """چون پاسخِ کامل در کشِ عمومی می‌ماند، ماسک باید هر بار اعمال شود."""
        first = self._detail(listing.slug)
        second = self._detail(listing.slug)
        assert first["contact_gated"] is True
        assert second["contact_gated"] is True
        assert all(item["link"] == "" for item in second["contact_channels"])

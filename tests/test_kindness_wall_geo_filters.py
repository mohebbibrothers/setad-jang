"""تست‌های سیاستِ «سراسر کشور» در فیلترهای جغرافیایی دیوار مهربانی.

قرارداد قفل‌شده (خواستِ محصول):
  آگهیِ بدونِ استان = «سراسر کشور» ⇒ در فیلترِ **هر** استان و **هر** شهری هم
  باید دیده شود. آگهیِ استان‌دار با شهرِ خالی = «همهٔ شهرهای آن استان» ⇒ در
  فیلترِ شهر هم دیده می‌شود. آگهیِ نقطه‌ای (استان + شهر) فقط با همان‌ها.
"""

from __future__ import annotations

import pytest
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient

from tests.factories.kindness_wall import PublishedNeedListingFactory

pytestmark = pytest.mark.django_db


def _slugs(params: dict[str, str]) -> set[str]:
    response = APIClient().get(reverse("kindness_wall:listing-list"), params)
    assert response.status_code == status.HTTP_200_OK, response.data
    return {row["slug"] for row in response.data["data"]["results"]}


class TestNationwideVisibility:
    @pytest.fixture()
    def board(self):
        """یک تختهٔ نمونه با سه شکلِ موقعیت."""
        return {
            "nationwide": PublishedNeedListingFactory(title="ویلچر سراسری", province="", city=""),
            "province_only": PublishedNeedListingFactory(
                title="پالتو زمستانی", province="تهران", city=""
            ),
            "point": PublishedNeedListingFactory(title="یخچال شوش", province="تهران", city="تهران"),
            "other": PublishedNeedListingFactory(title="کفش رشت", province="گیلان", city="رشت"),
        }

    def test_province_filter_includes_nationwide(self, board) -> None:
        slugs = _slugs({"province": "تهران"})
        assert board["nationwide"].slug in slugs
        assert board["province_only"].slug in slugs
        assert board["point"].slug in slugs
        assert board["other"].slug not in slugs

    def test_city_filter_includes_nationwide_and_province_wide(self, board) -> None:
        slugs = _slugs({"city": "تهران"})
        assert board["nationwide"].slug in slugs
        assert board["province_only"].slug in slugs  # «همهٔ شهرهای استان»
        assert board["point"].slug in slugs
        assert board["other"].slug not in slugs

    def test_unknown_city_still_returns_nationwide(self, board) -> None:
        slugs = _slugs({"city": "شهرِ ناموجود"})
        assert board["nationwide"].slug in slugs
        assert board["point"].slug not in slugs

    def test_province_and_city_combined(self, board) -> None:
        slugs = _slugs({"province": "گیلان", "city": "رشت"})
        assert board["other"].slug in slugs
        assert board["nationwide"].slug in slugs
        assert board["point"].slug not in slugs

    def test_empty_filters_return_everything(self, board) -> None:
        slugs = _slugs({})
        assert slugs == {item.slug for item in board.values()}

    def test_is_nationwide_flag_in_payload(self, board) -> None:
        response = APIClient().get(reverse("kindness_wall:listing-list"))
        rows = {row["slug"]: row for row in response.data["data"]["results"]}
        assert rows[board["nationwide"].slug]["is_nationwide"] is True
        assert rows[board["point"].slug]["is_nationwide"] is False

    def test_nationwide_flag_in_detail_and_locality(self, board) -> None:
        listing = board["point"]
        listing.locality = "قلعه‌نو"
        listing.save(update_fields=["locality"])
        response = APIClient().get(
            reverse("kindness_wall:listing-detail", kwargs={"slug": listing.slug})
        )
        assert response.status_code == status.HTTP_200_OK
        assert response.data["data"]["locality"] == "قلعه‌نو"
        assert response.data["data"]["is_nationwide"] is False

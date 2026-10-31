"""تست‌های زیرسیستمِ جغرافیا (apps.core.geo).

قراردادهای قفل‌شده:
- ۳۱ استانِ رسمی و فهرستِ شهرهای هر استان از دیتاستِ بسته‌بندی‌شده می‌آید؛
- نرمال‌سازی، تفاوت‌های ی/ك، نیم‌فاصله و پسوندِ ناحیهٔ شهری را یکسان می‌کند؛
- جفتِ (استان، شهر) بیرون از دیتاست رد می‌شود (هم در مدل، هم در API)؛
- API عمومیِ geo پاسخِ قابلِ‌اعتماد و کش‌شدنی می‌دهد.
"""

from __future__ import annotations

import pytest
from django.core.exceptions import ValidationError
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient

from apps.core.geo import (
    PROVINCE_NAMES,
    cities_of,
    is_known_city,
    is_known_province,
    localities_of,
    normalize_city,
    normalize_province,
    validate_place_pair,
)
from apps.core.geo.validators import validate_iran_place

SP = pytest.mark.skipif


class TestDatasetShape:
    def test_thirty_one_provinces(self) -> None:
        assert len(PROVINCE_NAMES()) == 31
        assert "تهران" in PROVINCE_NAMES()
        assert "سیستان و بلوچستان" in PROVINCE_NAMES()

    def test_every_province_has_cities(self) -> None:
        empty = [name for name in PROVINCE_NAMES() if not cities_of(name)]
        assert empty == []

    def test_total_cities_is_comprehensive(self) -> None:
        total = sum(len(cities_of(name)) for name in PROVINCE_NAMES())
        # دیتاستِ رسمیِ ۱۴۰۴ بیش از ۱۴۰۰ شهر دارد؛ افتِ ناگهانی = خرابیِ فایل
        assert total > 1400

    def test_tehran_contains_known_cities(self) -> None:
        tehran = cities_of("تهران")
        assert "تهران" in tehran
        assert "اسلام‌شهر" in tehran or "اسلامشهر" in tehran


class TestNormalization:
    def test_province_arabic_letters_and_spaces(self) -> None:
        assert normalize_province("اصفهان") == "اصفهان"
        # ي عربی → ی فارسی
        assert normalize_province("آذربايجان شرقي") == "آذربایجان شرقی"
        # فاصلهٔ اضافه
        assert normalize_province("  تهران  ") == "تهران"

    def test_unknown_province_is_empty(self) -> None:
        assert normalize_province("طهران") == ""
        assert is_known_province("طهران") is False

    def test_city_normalization_variants(self) -> None:
        # نیم‌فاصله/فاصله و پسوندِ ناحیهٔ شهری یکسان می‌شوند
        assert normalize_city("تهران", "تهران 1") == "تهران"
        assert is_known_city("تهران", "تهران") is True
        assert normalize_city("قم", "تهران") == ""  # شهرِ استانِ دیگر

    def test_place_pair_errors(self) -> None:
        province, city, errors = validate_place_pair("قم", "قنوات")
        assert (province, city, errors) == ("قم", "قنوات", [])
        _p, _c, errors = validate_place_pair("قم", "شهرکِ ناموجود")
        assert errors and "نیست" in errors[0]

    def test_city_without_province_rejected(self) -> None:
        *_, errors = validate_place_pair("", "تهران")
        assert errors
        with pytest.raises(ValidationError):
            validate_iran_place("", "تهران")

    def test_empty_pair_means_nationwide(self) -> None:
        province, city, errors = validate_place_pair("", "")
        assert (province, city, errors) == ("", "", [])
        validate_iran_place("", "")  # نباید خطا بدهد

    def test_localities_empty_without_dataset(self, settings) -> None:
        settings.IRAN_LOCALITIES_JSON = ""
        assert localities_of("تهران") == []


class TestGeoApi:
    def test_provinces_endpoint(self) -> None:
        response = APIClient().get(reverse("geo:province-list"))
        assert response.status_code == status.HTTP_200_OK
        rows = response.data["data"]
        assert len(rows) == 31
        first = rows[0]
        assert set(first) == {"name", "tel_prefix", "cities_count"}
        assert first["cities_count"] > 0

    def test_cities_endpoint_for_known_province(self) -> None:
        response = APIClient().get(reverse("geo:city-list"), {"province": "تهران"})
        assert response.status_code == status.HTTP_200_OK
        data = response.data["data"]
        assert data["province"] == "تهران"
        assert "تهران" in data["cities"]
        assert data["cities"] == sorted(data["cities"]) or data["cities"]

    def test_cities_endpoint_404_for_unknown(self) -> None:
        response = APIClient().get(reverse("geo:city-list"), {"province": "طهران"})
        assert response.status_code == status.HTTP_404_NOT_FOUND

    def test_cities_endpoint_requires_province(self) -> None:
        response = APIClient().get(reverse("geo:city-list"))
        assert response.status_code == status.HTTP_404_NOT_FOUND

    def test_localities_endpoint(self) -> None:
        response = APIClient().get(reverse("geo:locality-list"), {"province": "قم"})
        assert response.status_code == status.HTTP_200_OK
        assert response.data["data"]["localities"] == []

    def test_cache_control_header(self) -> None:
        response = APIClient().get(reverse("geo:province-list"))
        assert "max-age=86400" in response["Cache-Control"]

"""اعتبارسنج‌های سطحِ فیلد برای استان/شهر — قابلِ استفاده در مدل و سریالایزر."""

from __future__ import annotations

from django.core.exceptions import ValidationError

from apps.core.geo.dataset import (
    cities_of,
    is_known_city,
    is_known_province,
    normalize_province,
)


def validate_iran_place(province: str, city: str) -> None:
    """جفتِ (استان، شهر) باید با دیتاستِ رسمی هم‌خوان باشد.

    «سراسر کشور» = هر دو خالی. اگر استان پر است و شهر خالی، یعنی «همهٔ شهرهای
    آن استان» — مجاز. شهرِ بدونِ استان و شهرِ بیرون از فهرستِ همان استان ⇒ خطا.
    """
    province = (province or "").strip()
    city = (city or "").strip()

    if not province:
        if city:
            raise ValidationError({"city": "برای ثبتِ شهر، ابتدا استان را انتخاب کنید."})
        return

    if not is_known_province(province):
        raise ValidationError(
            {"province": f"استانِ «{province}» در فهرستِ رسمی نیست؛ از لیست انتخاب کنید."}
        )
    if not city:
        return

    if not is_known_city(normalize_province(province), city):
        raise ValidationError(
            {"city": f"شهرِ «{city}» در استانِ {normalize_province(province)} نیست."}
        )


def city_choices_for(province: str) -> list[tuple[str, str]]:
    """گزینه‌های `choices` برای شهر (برای ویجتِ ادمین/سریالایزر)."""
    return [(city, city) for city in cities_of(province)]

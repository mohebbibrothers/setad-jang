"""تست‌های سیاستِ رمزِ بومی (یافتهٔ P2-8 فاز 8).

لایه‌ها:
1. واحدِ خالصِ `BesatPasswordPolicyValidator` — هر پنج قرارداد + normalize.
2. wiring: کلاس در `AUTH_PASSWORD_VALIDATORS` ثبت باشد و از مسیرِ استانداردِ
   `validate_password()` اجرا شود (هر شش serializer رمز‌ساز پروژه همان مسیرند).
3. fixture-safe: رمزِ پیش‌فرضِ تست‌ها باید policy را پاس کند — اگر یک‌روز
   شکست، یعنی فیکسچرها با رمزِ ضعیف‌تر از policy ساخته شده‌اند، نه policy غلط.
"""

from __future__ import annotations

import pytest
from django.conf import settings as dj_settings
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError

from apps.authentication.password_policy import BesatPasswordPolicyValidator

pytestmark = pytest.mark.unit


@pytest.fixture(name="validator")
def validator_fixture() -> BesatPasswordPolicyValidator:
    """سازندهٔ policy بدون override."""
    return BesatPasswordPolicyValidator()


def _rejects(validator: BesatPasswordPolicyValidator, password: str) -> str:
    """validate را صدا می‌زند و code خطا را برمی‌گرداند (fail اگر پذیرفت)."""
    with pytest.raises(ValidationError) as excinfo:
        validator.validate(password)
    return excinfo.value.error_list[0].code


@pytest.mark.parametrize(
    ("password", "code"),
    [
        ("Short!A1", "password_too_short"),
        ("onlylowercaseandlong", "password_missing_char_classes"),
        ("1234567890", "password_missing_char_classes"),
        ("aaaa!A123456", "password_sequential"),
        ("Ali1366Xy!", "password_birth_year_pattern"),
        ("Besat@2024x!", "password_platform_token"),
        ("Setadjang!xq", "password_platform_token"),
        ("QwerTyui!9", "password_keyboard_row"),
        ("AsdfGhjk!9", "password_keyboard_row"),
        ("Password1234!", "password_sequential"),
        ("Khodahafez!", "password_common"),
        ("ILoveYou1369!", "password_birth_year_pattern"),
    ],
)
def test_rejects(validator: BesatPasswordPolicyValidator, password: str, code: str) -> None:
    """هر قرارداد باید با کدِ خودش رد کند (کد = قرارداد؛ پیام‌ها user-facing‌اند)."""
    assert _rejects(validator, password) == code


@pytest.mark.parametrize(
    "password",
    [
        "StrongPass!234",
        "Tr0ub4dor&3xyz",
        "Kolah!9farangi",  # بدونِ الگو، با کلاس‌های کامل
        "Zephyr!quilt27",
    ],
)
def test_accepts(validator: BesatPasswordPolicyValidator, password: str) -> None:
    """رمزهای واقعیِ قوی نباید رد شوند — سخت‌گیریِ بی‌مورد، churn می‌سازد."""
    validator.validate(password)


def test_persian_digits_and_noise_normalization(validator: BesatPasswordPolicyValidator) -> None:
    """«B e s a t!۱۳۶۶» باید مثلِ «besat1366» رد شود، نه فرار کند."""
    assert _rejects(validator, "B e s a t!۱۳۶۶") in {
        "password_platform_token",
        "password_birth_year_pattern",
    }


def test_empty_password_rejected(validator: BesatPasswordPolicyValidator) -> None:
    """رشتهٔ خالی — ورودیِ مستقیمِ API — باید صریح رد شود نه IndexError."""
    assert _rejects(validator, "") == "password_empty"


# ============================================================
# Wiring
# ============================================================


def test_validator_registered_in_settings() -> None:
    """بدونِ ثبت در AUTH_PASSWORD_VALIDATORS، همهٔ serializerها بی‌دفاع‌اند."""
    names = [entry["NAME"] for entry in dj_settings.AUTH_PASSWORD_VALIDATORS]
    assert "apps.authentication.password_policy.BesatPasswordPolicyValidator" in names
    # طولِ کفِ ۱۰ هم رویِ پیش‌فرضِ ۸ِ جانگو سوار شده باشد (یافتهٔ P2-8).
    minimum = next(e for e in dj_settings.AUTH_PASSWORD_VALIDATORS if "Minimum" in e["NAME"])
    assert minimum.get("OPTIONS", {}).get("min_length") == 10


def test_validate_password_path_enforces_policy() -> None:
    """مسیرِ استانداردِ جانگو (که serializerها می‌زنند) قطعاً policy را اجرا کند."""
    with pytest.raises(ValidationError):
        validate_password("Password1234!")
    validate_password("Kolah!9farangi")  # نباید raise کند


def test_default_test_password_satisfies_policy() -> None:
    """رمزِ پیش‌فرضِ فیکسچرها (StrongPass!234) باید policy را پاس کند؛

    اگر این تست شکست، معنی‌اش تغییرِ policy در یک کامیتِ بعدی است و فیکسچرها
    باید *به‌روز* شوند — نه این‌که policy شل شود.
    """
    validate_password("StrongPass!234")

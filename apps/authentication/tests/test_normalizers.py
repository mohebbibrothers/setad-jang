"""
Tests — apps.authentication.normalizers

این تست‌ها contract کامل لایه‌ی normalization را پوشش می‌دهند:
- happy paths برای phone (ایرانی و بین‌المللی)
- happy paths برای email
- detection شناسه
- defensive rejection برای ورودی‌های invalid یا attack-like
- normalize_identifier (helper ترکیبی)

اصول طراحی:
- pure functions → بدون نیاز به DB، بدون fixture
- پارامتری‌سازی شده با pytest.parametrize برای پوشش گسترده
- assertها semantic و واضح
"""

from __future__ import annotations

import pytest
from django.core.exceptions import ValidationError

from apps.authentication.normalizers import (
    detect_identifier_kind,
    normalize_email,
    normalize_identifier,
    normalize_phone,
)

# ============================================================
# detect_identifier_kind
# ============================================================


class TestDetectIdentifierKind:
    """تشخیص نوع identifier از روی شکل ورودی."""

    @pytest.mark.parametrize(
        "value",
        ["user@example.com", "a@b.io", "  user@domain.com  "],
    )
    def test_detects_email(self, value: str) -> None:
        assert detect_identifier_kind(value) == "email"

    @pytest.mark.parametrize(
        "value",
        [
            "09120000000",
            "9120000000",
            "+989120000000",
            "00989120000000",
            "+98 912 000 0000",
            "+1234567890",
        ],
    )
    def test_detects_phone(self, value: str) -> None:
        assert detect_identifier_kind(value) == "phone"

    @pytest.mark.parametrize(
        "value",
        ["", "   ", "abcde", "hello world"],
    )
    def test_rejects_unknown(self, value: str) -> None:
        with pytest.raises(ValidationError):
            detect_identifier_kind(value)


# ============================================================
# normalize_phone
# ============================================================


class TestNormalizePhone:
    """نرمالایز کردن شماره موبایل به فرمت E.164."""

    @pytest.mark.parametrize(
        "raw,expected",
        [
            ("09120000000", "+989120000000"),
            ("9120000000", "+989120000000"),
            ("989120000000", "+989120000000"),
            ("+989120000000", "+989120000000"),
            ("+98 912 000 0000", "+989120000000"),
            ("+98-912-000-0000", "+989120000000"),
            ("00989120000000", "+989120000000"),
            ("(0912) 000-0000", "+989120000000"),
        ],
    )
    def test_normalizes_iran_phones(self, raw: str, expected: str) -> None:
        assert normalize_phone(raw) == expected

    @pytest.mark.parametrize(
        "raw,expected",
        [
            ("+12025551234", "+12025551234"),  # US
            ("+442071838750", "+442071838750"),  # UK
        ],
    )
    def test_normalizes_international_phones(self, raw: str, expected: str) -> None:
        assert normalize_phone(raw) == expected

    @pytest.mark.parametrize(
        "raw",
        [
            "",
            "   ",
            "abc",
            "+",
            "+abc",
            "12345",  # خیلی کوتاه
            "0" * 30,  # خیلی طولانی
            "0099999999999999999",  # بیش از حد رقم بعد از 00
            "08120000000",  # 0 اولی + 8 (8120... که 8-prefix ندارد به‌جای 9)
            "0812000000",  # کمتر از 11 رقم محلی
        ],
    )
    def test_rejects_invalid_phones(self, raw: str) -> None:
        with pytest.raises(ValidationError):
            normalize_phone(raw)

    def test_rejects_non_string(self) -> None:
        with pytest.raises(ValidationError):
            normalize_phone(None)  # type: ignore[arg-type]


# ============================================================
# normalize_email
# ============================================================


class TestNormalizeEmail:
    """نرمالایز کردن ایمیل به فرمت canonical."""

    @pytest.mark.parametrize(
        "raw,expected",
        [
            ("user@example.com", "user@example.com"),
            ("USER@EXAMPLE.COM", "user@example.com"),
            ("  user@example.com  ", "user@example.com"),
            ("User.Name+tag@example.co.uk", "user.name+tag@example.co.uk"),
        ],
    )
    def test_normalizes_emails(self, raw: str, expected: str) -> None:
        assert normalize_email(raw) == expected

    @pytest.mark.parametrize(
        "raw",
        [
            "",
            "   ",
            "no-at-sign",
            "double@@at.com",
            "user@",
            "@example.com",
            "user@no-tld",
            "user @example.com",  # whitespace داخل ایمیل
            "a" * 300 + "@example.com",  # بیش از حد طولانی
        ],
    )
    def test_rejects_invalid_emails(self, raw: str) -> None:
        with pytest.raises(ValidationError):
            normalize_email(raw)

    def test_rejects_non_string(self) -> None:
        with pytest.raises(ValidationError):
            normalize_email(None)  # type: ignore[arg-type]


# ============================================================
# normalize_identifier (combined)
# ============================================================


class TestNormalizeIdentifier:
    """helper ترکیبی: detect + normalize."""

    def test_returns_email_kind_and_normalized(self) -> None:
        kind, value = normalize_identifier("USER@Example.COM")
        assert kind == "email"
        assert value == "user@example.com"

    def test_returns_phone_kind_and_normalized(self) -> None:
        kind, value = normalize_identifier("09120000000")
        assert kind == "phone"
        assert value == "+989120000000"

    @pytest.mark.parametrize(
        "raw",
        ["", "   ", "abcde", "user@@example.com", "08120000000"],
    )
    def test_rejects_unknown_or_invalid(self, raw: str) -> None:
        with pytest.raises(ValidationError):
            normalize_identifier(raw)

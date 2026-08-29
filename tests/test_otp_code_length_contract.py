"""رگرسیون P0 فاز ۷ — طول کدِ موتور OTP و اعتبارسنجی سریالایزرها باید یکی باشد.

چرا این فایل تنها «نگهبان» واقعیِ این قرارداد است:
    در فاز ۳، موتور به کد ۶ رقمی رفت ولی هر شش سریالایزر verify با
    `max_length=5` ثابت ماند — یعنی در production هر کدِ معتبر ۴۰۰
    می‌خورد، در حالی که تست‌های view (به‌خاطر monkey-patch روی تولید کد به
    رشتهٔ ۵ رقمی) سبز بودند. تست‌های این فایل هیچ patch روی تولید ندارند
    و مستقیماً سازگاریِ «مقدارِ زندهٔ تنظیم ↔ ورودیِ سریالایزر» را تثبیت
    می‌کنند؛ اگر روزی دوباره دو منبع‌حقیقت ساختید، این‌جا می‌میرید.
"""

from __future__ import annotations

import pytest

from apps.authentication import otp as otp_module, providers as provider_module
from apps.authentication.choices import OTPPurpose
from apps.authentication.models import PrimaryIdentifierKind
from apps.authentication.serializers import OTPLoginVerifySerializer

pytestmark = pytest.mark.django_db


def test_engine_generated_code_passes_serializer_validation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """کد تولیدشده با تنظیمات پیش‌فرض (۶ رقم) باید از سریالایزرِ v2 رد شود."""
    monkeypatch.setattr(provider_module, "send_text_email", lambda **kwargs: 1)

    result = otp_module.generate_and_send_otp(
        identifier_kind=PrimaryIdentifierKind.EMAIL,
        identifier_value="engine-lock@example.com",
        purpose=OTPPurpose.LOGIN,
    )
    # اگر این assert هم شکست، خودِ موتور بی‌صدا تغییر کرده و باید کل
    # قرارداد (این‌جا و OTPCodeField) هم‌زمان بازبینی شود.
    assert len(result.code_plain) == 6

    serializer = OTPLoginVerifySerializer(
        data={"identifier": "engine-lock@example.com", "code": result.code_plain}
    )
    assert serializer.is_valid(), serializer.errors


def test_wrong_length_codes_are_rejected() -> None:
    """هر طولی جز طولِ موتور نباید از اعتبارسنجی رد شود."""
    for bad_code in ("12", "12345", "1234567"):
        serializer = OTPLoginVerifySerializer(
            data={"identifier": "engine-lock@example.com", "code": bad_code}
        )
        assert not serializer.is_valid(), f"code={bad_code!r} نباید رد می‌شد"
        assert "code" in serializer.errors


def test_serializer_tracks_runtime_override_of_code_length(settings) -> None:
    """overrideِ زندهٔ AUTH_OTP_CODE_LENGTH باید همان لحظه در ورودی اثر کند.

    `OTPCodeField` عمداً در زمانِ اعتبارسنجی (نه import) می‌خواند؛ این تست
    همان پایداریِ قراردادِ otp.py را تا لایهٔ ورودی سرریز می‌کند.
    """
    settings.AUTH_OTP_CODE_LENGTH = 8
    serializer = OTPLoginVerifySerializer(data={"identifier": "a@b.com", "code": "12345678"})
    assert serializer.is_valid(), serializer.errors

    short = OTPLoginVerifySerializer(data={"identifier": "a@b.com", "code": "1234567"})
    assert not short.is_valid()
    assert "code" in short.errors

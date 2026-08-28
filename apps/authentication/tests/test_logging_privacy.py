"""
Authentication logging privacy tests.

این تست‌ها تضمین می‌کنند لاگ‌های احراز هویت برای incident response مفید بمانند
اما PII کامل مثل ایمیل و شماره موبایل را ذخیره نکنند.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest

from apps.authentication.choices import OTPPurpose
from apps.authentication.logging_utils import mask_identifier
from apps.authentication.models import PrimaryIdentifierKind
from apps.authentication.otp import generate_and_send_otp


class TestMaskIdentifier:
    """تست‌های helper مرکزی masking شناسه‌ها."""

    def test_masks_email_without_exposing_full_local_part(self) -> None:
        masked = mask_identifier("very.secret.user@example.com")

        assert masked == "ve***@ex***.com"
        assert "very.secret.user" not in masked

    def test_masks_phone_preserving_prefix_and_last_digits(self) -> None:
        masked = mask_identifier("+989120000000", identifier_kind=PrimaryIdentifierKind.PHONE)

        assert masked == "+989***00"
        assert "+989120000000" not in masked

    def test_masks_blank_and_none_values(self) -> None:
        assert mask_identifier(None) == "<none>"
        assert mask_identifier("   ") == "<blank>"

    def test_masks_generic_identifier(self) -> None:
        assert mask_identifier("abcdefghi") == "ab***hi"


@pytest.mark.django_db
class TestOTPLoggingPrivacy:
    """تست‌های privacy برای logهای OTP engine."""

    def test_generate_otp_logs_masked_identifier_not_plain_email(self) -> None:
        identifier = "sensitive.user@example.com"

        with (
            patch("apps.authentication.providers.EmailOTPProvider.send", return_value=True),
            patch("apps.authentication.otp.logger.info") as mock_logger_info,
        ):
            generate_and_send_otp(
                identifier_kind=PrimaryIdentifierKind.EMAIL,
                identifier_value=identifier,
                purpose=OTPPurpose.LOGIN,
            )

        flattened_log_args = " ".join(
            str(arg) for call in mock_logger_info.call_args_list for arg in call.args
        )
        assert identifier not in flattened_log_args
        assert "se***@ex***.com" in flattened_log_args

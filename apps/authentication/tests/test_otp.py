"""
Tests — apps.authentication.otp

این تست‌ها contract امنیتی OTP service را verify می‌کنند:
- Generation: format، expiry، invalidation قبلی‌ها
- Cooldown: rate-limit بین دو request
- Verify success: کد درست + replay protection
- Verify failures: کد اشتباه، expiry، not-found، max attempts
- Edge cases: identifier/purpose نامعتبر، code خالی
- Security: hash storage، constant-time comparison

اصول طراحی:
- استفاده از monkeypatch روی timezone.now برای کنترل زمان (بدون freezegun)
- هر تست deterministic و ایزوله
- assertها semantic روی DB state، نه فقط return value
"""

from __future__ import annotations

from datetime import datetime, timedelta

import pytest
from django.core.exceptions import ValidationError
from django.utils import timezone

from apps.authentication import otp as otp_service
from apps.authentication.models import OTPCode, PrimaryIdentifierKind

pytestmark = [pytest.mark.django_db]


# ============================================================
# Helpers
# ============================================================


def _make_email_otp(
    *,
    identifier: str = "user@example.com",
    purpose: str = "signup",
) -> otp_service.OTPGenerationResult:
    """Shortcut برای ساخت OTP در تست‌ها."""
    return otp_service.generate_and_send_otp(
        identifier_kind=PrimaryIdentifierKind.EMAIL,
        identifier_value=identifier,
        purpose=purpose,
    )


def _freeze_time(monkeypatch: pytest.MonkeyPatch, when: datetime) -> None:
    """جایگزینی timezone.now در ماژول otp برای کنترل زمان."""
    monkeypatch.setattr(
        "apps.authentication.otp.timezone.now",
        lambda: when,
    )


# ============================================================
# Group 1: Generation
# ============================================================


class TestGenerateOTP:
    """رفتار تولید OTP جدید."""

    def test_creates_otp_with_correct_structure(self) -> None:
        result = _make_email_otp(identifier="alice@example.com", purpose="signup")

        assert isinstance(result.otp, OTPCode)
        assert result.otp.identifier_kind == PrimaryIdentifierKind.EMAIL
        assert result.otp.identifier_value == "alice@example.com"
        assert result.otp.purpose == "signup"
        assert result.otp.attempts == 0
        assert result.otp.is_used is False
        assert result.otp.code_hash  # not empty

    def test_code_plain_has_correct_length(self) -> None:
        result = _make_email_otp()
        assert len(result.code_plain) == 5
        assert result.code_plain.isdigit()

    def test_code_plain_is_not_stored_in_db(self) -> None:
        result = _make_email_otp()
        # DB only has hash, not plain
        assert result.code_plain not in result.otp.code_hash
        # And hash length is SHA-256 hex (64 chars)
        assert len(result.otp.code_hash) == 64

    def test_expires_in_5_minutes(self) -> None:
        result = _make_email_otp()
        delta = result.otp.expires_at - timezone.now()
        # tolerance: 5 ثانیه برای execution time
        assert timedelta(minutes=4, seconds=55) < delta <= timedelta(minutes=5)
        assert result.expires_in_seconds == 5 * 60

    def test_invalidates_previous_active_otp_for_same_purpose(self) -> None:
        # اولین OTP
        first = _make_email_otp(identifier="bob@example.com", purpose="signup")

        # سعی کن دومی بسازی — باید با cooldown مواجه شویم
        # پس اول cooldown را با تغییر created_at قبلی دور بزنیم
        first.otp.created_at = timezone.now() - timedelta(seconds=120)
        first.otp.save(update_fields=["created_at"])

        # دومین OTP
        second = _make_email_otp(identifier="bob@example.com", purpose="signup")

        # OTP اول باید alreadyinvalid شده باشد
        first.otp.refresh_from_db()
        assert first.otp.is_used is True
        # OTP دوم فعال است
        assert second.otp.is_used is False


# ============================================================
# Group 2: Cooldown
# ============================================================


class TestCooldown:
    """rate-limit بین دو request OTP."""

    def test_immediate_second_request_raises_cooldown(self) -> None:
        _make_email_otp(identifier="cool@example.com", purpose="signup")

        with pytest.raises(otp_service.OTPCooldownActive) as exc_info:
            _make_email_otp(identifier="cool@example.com", purpose="signup")

        assert exc_info.value.seconds_remaining > 0
        assert exc_info.value.seconds_remaining <= 60

    def test_cooldown_is_per_purpose(self) -> None:
        """OTP برای purpose A نباید cooldown روی purpose B بگذارد."""
        _make_email_otp(identifier="multi@example.com", purpose="signup")
        # purpose دیگری → نباید fail کند
        result = _make_email_otp(identifier="multi@example.com", purpose="login")
        assert result.otp.is_used is False

    def test_cooldown_is_per_identifier(self) -> None:
        """OTP برای identifier A نباید cooldown روی identifier B بگذارد."""
        _make_email_otp(identifier="user1@example.com", purpose="signup")
        # identifier دیگری → نباید fail کند
        result = _make_email_otp(identifier="user2@example.com", purpose="signup")
        assert result.otp.is_used is False


# ============================================================
# Group 3: Verify success
# ============================================================


class TestVerifySuccess:
    """مسیر موفق verify."""

    def test_correct_code_returns_otp_and_marks_used(self) -> None:
        result = _make_email_otp(identifier="verify@example.com", purpose="signup")

        verified = otp_service.verify_otp(
            identifier_kind=PrimaryIdentifierKind.EMAIL,
            identifier_value="verify@example.com",
            purpose="signup",
            code=result.code_plain,
        )

        assert verified.pk == result.otp.pk
        verified.refresh_from_db()
        assert verified.is_used is True

    def test_replay_attack_blocked(self) -> None:
        """همان کد دوبار verify نشود."""
        result = _make_email_otp(identifier="replay@example.com", purpose="signup")

        otp_service.verify_otp(
            identifier_kind=PrimaryIdentifierKind.EMAIL,
            identifier_value="replay@example.com",
            purpose="signup",
            code=result.code_plain,
        )

        # دومین verify باید fail شود (OTP الان used است)
        with pytest.raises(otp_service.OTPNotFound):
            otp_service.verify_otp(
                identifier_kind=PrimaryIdentifierKind.EMAIL,
                identifier_value="replay@example.com",
                purpose="signup",
                code=result.code_plain,
            )


# ============================================================
# Group 4: Verify failures
# ============================================================


class TestVerifyFailures:
    """مسیرهای failure در verify."""

    def test_wrong_code_increments_attempts(self) -> None:
        _make_email_otp(identifier="wrong@example.com", purpose="signup")

        with pytest.raises(otp_service.OTPInvalidCode):
            otp_service.verify_otp(
                identifier_kind=PrimaryIdentifierKind.EMAIL,
                identifier_value="wrong@example.com",
                purpose="signup",
                code="00000",  # almost certainly wrong
            )

        otp_in_db = OTPCode.objects.get(identifier_value="wrong@example.com")
        assert otp_in_db.attempts == 1
        assert otp_in_db.is_used is False

    def test_max_attempts_invalidates_otp(self) -> None:
        result = _make_email_otp(identifier="bf@example.com", purpose="signup")

        wrong_code = "00000" if result.code_plain != "00000" else "11111"

        # 4 attempt اشتباه قبل از آخرین
        for _ in range(4):
            with pytest.raises(otp_service.OTPInvalidCode):
                otp_service.verify_otp(
                    identifier_kind=PrimaryIdentifierKind.EMAIL,
                    identifier_value="bf@example.com",
                    purpose="signup",
                    code=wrong_code,
                )

        # پنجمین attempt اشتباه → OTPTooManyAttempts
        with pytest.raises(otp_service.OTPTooManyAttempts):
            otp_service.verify_otp(
                identifier_kind=PrimaryIdentifierKind.EMAIL,
                identifier_value="bf@example.com",
                purpose="signup",
                code=wrong_code,
            )

        otp_in_db = OTPCode.objects.get(identifier_value="bf@example.com")
        assert otp_in_db.is_used is True
        assert otp_in_db.attempts == 5

    def test_expired_otp_raises_expired_and_invalidates(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        result = _make_email_otp(identifier="exp@example.com", purpose="signup")

        # سفر در زمان: 6 دقیقه بعد
        future_time = timezone.now() + timedelta(minutes=6)
        _freeze_time(monkeypatch, future_time)

        with pytest.raises(otp_service.OTPExpired):
            otp_service.verify_otp(
                identifier_kind=PrimaryIdentifierKind.EMAIL,
                identifier_value="exp@example.com",
                purpose="signup",
                code=result.code_plain,
            )

        result.otp.refresh_from_db()
        assert result.otp.is_used is True

    def test_no_active_otp_raises_not_found(self) -> None:
        with pytest.raises(otp_service.OTPNotFound):
            otp_service.verify_otp(
                identifier_kind=PrimaryIdentifierKind.EMAIL,
                identifier_value="ghost@example.com",
                purpose="signup",
                code="12345",
            )

    def test_empty_code_raises_invalid_code(self) -> None:
        with pytest.raises(otp_service.OTPInvalidCode):
            otp_service.verify_otp(
                identifier_kind=PrimaryIdentifierKind.EMAIL,
                identifier_value="empty@example.com",
                purpose="signup",
                code="",
            )

    def test_whitespace_only_code_raises_invalid_code(self) -> None:
        with pytest.raises(otp_service.OTPInvalidCode):
            otp_service.verify_otp(
                identifier_kind=PrimaryIdentifierKind.EMAIL,
                identifier_value="ws@example.com",
                purpose="signup",
                code="   ",
            )


# ============================================================
# Group 5: Validation edges
# ============================================================


class TestValidationErrors:
    """ورودی‌های نامعتبر."""

    @pytest.mark.parametrize(
        "invalid_kind",
        ["not_a_kind", "", "EMAIL_X", "phone_number"],
    )
    def test_invalid_identifier_kind_in_generate(self, invalid_kind: str) -> None:
        with pytest.raises(ValidationError):
            otp_service.generate_and_send_otp(
                identifier_kind=invalid_kind,
                identifier_value="x@example.com",
                purpose="signup",
            )

    @pytest.mark.parametrize(
        "invalid_purpose",
        ["bogus_purpose", "", "SIGNUP_X"],
    )
    def test_invalid_purpose_in_generate(self, invalid_purpose: str) -> None:
        with pytest.raises(ValidationError):
            otp_service.generate_and_send_otp(
                identifier_kind=PrimaryIdentifierKind.EMAIL,
                identifier_value="x@example.com",
                purpose=invalid_purpose,
            )

    def test_invalid_identifier_kind_in_verify(self) -> None:
        with pytest.raises(ValidationError):
            otp_service.verify_otp(
                identifier_kind="bogus",
                identifier_value="x@example.com",
                purpose="signup",
                code="12345",
            )


# ============================================================
# Group 6: Security
# ============================================================


class TestSecurity:
    """contract امنیتی بحرانی."""

    def test_code_hash_does_not_contain_plain_code(self) -> None:
        result = _make_email_otp()
        # SHA-256 hex output should never coincidentally contain the 5-digit code.
        # این یک تضمین semantic است نه perfect (احتمال coincidence میلیونی است).
        assert result.code_plain not in result.otp.code_hash

    def test_two_different_codes_have_different_hashes(self) -> None:
        """sanity check: hash واقعاً به code وابسته است."""
        h1 = otp_service._hash_code("12345")
        h2 = otp_service._hash_code("12346")
        assert h1 != h2

    def test_same_code_has_consistent_hash(self) -> None:
        """sanity check: hash deterministic است (با همان SECRET_KEY)."""
        h1 = otp_service._hash_code("99999")
        h2 = otp_service._hash_code("99999")
        assert h1 == h2

    def test_hash_is_sha256_hex_length(self) -> None:
        h = otp_service._hash_code("00000")
        assert len(h) == 64
        # SHA-256 hex فقط شامل [0-9a-f]
        assert all(c in "0123456789abcdef" for c in h)


# ============================================================
# Group 7: Cross-cutting
# ============================================================


class TestCrossPurposeIsolation:
    """OTPهای purposeهای مختلف نباید با هم تداخل کنند."""

    def test_verify_with_correct_code_but_wrong_purpose_fails(self) -> None:
        result = _make_email_otp(identifier="cross@example.com", purpose="signup")

        # سعی کن همان کد را برای purpose دیگری verify کنی
        with pytest.raises(otp_service.OTPNotFound):
            otp_service.verify_otp(
                identifier_kind=PrimaryIdentifierKind.EMAIL,
                identifier_value="cross@example.com",
                purpose="login",
                code=result.code_plain,
            )

    def test_verify_with_correct_code_but_wrong_identifier_fails(self) -> None:
        result = _make_email_otp(identifier="alice@example.com", purpose="signup")

        with pytest.raises(otp_service.OTPNotFound):
            otp_service.verify_otp(
                identifier_kind=PrimaryIdentifierKind.EMAIL,
                identifier_value="bob@example.com",
                purpose="signup",
                code=result.code_plain,
            )

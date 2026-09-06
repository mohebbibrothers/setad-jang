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
        """طول کد از settings خوانده می‌شود و پیش‌فرضش ۶ رقم است (نه ۵)."""
        result = _make_email_otp()
        assert len(result.code_plain) == 6
        assert result.code_plain.isdigit()

    def test_code_length_is_configurable_from_settings(self, settings) -> None:
        """ثابت‌های OTP باید در زمان فراخوانی خوانده شوند، نه زمان import."""
        settings.AUTH_OTP_CODE_LENGTH = 8
        result = _make_email_otp(identifier="len8@example.com")
        assert len(result.code_plain) == 8

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

        # سعی کن دومی بسازی — باید با cooldown مواجه شویم.
        # cooldown حالا دو سد دارد: رزرو اتمیک در کش و بررسی دیتابیس.
        # پس عقب‌بردن created_at به‌تنهایی کافی نیست و باید رزرو کش هم
        # آزاد شود. همین که این تست بدون خط زیر رد می‌شود، خودش نشان
        # می‌دهد سد جدید واقعاً فعال است.
        first.otp.created_at = timezone.now() - timedelta(seconds=120)
        first.otp.save(update_fields=["created_at"])
        otp_service._release_cooldown_slot(
            identifier_kind="email",
            identifier_value="bob@example.com",
            purpose="signup",
        )

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

    def test_concurrent_success_replay_loses_conditional_update(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """اگر request دیگری بین read و mark استفاده کرده باشد، verify موفق نشود."""
        result = _make_email_otp(identifier="race@example.com", purpose="signup")

        monkeypatch.setattr("apps.authentication.otp._mark_otp_used", lambda otp: False)

        with pytest.raises(otp_service.OTPNotFound):
            otp_service.verify_otp(
                identifier_kind=PrimaryIdentifierKind.EMAIL,
                identifier_value="race@example.com",
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
        context = {
            "salt": "a" * 32,
            "identifier_kind": "email",
            "identifier_value": "x@example.com",
            "purpose": "signup",
        }
        assert otp_service._hash_code("123456", **context) != otp_service._hash_code(
            "123457", **context
        )

    def test_hash_is_deterministic_for_the_same_record(self) -> None:
        """با نمک و کانتکست یکسان، هش باید بازتولیدپذیر باشد — وگرنه verify کار نمی‌کند."""
        context = {
            "salt": "b" * 32,
            "identifier_kind": "email",
            "identifier_value": "y@example.com",
            "purpose": "signup",
        }
        assert otp_service._hash_code("999999", **context) == otp_service._hash_code(
            "999999", **context
        )

    def test_same_code_hashes_differently_across_records(self) -> None:
        """هستهٔ یافتهٔ ۵.۳: کد یکسان نباید در دو رکورد هش یکسان بدهد."""
        base = {
            "identifier_kind": "email",
            "identifier_value": "z@example.com",
            "purpose": "signup",
        }
        first = otp_service._hash_code("424242", salt=otp_service._generate_salt(), **base)
        second = otp_service._hash_code("424242", salt=otp_service._generate_salt(), **base)
        assert first != second, "نمک اختصاصی هر رکورد باید هش‌ها را از هم جدا کند"

    def test_hash_is_bound_to_purpose(self) -> None:
        """هش یک کد برای یک purpose نباید در purpose دیگری معتبر باشد."""
        base = {
            "salt": "c" * 32,
            "identifier_kind": "email",
            "identifier_value": "w@example.com",
        }
        assert otp_service._hash_code("555555", purpose="signup", **base) != otp_service._hash_code(
            "555555", purpose="login", **base
        )

    def test_hash_is_sha256_hex_length(self) -> None:
        h = otp_service._hash_code(
            "000000",
            salt="d" * 32,
            identifier_kind="email",
            identifier_value="v@example.com",
            purpose="signup",
        )
        assert len(h) == 64
        # SHA-256 hex فقط شامل [0-9a-f]
        assert all(c in "0123456789abcdef" for c in h)

    def test_every_generated_otp_gets_a_unique_salt(self) -> None:
        """نمک باید واقعاً per-record باشد، نه یک مقدار ثابت مشترک."""
        first = _make_email_otp(identifier="s1@example.com")
        second = _make_email_otp(identifier="s2@example.com")
        assert first.otp.code_salt
        assert len(first.otp.code_salt) == 32
        assert first.otp.code_salt != second.otp.code_salt


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


# ============================================================
# Secondary SMS fan-out (email login/reset -> account phone)
# ============================================================


class _RecordingProvider:
    """provider ساختگی که کانال‌ها را برای assert ضبط می‌کند."""

    def __init__(self, channel: str, calls: list[tuple[str, str, str]], *, fail: bool = False):
        self.channel = channel
        self._calls = calls
        self._fail = fail

    def send(self, recipient: str, code: str, purpose: str) -> bool:
        if self._fail:
            from apps.authentication.providers import OTPDeliveryFailedError

            raise OTPDeliveryFailedError("simulated vendor outage")
        self._calls.append((self.channel, recipient, purpose))
        return True


def _patch_fanout_providers(
    monkeypatch: pytest.MonkeyPatch,
    calls: list[tuple[str, str, str]],
    *,
    phone_fail: bool = False,
) -> None:
    """get_otp_provider را با fake ضبط‌کننده جایگزین می‌کند."""

    def fake_get_otp_provider(channel: str | None = None):
        assert channel is not None
        fail = phone_fail and channel == PrimaryIdentifierKind.PHONE
        return _RecordingProvider(channel, calls, fail=fail)

    monkeypatch.setattr(otp_service, "get_otp_provider", fake_get_otp_provider)


class TestSecondarySmsFanout:
    """fan-out ثانویه پیامکی فقط برای login/reset ایمیلی و با provider فعال."""

    @staticmethod
    def _user_with_phone():
        from django.contrib.auth import get_user_model

        return get_user_model().all_objects.create(
            email="fanout@example.com",
            phone_number="+989121234567",
            primary_identifier=PrimaryIdentifierKind.EMAIL,
            is_active=True,
        )

    def _run(self, *, settings, monkeypatch, purpose: str, phone: str):
        self._user_with_phone()
        settings.OTP_SMS_PROVIDER = "iranpayamak"
        if not phone:
            from django.contrib.auth import get_user_model

            get_user_model().all_objects.update(phone_number="")
        calls: list[tuple[str, str, str]] = []
        _patch_fanout_providers(monkeypatch, calls)
        result = otp_service.generate_and_send_otp(
            identifier_kind=PrimaryIdentifierKind.EMAIL,
            identifier_value="fanout@example.com",
            purpose=purpose,
        )
        return result, calls

    def test_email_login_also_sends_to_account_phone(self, settings, monkeypatch):
        result, calls = self._run(
            settings=settings, monkeypatch=monkeypatch, purpose="login", phone="+989121234567"
        )

        assert calls == [
            ("email", "fanout@example.com", "login"),
            ("phone", "+989121234567", "login"),
        ]
        result.otp.refresh_from_db()
        assert result.otp.is_used is False

    def test_password_reset_also_fans_out(self, settings, monkeypatch):
        _result, calls = self._run(
            settings=settings,
            monkeypatch=monkeypatch,
            purpose="password_reset",
            phone="+989121234567",
        )
        assert [c[0] for c in calls] == ["email", "phone"]

    def test_signup_does_not_fan_out(self, settings, monkeypatch):
        _result, calls = self._run(
            settings=settings, monkeypatch=monkeypatch, purpose="signup", phone="+989121234567"
        )
        assert [c[0] for c in calls] == ["email"]

    def test_console_provider_disables_fanout(self, settings, monkeypatch):
        settings.OTP_SMS_PROVIDER = "console"
        calls: list[tuple[str, str, str]] = []
        _patch_fanout_providers(monkeypatch, calls)
        self._user_with_phone()

        otp_service.generate_and_send_otp(
            identifier_kind=PrimaryIdentifierKind.EMAIL,
            identifier_value="fanout@example.com",
            purpose="login",
        )
        assert [c[0] for c in calls] == ["email"]

    def test_missing_phone_skips_silently(self, settings, monkeypatch):
        _result, calls = self._run(
            settings=settings, monkeypatch=monkeypatch, purpose="login", phone=""
        )
        assert [c[0] for c in calls] == ["email"]

    def test_fanout_failure_keeps_primary_otp_valid(self, settings, monkeypatch):
        self._user_with_phone()
        settings.OTP_SMS_PROVIDER = "iranpayamak"
        calls: list[tuple[str, str, str]] = []
        _patch_fanout_providers(monkeypatch, calls, phone_fail=True)

        result = otp_service.generate_and_send_otp(
            identifier_kind=PrimaryIdentifierKind.EMAIL,
            identifier_value="fanout@example.com",
            purpose="login",
        )
        # کانال primary موفق بوده → OTP اعتبار دارد و cooldown آزاد نشده.
        result.otp.refresh_from_db()
        assert result.otp.is_used is False
        verified = otp_service.verify_otp(
            identifier_kind=PrimaryIdentifierKind.EMAIL,
            identifier_value="fanout@example.com",
            purpose="login",
            code=result.code_plain,
        )
        assert verified.pk == result.otp.pk

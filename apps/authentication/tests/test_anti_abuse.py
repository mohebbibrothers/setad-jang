"""
Tests — apps.authentication.anti_abuse

این تست‌ها contract ماژول anti_abuse را پوشش می‌دهند:

- Honeypot detection:
  - payload غیر dict باید benign باشد
  - نبودن field باید benign باشد
  - empty / whitespace-only string باید benign باشد
  - non-empty string باید suspicious باشد
  - non-string value باید suspicious باشد

- Global OTP guard:
  - counter باید تا قبل از عبور از threshold tripped نشود
  - guard فقط وقتی tripped می‌شود که counter > threshold شود
  - reset باید counter را پاک کند
  - مسیر race-condition در cache.incr (ValueError) باید safe باشد
  - در صورت failure cache backend باید fail-open رفتار کند و warning log بدهد

نکته:
behavior فعلی honeypot، whitespace-only را benign در نظر می‌گیرد.
تست‌ها عمداً runtime behavior فعلی را lock می‌کنند.
"""

from __future__ import annotations

from typing import Any

import pytest

from apps.authentication import anti_abuse


class _ValueErrorOnIncrCache:
    """شبیه‌ساز cache که روی incr خطای ValueError می‌دهد."""

    def __init__(self) -> None:
        self.set_calls: list[tuple[str, int, int | None]] = []

    def get(self, key: str) -> int:
        return 7

    def set(self, key: str, value: int, timeout: int | None = None) -> None:
        self.set_calls.append((key, value, timeout))

    def incr(self, key: str) -> int:
        raise ValueError("key expired between get and incr")

    def delete(self, key: str) -> None:
        return None


class _ExplodingCache:
    """شبیه‌ساز cache که از همان ابتدا fail می‌شود."""

    def get(self, key: str) -> None:
        raise RuntimeError("redis down")


# ============================================================
# Honeypot
# ============================================================


class TestIsHoneypotTriggered:
    """پوشش edge caseهای helper مربوط به honeypot."""

    @pytest.mark.parametrize(
        "payload",
        [
            None,
            "not-a-dict",
            [],
            ("a", "b"),
            object(),
        ],
    )
    def test_returns_false_for_non_dict_payloads(self, payload: Any) -> None:
        assert anti_abuse.is_honeypot_triggered(payload) is False

    def test_returns_false_when_honeypot_field_is_missing(self) -> None:
        payload = {
            "email": "user@example.com",
            "password": "StrongPass!234",
        }

        assert anti_abuse.is_honeypot_triggered(payload) is False

    @pytest.mark.parametrize(
        "value",
        [
            "",
            "   ",
            "\n\t  ",
        ],
    )
    def test_returns_false_for_empty_or_whitespace_only_string(
        self,
        value: str,
    ) -> None:
        payload = {
            anti_abuse.HONEYPOT_FIELD_NAME: value,
        }

        assert anti_abuse.is_honeypot_triggered(payload) is False

    @pytest.mark.parametrize(
        "value",
        [
            "bot",
            "  bot  ",
            "https://spam.example",
        ],
    )
    def test_returns_true_for_non_empty_string(self, value: str) -> None:
        payload = {
            anti_abuse.HONEYPOT_FIELD_NAME: value,
        }

        assert anti_abuse.is_honeypot_triggered(payload) is True

    @pytest.mark.parametrize(
        "value",
        [
            0,
            True,
            {"nested": "value"},
            ["spam"],
        ],
    )
    def test_returns_true_for_non_string_values(self, value: Any) -> None:
        payload = {
            anti_abuse.HONEYPOT_FIELD_NAME: value,
        }

        assert anti_abuse.is_honeypot_triggered(payload) is True


# ============================================================
# Global OTP Guard
# ============================================================


class TestGlobalOtpGuard:
    """پوشش contract مربوط به global anomaly counter."""

    def test_trips_only_after_threshold_is_exceeded(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        warning_messages: list[str] = []

        def fake_warning(message: str, *args: object) -> None:
            warning_messages.append(message % args if args else message)

        monkeypatch.setattr(anti_abuse, "_GLOBAL_OTP_GUARD_THRESHOLD", 2)
        monkeypatch.setattr(anti_abuse, "_GLOBAL_OTP_GUARD_WINDOW_SECONDS", 60)
        monkeypatch.setattr(anti_abuse.logger, "warning", fake_warning)

        anti_abuse.reset_global_otp_guard()

        assert anti_abuse.is_global_otp_guard_tripped() is False
        assert anti_abuse.is_global_otp_guard_tripped() is False
        assert anti_abuse.is_global_otp_guard_tripped() is True

        assert len(warning_messages) == 1
        assert "Global OTP guard TRIPPED" in warning_messages[0]

    def test_reset_global_otp_guard_clears_counter(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.setattr(anti_abuse, "_GLOBAL_OTP_GUARD_THRESHOLD", 1)
        monkeypatch.setattr(anti_abuse, "_GLOBAL_OTP_GUARD_WINDOW_SECONDS", 60)

        anti_abuse.reset_global_otp_guard()

        assert anti_abuse.is_global_otp_guard_tripped() is False
        assert anti_abuse.is_global_otp_guard_tripped() is True

        anti_abuse.reset_global_otp_guard()

        assert anti_abuse.is_global_otp_guard_tripped() is False

    def test_recovers_safely_when_cache_incr_raises_value_error(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        fake_cache = _ValueErrorOnIncrCache()

        monkeypatch.setattr(anti_abuse, "cache", fake_cache)
        monkeypatch.setattr(anti_abuse, "_GLOBAL_OTP_GUARD_THRESHOLD", 100)
        monkeypatch.setattr(anti_abuse, "_GLOBAL_OTP_GUARD_WINDOW_SECONDS", 60)

        result = anti_abuse.is_global_otp_guard_tripped()

        assert result is False
        assert fake_cache.set_calls == [
            (
                anti_abuse._GLOBAL_OTP_GUARD_CACHE_KEY,
                1,
                60,
            ),
        ]

    def test_fails_open_and_logs_warning_when_cache_backend_fails(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        warning_messages: list[str] = []

        def fake_warning(message: str, *args: object) -> None:
            warning_messages.append(message % args if args else message)

        monkeypatch.setattr(anti_abuse, "cache", _ExplodingCache())
        monkeypatch.setattr(anti_abuse.logger, "warning", fake_warning)

        result = anti_abuse.is_global_otp_guard_tripped()

        assert result is False
        assert len(warning_messages) == 1
        assert "Global OTP guard check failed (fail-open)" in warning_messages[0]
        assert "redis down" in warning_messages[0]

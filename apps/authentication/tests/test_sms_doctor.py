"""تست‌های commandِ sms_doctor — چکاپِ خودکارِ «چرا پیامک نمی‌رسد؟».

هیچ شبکه‌ای زده نمی‌شود؛ مسیرِ ارسال با monkeypatch روی requests.postِ همان
ماژولِ iranpayamak (قراردادِ تست‌های provider) ساختگی می‌شود.
"""

from __future__ import annotations

from io import StringIO

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError


class _FakeResponse:
    def __init__(self, *, status_code: int = 201, payload: dict | None = None) -> None:
        self.status_code = status_code
        self._payload = payload if payload is not None else {"status": "success", "data": 0}
        self.text = str(self._payload)

    def json(self) -> dict:
        return self._payload


def _configure(settings, *, provider: str = "iranpayamak") -> None:
    settings.DEBUG = False
    settings.OTP_PROVIDER = "sms"
    settings.OTP_SMS_PROVIDER = provider
    settings.NOTIFICATIONS_SMS_ENABLED = False
    settings.SMS_IRANPAYAMAK_API_KEY = "k" * 24
    settings.SMS_IRANPAYAMAK_LINE_NUMBER = "50002178584000"
    settings.SMS_IRANPAYAMAK_NUMBER_FORMAT = "persian"
    settings.SMS_IRANPAYAMAK_PATTERN_URL = "https://api.iranpayamak.com/ws/v1/sms/pattern"
    settings.SMS_IRANPAYAMAK_TIMEOUT_SECONDS = 5
    settings.SMS_IRANPAYAMAK_PATTERN_LOGIN = "P-LOGIN"
    settings.SMS_IRANPAYAMAK_PATTERN_SIGNUP = "P-SIGNUP"
    settings.SMS_IRANPAYAMAK_PATTERN_PASSWORD_RESET = "P-RESET"
    settings.SMS_IRANPAYAMAK_PATTERN_IDENTIFIER_ADD = ""
    settings.SMS_IRANPAYAMAK_PATTERN_NOTIFICATION = ""


class TestConfigLayer:
    """لایهٔ ۱ و ۲: قراردادِ تنظیمات + آمادگیِ درگاه."""

    def test_console_backend_in_production_is_fatal(self, settings) -> None:
        """ریشهٔ شایعِ «همهٔ پیامک‌ها مرده»: OTP_SMS_PROVIDER تنظیم‌نشده = console."""
        _configure(settings, provider="console")
        with pytest.raises(CommandError, match="OTP_SMS_PROVIDER='console'"):
            call_command("sms_doctor", stdout=StringIO(), stderr=StringIO())

    def test_ready_config_exits_clean(self, settings) -> None:
        _configure(settings)
        out = StringIO()
        call_command("sms_doctor", stdout=out)
        text = out.getvalue()
        assert "ready=True" in text
        assert "همهٔ لایه‌های SMS سالم‌اند" in text
        assert "set (24 chars)" in text
        assert "k" * 24 not in text  # کلیدِ خام هرگز چاپ نمی‌شود

    def test_missing_login_pattern_reported(self, settings) -> None:
        _configure(settings)
        settings.SMS_IRANPAYAMAK_PATTERN_LOGIN = ""
        with pytest.raises(CommandError, match="readiness"):
            call_command("sms_doctor", stdout=StringIO(), stderr=StringIO())

    def test_notification_channel_makes_notification_pattern_mandatory(self, settings) -> None:
        """کانالِ نوتیفیکیشن روشن + الگویِ نبودِش = همان «مرگِ بی‌صدا» — باید فریاد بزند."""
        _configure(settings)
        settings.NOTIFICATIONS_SMS_ENABLED = True
        with pytest.raises(CommandError, match="SMS_IRANPAYAMAK_PATTERN_NOTIFICATION"):
            call_command("sms_doctor", stdout=StringIO(), stderr=StringIO())

        settings.SMS_IRANPAYAMAK_PATTERN_NOTIFICATION = "P-NOTIF"
        out = StringIO()
        call_command("sms_doctor", stdout=out)
        assert "ready=True" in out.getvalue()


class TestLiveSendLayer:
    """لایهٔ ۳: --to با پاسخِ خامِ درگاه."""

    def test_live_send_success(self, settings, monkeypatch) -> None:
        _configure(settings)
        monkeypatch.setattr(
            "apps.authentication.iranpayamak.requests.post",
            lambda url, *, json, headers, timeout: _FakeResponse(),
        )
        out = StringIO()
        call_command("sms_doctor", "--to", "09121234567", stdout=out)
        assert "تحویلِ درگاه شد" in out.getvalue()

    def test_live_send_shows_vendor_detail_from_logs(self, settings, monkeypatch) -> None:
        _configure(settings)

        def fake_post(url, *, json, headers, timeout):
            return _FakeResponse(
                status_code=400,
                payload={"status": "error", "messages": "کد الگو نامعتبر است."},
            )

        monkeypatch.setattr("apps.authentication.iranpayamak.requests.post", fake_post)
        with pytest.raises(CommandError, match="شکست خورد") as excinfo:
            call_command("sms_doctor", "--to", "09121234567", stdout=StringIO(), stderr=StringIO())
        detail = str(excinfo.value)
        assert "کد الگو نامعتبر است" in detail  # متنِ درگاه عیناً از log عبور داده می‌شود
        assert "09121234567" not in detail  # مقصدِ کامل هرگز نشت نمی‌کند

    def test_live_send_refused_on_console_backend(self, settings) -> None:
        _configure(settings, provider="console")
        with pytest.raises(CommandError):
            call_command("sms_doctor", "--to", "09121234567", stdout=StringIO(), stderr=StringIO())

"""Tests — apps.core.mailing.send_text_email (multipart/alternative).

قراردادی که اینجا قفل می‌شود:
- ارسال با `html_message` → ایمیل واقعاً multipart/alternative می‌شود
  (alternative با mimetype text/html روی همان بدنهٔ plain)؛
- ارسال بدون `html_message` → رفتار بایت‌به‌بایت مثل قبل، بدون هیچ alternative
  تا call siteهای قدیمی (notifications/receipt/…) غافلگیر نشوند.
"""

from __future__ import annotations

from typing import Any

from apps.core import mailing


class _CollectingMailer:
    """mailer ساختگی که پیام‌های ارسالی را ضبط می‌کند."""

    def __init__(self) -> None:
        self.messages: list[Any] = []

    def send_messages(self, messages: list[Any]) -> int:
        self.messages.extend(messages)
        return len(messages)


def _patch_mailer(monkeypatch, mailer: _CollectingMailer) -> None:
    monkeypatch.setattr(mailing, "mailers", {"default": mailer})


def test_html_alternative_attached_when_provided(monkeypatch, settings) -> None:
    settings.DEFAULT_FROM_EMAIL = "brand@example.com"
    mailer = _CollectingMailer()
    _patch_mailer(monkeypatch, mailer)

    sent = mailing.send_text_email(
        subject="کد تأیید",
        message="کد: 123456",
        recipient_list=["user@example.com"],
        html_message="<p dir=rtl>کد: 123456</p>",
    )

    assert sent == 1
    message = mailer.messages[0]
    assert message.content_subtype == "plain"
    assert message.body == "کد: 123456"
    assert len(message.alternatives) == 1
    html, mimetype = message.alternatives[0]
    assert mimetype == "text/html"
    assert "123456" in html


def test_plain_only_behavior_unchanged_without_html(monkeypatch, settings) -> None:
    settings.DEFAULT_FROM_EMAIL = "brand@example.com"
    mailer = _CollectingMailer()
    _patch_mailer(monkeypatch, mailer)

    sent = mailing.send_text_email(
        subject="سلام",
        message="متن ساده",
        recipient_list=["user@example.com"],
    )

    assert sent == 1
    message = mailer.messages[0]
    assert message.alternatives == []
    assert message.body == "متن ساده"

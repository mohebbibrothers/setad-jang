"""
Custom email backend implementations for local and development delivery.
"""

from __future__ import annotations

from email.header import decode_header, make_header
from email.message import Message
from typing import Final

from django.core.mail.backends.console import EmailBackend as ConsoleEmailBackend
from django.core.mail.message import EmailMessage

SEPARATOR: Final[str] = "-" * 79


class ReadableConsoleEmailBackend(ConsoleEmailBackend):
    """
    Development-only email backend.

    Instead of printing the raw MIME/base64 email, this backend prints a
    decoded and human-readable preview in the console. This is useful for
    local development when working with OTP emails in Persian/UTF-8.
    """

    def write_message(self, message: EmailMessage) -> None:
        mime_message: Message = message.message()

        subject: str = self._decode_header_value(mime_message.get("Subject", ""))
        from_email: str = self._decode_header_value(mime_message.get("From", ""))
        to_emails: str = ", ".join(message.to)
        cc_emails: str = ", ".join(message.cc) if message.cc else ""
        bcc_emails: str = ", ".join(message.bcc) if message.bcc else ""
        body: str = self._extract_text_body(mime_message)

        self.stream.write(f"{SEPARATOR}\n")
        self.stream.write("Readable email preview (development only)\n")
        self.stream.write(f"{SEPARATOR}\n")
        self.stream.write(f"Subject: {subject}\n")
        self.stream.write(f"From: {from_email}\n")
        self.stream.write(f"To: {to_emails}\n")

        if cc_emails:
            self.stream.write(f"CC: {cc_emails}\n")

        if bcc_emails:
            self.stream.write(f"BCC: {bcc_emails}\n")

        self.stream.write("\n")
        self.stream.write(body)
        self.stream.write(f"\n{SEPARATOR}\n")
        self.stream.flush()

    @staticmethod
    def _decode_header_value(value: str) -> str:
        """Decode MIME-encoded email headers into readable UTF-8 text."""
        if not value:
            return ""

        return str(make_header(decode_header(value)))

    def _extract_text_body(self, mime_message: Message) -> str:
        """
        Extract and decode the plain text body from the email message.
        """
        if mime_message.is_multipart():
            for part in mime_message.walk():
                content_type: str = part.get_content_type()
                content_disposition: str = part.get("Content-Disposition", "")

                if content_type == "text/plain" and "attachment" not in content_disposition.lower():
                    return self._decode_payload(part)

            return ""

        return self._decode_payload(mime_message)

    @staticmethod
    def _decode_payload(part: Message) -> str:
        """Decode email payload using its declared charset."""
        payload = part.get_payload(decode=True)

        if payload is None:
            raw_payload = part.get_payload()
            return raw_payload if isinstance(raw_payload, str) else ""

        charset: str = part.get_content_charset() or "utf-8"
        return payload.decode(charset, errors="replace")

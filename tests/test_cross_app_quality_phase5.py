"""Production Phase 5 cross-app quality and coverage hardening tests."""

from __future__ import annotations

from io import StringIO
from types import SimpleNamespace

import pytest
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.mail import EmailMessage, EmailMultiAlternatives

from apps.core.email_backends import ReadableConsoleEmailBackend
from apps.kindness_wall.validators import (
    validate_listing_image_extension,
    validate_listing_image_size,
)
from apps.lms.validators import (
    validate_duration_seconds,
    validate_lesson_file_size,
    validate_lesson_video_file_size,
    validate_positive_weight,
    validate_quiz_passing_score,
)
from apps.r4j.validators import validate_attachment_extension, validate_photo_extension
from apps.tabyin.choices import MediaType
from apps.tabyin.sync.client import MohtavanegarClient
from apps.tabyin.sync.parser import extract_items, extract_page_info, parse_content_item


class TestReadableConsoleEmailBackend:
    """Email backend should produce readable UTF-8 development previews."""

    def test_prints_decoded_readable_email_preview(self) -> None:
        stream = StringIO()
        backend = ReadableConsoleEmailBackend(stream=stream)
        message = EmailMessage(
            subject="کد ورود",
            body="کد شما ۱۲۳۴۵ است",
            from_email="noreply@example.com",
            to=["user@example.com"],
            cc=["cc@example.com"],
            bcc=["bcc@example.com"],
        )

        backend.write_message(message)
        output = stream.getvalue()

        assert "Readable email preview" in output
        assert "کد ورود" in output
        assert "کد شما ۱۲۳۴۵ است" in output
        assert "cc@example.com" in output
        assert "bcc@example.com" in output

    def test_extracts_plain_text_part_from_multipart_message(self) -> None:
        stream = StringIO()
        backend = ReadableConsoleEmailBackend(stream=stream)
        message = EmailMultiAlternatives(
            subject="Multipart",
            body="plain body",
            from_email="noreply@example.com",
            to=["user@example.com"],
        )
        message.attach_alternative("<strong>html</strong>", "text/html")

        backend.write_message(message)

        assert "plain body" in stream.getvalue()


class TestTabyinParserContracts:
    """Tabyin parser should normalize provider payloads defensively."""

    def test_parse_content_item_normalizes_attachments_and_dates(self) -> None:
        raw = {
            "id": "abc-1",
            "e19_title": " عنوان محتوا ",
            "e20_description": " توضیح ",
            "username": "author",
            "entity_id": 12,
            "status": 1,
            "type": 2,
            "created_at": "2026-05-06 22:44:05",
            "updated_at": "bad-date",
            "e22_attachment": [
                {"url": "uploads/video.mp4", "size": "10MB", "duration": 12, "file_size": 100, "title": "ویدئو"},
                {"url": "uploads/image.webp", "title": "تصویر"},
                {"url": ""},
            ],
        }

        parsed = parse_content_item(raw)

        assert parsed["external_id"] == "abc-1"
        assert parsed["title"] == "عنوان محتوا"
        assert parsed["source_created_at"].tzinfo is not None
        assert parsed["source_updated_at"] is None
        assert parsed["attachments"][0]["media_type"] == MediaType.VIDEO
        assert parsed["attachments"][1]["media_type"] == MediaType.IMAGE
        assert len(parsed["attachments"]) == 2

    def test_parse_content_item_rejects_missing_id_and_extract_helpers_are_defensive(self) -> None:
        assert parse_content_item({"name": "بدون شناسه"}) is None
        assert extract_page_info({"data": {"total_page": 3, "page_size": 50, "count": 120}}) == {
            "total_pages": 3,
            "page_size": 50,
            "total_count": 120,
        }
        assert extract_items({"data": {"fields": [{"id": 1}]}}) == [{"id": 1}]


class TestTabyinClientContracts:
    """Tabyin HTTP client should handle provider failures without leaking exceptions."""

    def test_fetch_page_builds_expected_url_and_returns_json(self) -> None:
        client = MohtavanegarClient(base_url="https://provider.test/", authorization="Bearer token")
        captured: dict[str, str] = {}

        def fake_get(url: str, timeout: int):
            captured["url"] = url
            captured["timeout"] = str(timeout)
            return SimpleNamespace(
                status_code=200,
                headers={"Content-Type": "application/json"},
                json=lambda: {"status": True, "data": {"fields": []}},
                text="ok",
            )

        client._session.get = fake_get

        result = client.fetch_page(page=2, page_size=10)

        assert result["status"] is True
        assert "page=2" in captured["url"]
        assert "page_size=10" in captured["url"]
        assert captured["timeout"] == "30"

    def test_client_returns_none_for_non_json_or_failed_status(self) -> None:
        client = MohtavanegarClient(base_url="https://provider.test", authorization="Bearer token")

        client._session.get = lambda url, timeout: SimpleNamespace(
            status_code=200,
            headers={"Content-Type": "text/html"},
            json=lambda: {},
            text="<html></html>",
        )
        assert client.fetch_detail("abc") is None

        client._session.get = lambda url, timeout: SimpleNamespace(
            status_code=200,
            headers={"Content-Type": "application/json"},
            json=lambda: {"status": False},
            text='{"status": false}',
        )
        assert client.fetch_detail("abc") is None


class TestFileAndDomainValidators:
    """Cross-app validators should reject unsafe or invalid input."""

    def test_kindness_wall_image_validators(self) -> None:
        valid = SimpleUploadedFile("listing.webp", b"x", content_type="image/webp")
        invalid = SimpleUploadedFile("listing.exe", b"x")
        too_large = SimpleUploadedFile("large.jpg", b"x" * (6 * 1024 * 1024), content_type="image/jpeg")

        validate_listing_image_extension(valid)
        with pytest.raises(ValidationError):
            validate_listing_image_extension(invalid)
        with pytest.raises(ValidationError):
            validate_listing_image_size(too_large)

    def test_lms_numeric_and_file_validators(self) -> None:
        validate_duration_seconds(0)
        validate_quiz_passing_score(20)
        validate_positive_weight(1)
        validate_lesson_file_size(SimpleUploadedFile("handout.pdf", b"x" * 1024))
        validate_lesson_video_file_size(SimpleUploadedFile("lesson.mp4", b"x" * 1024))

        with pytest.raises(ValidationError):
            validate_duration_seconds(-1)
        with pytest.raises(ValidationError):
            validate_quiz_passing_score(21)
        with pytest.raises(ValidationError):
            validate_positive_weight(0)

    def test_r4j_file_security_rejects_dangerous_extension_before_domain_extension_check(self) -> None:
        safe_photo = SimpleUploadedFile("photo.webp", b"x")
        dangerous_attachment = SimpleUploadedFile("payload.sh", b"echo bad")

        validate_photo_extension(safe_photo)
        with pytest.raises(ValidationError):
            validate_attachment_extension(dangerous_attachment)

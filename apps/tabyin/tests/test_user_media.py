"""
تست‌های قراردادِ «رسانه‌ی روایت‌های مردمی»:

- هر روایت فقط یک نوع رسانه می‌پذیرد (تک‌نوعیِ پیوست‌ها)؛
- آپلود مستقیم: احراز هویت، allowlist فرمت، سقف حجم، EXIF-stripping و
  استخراجِ متادیتا (همان فیلدهایی که برای محتوای منبع خارجی پر می‌شود)؛
- نشانیِ محلی در ثبتِ محتوا → بلافاصله mirrored و دارای متادیتا؛
- نشانیِ بیرونی → pending و بعد از آینه‌سازیِ دفاعی روی سرور خودمان
  منتشر می‌شود (سدِ SSRF، عدم‌تطابق نوع، fallback هنگام شکست)؛
- نامِ پدیدآورنده‌ی پویا: نام کامل → ایمیل → موبایل → fallback.
"""

from __future__ import annotations

import io
import shutil
import socket
import tempfile
from pathlib import Path
from unittest import mock

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from PIL import Image
from rest_framework.test import APIClient

from apps.tabyin import services, uploading
from apps.tabyin.choices import MediaType, MirrorStatus, SubmissionStatus
from apps.tabyin.models import TabyinAttachment, TabyinContent
from apps.tabyin.serializers import PublicTabyinContentListSerializer

User = get_user_model()

SUBMISSIONS_URL = "/api/v1/tabyin/me/submissions/"
UPLOAD_URL = "/api/v1/tabyin/me/uploads/"
CONFIG_URL = "/api/v1/tabyin/uploads/config/"


def make_png_bytes(width: int = 6, height: int = 4) -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", (width, height), (24, 90, 160)).save(buffer, "PNG")
    return buffer.getvalue()


def make_user(**overrides) -> User:
    defaults = {
        "email": "narrator@example.com",
        "password": "StrongPass!123",
        "first_name": "سارا",
        "last_name": "محمدی",
    }
    defaults.update(overrides)
    return User.objects.create_user(**defaults)


class _FakeStreamResponse:
    """پاسخِ جعلیِ requests برای شبیه‌سازی دانلودِ آینه‌سازی."""

    def __init__(
        self,
        body: bytes,
        *,
        status: int = 200,
        content_type: str = "image/png",
        url: str = "https://media.example.net/files/pic.png",
    ) -> None:
        self._body = body
        self.status_code = status
        self.headers = {"Content-Type": content_type, "Content-Length": str(len(body))}
        self.url = url

    def iter_content(self, chunk_size: int = 65536):
        for index in range(0, len(self._body), chunk_size):
            yield self._body[index : index + chunk_size]

    def close(self) -> None:  # pragma: no cover - قرارداد requests
        return None

    def __enter__(self):
        return self

    def __exit__(self, *exc) -> None:
        self.close()


def _public_dns(hostname, port, proto=0):
    return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 0))]


_TEMP_MEDIA_ROOT = Path(tempfile.mkdtemp(prefix="tabyin-test-media-"))


@override_settings(MEDIA_ROOT=_TEMP_MEDIA_ROOT)
class UserMediaTestCase(TestCase):
    """زیرکلاس مشترک: MEDIA_ROOT موقت برای جداییِ فایل‌های تست."""

    @classmethod
    def tearDownClass(cls) -> None:
        super().tearDownClass()
        shutil.rmtree(_TEMP_MEDIA_ROOT, ignore_errors=True)


class SubmissionTypeHomogeneityTests(UserMediaTestCase):
    def setUp(self) -> None:
        self.user = make_user()
        self.client = APIClient()
        self.client.force_authenticate(self.user)

    def _payload(self, attachments: list[dict]) -> dict:
        return {
            "title": "روایت آزمایشی",
            "description": "شرحِ کوتاهِ روایت برای عبور از اعتبارسنجی پایه.",
            "attachments": attachments,
        }

    def test_mixed_attachment_types_rejected(self) -> None:
        response = self.client.post(
            SUBMISSIONS_URL,
            self._payload(
                [
                    {"url": "https://media.example.net/a.png", "media_type": "image"},
                    {"url": "https://media.example.net/b.mp4", "media_type": "video"},
                ]
            ),
            format="json",
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("یک نوع رسانه", str(response.data["errors"]["attachments"]))

    def test_same_type_attachments_accepted(self) -> None:
        response = self.client.post(
            SUBMISSIONS_URL,
            self._payload(
                [
                    {"url": "https://media.example.net/a.png", "media_type": "image"},
                    {"url": "https://media.example.net/b.webp", "media_type": "image"},
                ]
            ),
            format="json",
        )
        self.assertEqual(response.status_code, 201)
        # محتوای در انتظارِ بررسی is_active=False است و از منیجرِ عمومی پیدا نمی‌شود.
        content = TabyinContent.all_objects.get(external_id=response.data["data"]["external_id"])
        self.assertEqual(content.origin, "user_submitted")
        self.assertEqual(content.submission_status, SubmissionStatus.PENDING_REVIEW)

    def test_non_http_attachment_url_rejected(self) -> None:
        response = self.client.post(
            SUBMISSIONS_URL,
            self._payload([{"url": "ftp://files.example.net/a.png", "media_type": "image"}]),
            format="json",
        )
        self.assertEqual(response.status_code, 400)

    def test_remote_attachment_marks_pending_and_dispatches_mirror(self) -> None:
        with (
            mock.patch("apps.tabyin.tasks.mirror_tabyin_user_attachments_task") as mirror_task,
            self.captureOnCommitCallbacks(execute=True),
        ):
            response = self.client.post(
                SUBMISSIONS_URL,
                self._payload([{"url": "https://media.example.net/a.png", "media_type": "image"}]),
                format="json",
            )
        self.assertEqual(response.status_code, 201)
        attachment = TabyinAttachment.objects.get()
        self.assertEqual(attachment.mirror_status, MirrorStatus.PENDING)
        self.assertEqual(attachment.origin_url, "https://media.example.net/a.png")
        mirror_task.delay.assert_called_once_with(content_id=attachment.content_id)

    def test_no_mirror_dispatch_without_remote_urls(self) -> None:
        with (
            mock.patch("apps.tabyin.tasks.mirror_tabyin_user_attachments_task") as mirror_task,
            self.captureOnCommitCallbacks(execute=True),
        ):
            response = self.client.post(
                SUBMISSIONS_URL,
                {
                    "title": "روایت متنی",
                    "description": "پیوستی ندارد؛ پس تَسکی هم در صف نمی‌رود.",
                },
                format="json",
            )
        self.assertEqual(response.status_code, 201)
        mirror_task.delay.assert_not_called()


class MediaUploadEndpointTests(UserMediaTestCase):
    def setUp(self) -> None:
        self.user = make_user()
        self.client = APIClient()
        self.client.force_authenticate(self.user)

    def test_config_endpoint_is_public(self) -> None:
        response = APIClient().get(CONFIG_URL)
        self.assertEqual(response.status_code, 200)
        data = response.data["data"]
        self.assertIn("jpg", data["extensions"]["image"])
        self.assertIn("mp4", data["extensions"]["video"])
        self.assertGreaterEqual(data["max_mb"]["image"], 1)
        self.assertEqual(data["max_attachments"], 5)

    def test_upload_requires_authentication(self) -> None:
        response = APIClient().post(
            UPLOAD_URL,
            {"file": SimpleUploadedFile("p.png", make_png_bytes(), content_type="image/png")},
            format="multipart",
        )
        self.assertIn(response.status_code, (401, 403))

    def test_upload_rejects_forbidden_extension(self) -> None:
        response = self.client.post(
            UPLOAD_URL,
            {
                "file": SimpleUploadedFile(
                    "evil.exe", b"MZ-etc", content_type="application/x-msdownload"
                )
            },
            format="multipart",
        )
        self.assertEqual(response.status_code, 400)

    def test_upload_rejects_svg_even_as_image(self) -> None:
        response = self.client.post(
            UPLOAD_URL,
            {
                "file": SimpleUploadedFile(
                    "vector.svg",
                    b"<svg xmlns='http://www.w3.org/2000/svg'/>",
                    content_type="image/svg+xml",
                )
            },
            format="multipart",
        )
        self.assertEqual(response.status_code, 400)

    @override_settings(TABYIN_UPLOAD_MAX_MB={"image": 1, "video": 1, "audio": 1, "other": 1})
    def test_upload_over_limit_rejected(self) -> None:
        big = SimpleUploadedFile("big.png", b"\x00" * (1024 * 1024 + 16), content_type="image/png")
        response = self.client.post(UPLOAD_URL, {"file": big}, format="multipart")
        self.assertEqual(response.status_code, 400)
        self.assertIn("مگابایت", str(response.data))

    def test_upload_png_success_with_meta(self) -> None:
        response = self.client.post(
            UPLOAD_URL,
            {
                "file": SimpleUploadedFile(
                    "photo.png", make_png_bytes(12, 8), content_type="image/png"
                )
            },
            format="multipart",
        )
        self.assertEqual(response.status_code, 201)
        data = response.data["data"]
        self.assertTrue(data["url"].startswith("/media/public/tabyin/uploads/"))
        self.assertTrue(data["url"].endswith(".png"))
        self.assertEqual(data["media_type"], MediaType.IMAGE)
        self.assertEqual(data["size"], "12X8")
        self.assertGreaterEqual(data["file_size"], 1)
        self.assertIn("سرور بعثت", response.data["message"])

    def test_uploaded_local_url_flows_into_submission_as_mirrored(self) -> None:
        upload = self.client.post(
            UPLOAD_URL,
            {
                "file": SimpleUploadedFile(
                    "photo.png", make_png_bytes(9, 3), content_type="image/png"
                )
            },
            format="multipart",
        )
        url = upload.data["data"]["url"]
        with self.captureOnCommitCallbacks(execute=True):
            submission = self.client.post(
                SUBMISSIONS_URL,
                {
                    "title": "روایت با فایلِ بارگذاری‌شده",
                    "description": "پیوست از قبل روی سرور خودمان است.",
                    "attachments": [{"url": url, "media_type": "image"}],
                },
                format="json",
            )
        self.assertEqual(submission.status_code, 201)
        attachment = TabyinAttachment.objects.get()
        self.assertEqual(attachment.mirror_status, MirrorStatus.MIRRORED)
        self.assertEqual(attachment.size, "9X3")
        self.assertGreaterEqual(attachment.file_size, 1)
        self.assertEqual(attachment.origin_url, "")


class MirrorBehaviorTests(UserMediaTestCase):
    def setUp(self) -> None:
        self.user = make_user()
        self.content = TabyinContent.objects.create(
            title="روایت",
            description="شرح",
            origin="user_submitted",
            submitted_by=self.user,
            submission_status=SubmissionStatus.PENDING_REVIEW,
            is_active=False,
        )

    def _attachment(self, url: str, media_type: str = MediaType.IMAGE) -> TabyinAttachment:
        return TabyinAttachment.objects.create(
            content=self.content,
            url=url,
            relative_url=url,
            media_type=media_type,
            order=0,
            origin_url=url,
            mirror_status=MirrorStatus.PENDING,
        )

    def test_ssrf_guard_blocks_private_networks(self) -> None:
        for bad in (
            "http://127.0.0.1/admin/secret.png",
            "http://192.168.1.1/router.png",
            "http://[::1]/local.png",
            "file:///etc/passwd",
            "ftp://internal.example/x.png",
            "https://user:pass@media.example.net/a.png",
        ):
            with self.subTest(url=bad), self.assertRaises(uploading.MirrorError):
                uploading._assert_public_web_url(bad)

    def test_ssrf_guard_blocks_dns_resolving_to_private(self) -> None:
        def _dns(hostname, port, proto=0):
            return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("10.0.0.9", 0))]

        with (
            mock.patch.object(uploading.socket, "getaddrinfo", side_effect=_dns),
            self.assertRaises(uploading.MirrorError),
        ):
            uploading._assert_public_web_url("https://sneaky.example.net/a.png")

    def test_mirror_success_moves_attachment_to_local_storage(self) -> None:
        attachment = self._attachment("https://media.example.net/pic.png")
        body = make_png_bytes(20, 10)
        with (
            mock.patch.object(uploading.socket, "getaddrinfo", side_effect=_public_dns),
            mock.patch.object(
                uploading.requests,
                "get",
                return_value=_FakeStreamResponse(body, content_type="image/png"),
            ) as request_get,
        ):
            ok = uploading.mirror_attachment_to_local(attachment)
        self.assertTrue(ok)
        self.assertTrue(request_get.called)
        attachment.refresh_from_db()
        self.assertEqual(attachment.mirror_status, MirrorStatus.MIRRORED)
        self.assertTrue(attachment.url.startswith("/media/public/tabyin/shared/"))
        self.assertEqual(attachment.origin_url, "https://media.example.net/pic.png")
        self.assertEqual(attachment.size, "20X10")
        self.assertGreaterEqual(attachment.file_size, 1)
        self.assertEqual(attachment.mime_type, "image/png")

    def test_mirror_type_mismatch_fails_and_keeps_remote_url(self) -> None:
        attachment = self._attachment("https://media.example.net/clip.mp4", MediaType.VIDEO)
        with (
            mock.patch.object(uploading.socket, "getaddrinfo", side_effect=_public_dns),
            mock.patch.object(
                uploading.requests,
                "get",
                return_value=_FakeStreamResponse(b"\x00\x00\x00\x18ftyp", content_type="image/png"),
            ),
        ):
            ok = uploading.mirror_attachment_to_local(attachment)
        self.assertFalse(ok)
        attachment.refresh_from_db()
        self.assertEqual(attachment.mirror_status, MirrorStatus.FAILED)
        self.assertEqual(attachment.url, "https://media.example.net/clip.mp4")

    def test_mirror_failure_keeps_original_url(self) -> None:
        attachment = self._attachment("https://media.example.net/gone.png")
        with (
            mock.patch.object(uploading.socket, "getaddrinfo", side_effect=_public_dns),
            mock.patch.object(
                uploading.requests,
                "get",
                return_value=_FakeStreamResponse(b"not found", status=404),
            ),
        ):
            ok = uploading.mirror_attachment_to_local(attachment)
        self.assertFalse(ok)
        attachment.refresh_from_db()
        self.assertEqual(attachment.mirror_status, MirrorStatus.FAILED)
        self.assertEqual(attachment.url, "https://media.example.net/gone.png")


class AuthorDisplayResolutionTests(UserMediaTestCase):
    def _content_for(self, user) -> TabyinContent:
        return TabyinContent.objects.create(
            title="روایت",
            description="شرح",
            origin="user_submitted",
            submitted_by=user,
            author_username=user.primary_identifier_value or "",
            submission_status=SubmissionStatus.APPROVED,
            is_active=True,
        )

    def _author_of(self, content: TabyinContent) -> str:
        fresh = TabyinContent.objects.with_submitter().get(pk=content.pk)
        return PublicTabyinContentListSerializer(fresh).data["author_username"]

    def test_full_name_wins(self) -> None:
        user = make_user()
        self.assertEqual(self._author_of(self._content_for(user)), "سارا محمدی")

    def test_email_when_no_name(self) -> None:
        user = make_user(first_name="", last_name="", email="narrator@example.com")
        self.assertEqual(self._author_of(self._content_for(user)), "narrator@example.com")

    def test_phone_when_no_name_and_no_email(self) -> None:
        user = make_user(first_name="", last_name="", email=None, phone_number="+989121234567")
        self.assertEqual(self._author_of(self._content_for(user)), "+989121234567")

    def test_author_updates_after_profile_rename(self) -> None:
        user = make_user()
        content = self._content_for(user)
        user.first_name = "سارا"
        user.last_name = "رضایی"
        user.save(update_fields=["first_name", "last_name"])
        self.assertEqual(self._author_of(content), "سارا رضایی")

    def test_external_author_untouched(self) -> None:
        user = make_user()
        content = TabyinContent.objects.create(
            title="محتوای منبع",
            description="شرح",
            origin="external",
            external_id="ext-123",
            submitted_by=user,
            author_username="upstream_author",
            submission_status=SubmissionStatus.APPROVED,
            is_active=True,
        )
        self.assertEqual(self._author_of(content), "upstream_author")


class MirrorDispatchServiceTests(UserMediaTestCase):
    def test_mirror_service_counts_results(self) -> None:
        user = make_user()
        content = TabyinContent.objects.create(
            title="روایت",
            description="شرح",
            origin="user_submitted",
            submitted_by=user,
            submission_status=SubmissionStatus.PENDING_REVIEW,
            is_active=False,
        )
        for idx in range(2):
            TabyinAttachment.objects.create(
                content=content,
                url=f"https://media.example.net/{idx}.png",
                relative_url=f"https://media.example.net/{idx}.png",
                media_type=MediaType.IMAGE,
                order=idx,
                origin_url=f"https://media.example.net/{idx}.png",
                mirror_status=MirrorStatus.PENDING,
            )
        body = make_png_bytes()
        with (
            mock.patch.object(uploading.socket, "getaddrinfo", side_effect=_public_dns),
            mock.patch.object(
                uploading.requests,
                "get",
                side_effect=lambda *a, **kw: _FakeStreamResponse(body),
            ),
        ):
            result = services.mirror_user_content_attachments(content_id=content.pk)
        self.assertEqual(result["mirrored"], 2)
        self.assertEqual(result["failed"], 0)

    def test_mirror_service_missing_content_is_safe(self) -> None:
        result = services.mirror_user_content_attachments(content_id=424242)
        self.assertEqual(result["skipped"], "missing")

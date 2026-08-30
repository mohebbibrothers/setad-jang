"""
تست‌های «مدیریتِ روایت‌های من» (ویرایش/حذف) + تک‌نوع‌سازیِ سخت‌گیرانه + signalها.

پوشش:
- ویرایشِ روایت (PATCH): نقطه‌ایِ عنوان/شرح، جایگزینیِ کاملِ پیوست‌ها،
  قانونِ «بازگشت به صفِ بررسی پس از هر ویرایشِ روی روایتِ بررسی‌شده»،
  IDOR و احراز هویت؛
- حذفِ روایت (DELETE): حذفِ کامل از دیتابیس، IDOR و احراز هویت؛
- تک‌نوع‌سازیِ سخت‌گیرانه: بو کشیدن از پسوندِ نشانی در نبودِ media_type،
  ردِ ناسازگاریِ اعلام/پسوند، و اعتماد به اعلامِ کاربر برای نشانیِ
  بدونِ پسوندِ شناخته‌شده؛
- signalهای تازه (post_save/post_delete محتوا و پیوست): invalidate پس از
  commit، ردّ کردنِ saveهای bookkeeping، و سرکوب در همگام‌سازیِ انبوه —
  ریشه‌ی باگِ «حذف از ادمین ولی ماندن روی دیوار».
"""

from __future__ import annotations

from unittest import mock

from django.contrib.auth import get_user_model
from django.test import TestCase, TransactionTestCase
from django.utils import timezone
from rest_framework.test import APIClient

from apps.tabyin import services
from apps.tabyin.choices import (
    ContentOrigin,
    MediaType,
    MirrorStatus,
    SubmissionStatus,
)
from apps.tabyin.models import TabyinAttachment, TabyinContent
from apps.tabyin.signals import suppress_signal_invalidation

User = get_user_model()

LIST_URL = "/api/v1/tabyin/me/submissions/"


def detail_url(content_id: int) -> str:
    return f"/api/v1/tabyin/me/submissions/{content_id}/"


def make_user(**overrides) -> User:
    """کاربرِ تست با ایمیل پیش‌فرضِ یکتا برای هر صدا."""
    defaults = {
        "email": f"user-{User.objects.count() + 1}@example.com",
        "password": "StrongPass!123",
        "first_name": "سارا",
        "last_name": "محمدی",
    }
    defaults.update(overrides)
    return User.objects.create_user(**defaults)


def make_submission(
    user: User,
    *,
    status: str = SubmissionStatus.PENDING_REVIEW,
    is_active: bool = False,
    with_review: bool = False,
    attachments: list[dict] | None = None,
) -> TabyinContent:
    """ساختِ مستقیمِ یک روایت در وضعیتِ دلخواه (بایپسِ جریانِ API)."""
    now = timezone.now()
    content = TabyinContent.objects.create(
        title="روایت اولیه",
        description="شرحِ اولیه‌ی روایت.",
        origin=ContentOrigin.USER_SUBMITTED,
        submitted_by=user,
        submission_status=status,
        is_active=is_active,
        is_deleted_in_source=False,
        author_username="sara",
        source_created_at=now,
        source_updated_at=now,
        reviewed_by=make_user() if with_review else None,
        reviewed_at=now if with_review else None,
        admin_note="یادداشتِ بررسیِ قبلی." if with_review else "",
        raw_payload={"source": "user_submission"},
    )
    for index, att in enumerate(attachments or [{"url": "/media/public/x/a.png"}]):
        is_local = str(att["url"]).startswith("/media/")
        TabyinAttachment.objects.create(
            content=content,
            url=att["url"],
            relative_url=att["url"],
            media_type=att.get("media_type", MediaType.IMAGE),
            title=att.get("title", ""),
            order=index,
            origin_url="" if is_local else att["url"],
            mirror_status=(MirrorStatus.MIRRORED if is_local else MirrorStatus.PENDING),
        )
    return content


class SubmissionAuthAndIdorTests(TestCase):
    """گیتِ احراز و مالکیت — هیچ‌کس جز مالک به روایت دست نمی‌زند."""

    def setUp(self) -> None:
        self.owner = make_user()
        self.stranger = make_user()
        self.client = APIClient()

    def test_patch_requires_authentication(self) -> None:
        content = make_submission(self.owner)
        response = self.client.patch(detail_url(content.pk), {"title": "x"}, format="json")
        self.assertIn(response.status_code, (401, 403))

    def test_delete_requires_authentication(self) -> None:
        content = make_submission(self.owner)
        response = self.client.delete(detail_url(content.pk))
        self.assertIn(response.status_code, (401, 403))

    def test_patch_other_users_submission_not_found(self) -> None:
        self.client.force_authenticate(self.stranger)
        content = make_submission(self.owner)
        response = self.client.patch(detail_url(content.pk), {"title": "x"}, format="json")
        self.assertEqual(response.status_code, 404)

    def test_delete_other_users_submission_not_found(self) -> None:
        self.client.force_authenticate(self.stranger)
        content = make_submission(self.owner)
        response = self.client.delete(detail_url(content.pk))
        self.assertEqual(response.status_code, 404)
        self.assertTrue(TabyinContent.all_objects.filter(pk=content.pk).exists())


class SubmissionUpdateTests(TestCase):
    """رفتارِ اصلیِ ویرایش — فیلدها، پیوست‌ها و بازگشت به صفِ بررسی."""

    def setUp(self) -> None:
        self.user = make_user()
        self.client = APIClient()
        self.client.force_authenticate(self.user)

    def test_patch_title_and_description_on_pending(self) -> None:
        content = make_submission(self.user)
        response = self.client.patch(
            detail_url(content.pk),
            {"title": "عنوانِ تازه", "description": "شرحِ تازه‌ی روایت."},
            format="json",
        )
        self.assertEqual(response.status_code, 200)
        content.refresh_from_db()
        self.assertEqual(content.title, "عنوانِ تازه")
        self.assertEqual(content.description, "شرحِ تازه‌ی روایت.")
        # روایتِ درانتظار بدونِ تغییرِ وضعیت و همچنان پنهان می‌ماند.
        self.assertEqual(content.submission_status, SubmissionStatus.PENDING_REVIEW)
        self.assertFalse(content.is_active)
        self.assertIn("به‌روزرسانی شد", response.data["message"])

    def test_patch_approved_submission_re_pends_it(self) -> None:
        content = make_submission(
            self.user,
            status=SubmissionStatus.APPROVED,
            is_active=True,
            with_review=True,
        )
        response = self.client.patch(
            detail_url(content.pk),
            {"title": "عنوانِ ویرایش‌شده"},
            format="json",
        )
        self.assertEqual(response.status_code, 200)
        content.refresh_from_db()
        self.assertEqual(content.submission_status, SubmissionStatus.PENDING_REVIEW)
        self.assertFalse(content.is_active)
        self.assertIsNone(content.reviewed_by)
        self.assertIsNone(content.reviewed_at)
        self.assertEqual(content.admin_note, "")
        self.assertIn("صفِ بررسی", response.data["message"])

    def test_patch_rejected_submission_returns_to_queue(self) -> None:
        content = make_submission(
            self.user,
            status=SubmissionStatus.REJECTED,
            is_active=False,
            with_review=True,
        )
        response = self.client.patch(
            detail_url(content.pk),
            {"description": "روایت را اصلاح کردم؛ دوباره بررسی کنید."},
            format="json",
        )
        self.assertEqual(response.status_code, 200)
        content.refresh_from_db()
        self.assertEqual(content.submission_status, SubmissionStatus.PENDING_REVIEW)
        self.assertEqual(content.admin_note, "")

    def test_patch_empty_body_rejected(self) -> None:
        content = make_submission(self.user)
        response = self.client.patch(detail_url(content.pk), {}, format="json")
        self.assertEqual(response.status_code, 400)

    def test_patch_blank_title_rejected(self) -> None:
        content = make_submission(self.user)
        response = self.client.patch(
            detail_url(content.pk),
            {"title": "   "},
            format="json",
        )
        self.assertEqual(response.status_code, 400)

    def test_patch_attachments_replaces_fully(self) -> None:
        content = make_submission(
            self.user,
            attachments=[
                {"url": "/media/public/x/old1.png"},
                {"url": "/media/public/x/old2.png"},
            ],
        )
        with (
            mock.patch("apps.tabyin.tasks.mirror_tabyin_user_attachments_task") as mirror_task,
            self.captureOnCommitCallbacks(execute=True),
        ):
            response = self.client.patch(
                detail_url(content.pk),
                {
                    "attachments": [
                        {"url": "/media/public/x/new.png", "title": "جدید"},
                        {"url": "https://cdn.example.net/remote.png"},
                    ]
                },
                format="json",
            )
        self.assertEqual(response.status_code, 200)
        attachments = list(content.attachments.order_by("order"))
        self.assertEqual(len(attachments), 2)
        # نشانیِ بومی فوراً mirrored و نشانیِ بیرونی در صفِ آینه است.
        self.assertEqual(attachments[0].mirror_status, MirrorStatus.MIRRORED)
        self.assertEqual(attachments[1].mirror_status, MirrorStatus.PENDING)
        self.assertEqual(attachments[1].origin_url, "https://cdn.example.net/remote.png")
        mirror_task.delay.assert_called_once_with(content_id=content.pk)

    def test_patch_attachments_omitted_keeps_existing(self) -> None:
        content = make_submission(self.user)
        before = list(content.attachments.values_list("url", flat=True))
        response = self.client.patch(
            detail_url(content.pk),
            {"title": "فقط عنوان"},
            format="json",
        )
        self.assertEqual(response.status_code, 200)
        after = list(content.attachments.values_list("url", flat=True))
        self.assertEqual(before, after)

    def test_patch_empty_attachments_list_clears_all(self) -> None:
        content = make_submission(self.user)
        response = self.client.patch(
            detail_url(content.pk),
            {"attachments": []},
            format="json",
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(content.attachments.count(), 0)


class SubmissionDeleteTests(TestCase):
    """حذفِ کامل — سطر و پیوست‌ها می‌روند و دیگر جایی دیده نمی‌شوند."""

    def setUp(self) -> None:
        self.user = make_user()
        self.client = APIClient()
        self.client.force_authenticate(self.user)

    def test_delete_own_submission(self) -> None:
        content = make_submission(
            self.user,
            attachments=[
                {"url": "/media/public/x/a.png"},
                {"url": "/media/public/x/b.png"},
            ],
        )
        attachment_ids = list(content.attachments.values_list("pk", flat=True))
        response = self.client.delete(detail_url(content.pk))
        self.assertEqual(response.status_code, 200)
        self.assertIn("حذف شد", response.data["message"])
        self.assertFalse(TabyinContent.all_objects.filter(pk=content.pk).exists())
        self.assertFalse(TabyinAttachment.all_objects.filter(pk__in=attachment_ids).exists())

    def test_delete_approved_submission_removes_it_from_public(self) -> None:
        content = make_submission(
            self.user,
            status=SubmissionStatus.APPROVED,
            is_active=True,
            with_review=True,
        )
        external_id = content.external_id
        response = self.client.delete(detail_url(content.pk))
        self.assertEqual(response.status_code, 200)
        self.assertFalse(TabyinContent.all_objects.filter(external_id=external_id).exists())

    def test_deleted_submission_leaves_the_owner_list(self) -> None:
        content = make_submission(self.user)
        self.client.delete(detail_url(content.pk))
        list_response = self.client.get(LIST_URL)
        self.assertEqual(list_response.status_code, 200)
        ids = [item["id"] for item in list_response.data["data"]["results"]]
        self.assertNotIn(content.pk, ids)


class StrictHomogeneityTests(TestCase):
    """
    تک‌نوع‌سازیِ سخت‌گیرانه — حفره‌ی «پیش‌فرضِ other» برطرف شده است.

    پیش از این، پیوستی که media_type نداشت بی‌قید «other» ثبت می‌شد و
    مخلوطِ واقعیِ (مثلاً) عکس+ویدئو از چشمِ اعتبارسنجی رد می‌شد؛ حالا نوعِ
    واقعی از پسوندِ نشانی بویده می‌شود و ناسازگاریِ اعلام/واقعیت رد می‌شود.
    """

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

    def test_type_inferred_from_url_extension_when_omitted(self) -> None:
        response = self.client.post(
            LIST_URL,
            self._payload([{"url": "https://media.example.net/pic.png"}]),
            format="json",
        )
        self.assertEqual(response.status_code, 201)
        attachment = TabyinAttachment.objects.get()
        self.assertEqual(attachment.media_type, MediaType.IMAGE)

    def test_mixed_untyped_urls_caught_by_sniffing(self) -> None:
        response = self.client.post(
            LIST_URL,
            self._payload(
                [
                    {"url": "https://media.example.net/a.png"},
                    {"url": "https://media.example.net/b.mp4"},
                ]
            ),
            format="json",
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("یک نوع رسانه", str(response.data["errors"]["attachments"]))

    def test_explicit_type_versus_obvious_extension_rejected(self) -> None:
        response = self.client.post(
            LIST_URL,
            self._payload([{"url": "https://media.example.net/photo.jpg", "media_type": "audio"}]),
            format="json",
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("ناسازگار", str(response.data["errors"]["attachments"]))

    def test_explicit_type_plus_conflicting_untyped_url_rejected(self) -> None:
        response = self.client.post(
            LIST_URL,
            self._payload(
                [
                    {"url": "https://media.example.net/a.png", "media_type": "image"},
                    {"url": "https://media.example.net/b.mp4"},
                ]
            ),
            format="json",
        )
        self.assertEqual(response.status_code, 400)

    def test_explicit_type_without_sniffable_extension_trusted(self) -> None:
        response = self.client.post(
            LIST_URL,
            self._payload(
                [{"url": "https://media.example.net/watch?v=coffee", "media_type": "video"}]
            ),
            format="json",
        )
        self.assertEqual(response.status_code, 201)
        attachment = TabyinAttachment.objects.get()
        self.assertEqual(attachment.media_type, MediaType.VIDEO)

    def test_unknown_extension_without_explicit_type_defaults_to_other(self) -> None:
        response = self.client.post(
            LIST_URL,
            self._payload([{"url": "https://media.example.net/download/12345"}]),
            format="json",
        )
        self.assertEqual(response.status_code, 201)
        attachment = TabyinAttachment.objects.get()
        self.assertEqual(attachment.media_type, MediaType.OTHER)

    def test_extension_in_query_string_is_not_a_type_hint(self) -> None:
        response = self.client.post(
            LIST_URL,
            self._payload([{"url": "https://media.example.net/dl?file=a.mp4"}]),
            format="json",
        )
        self.assertEqual(response.status_code, 201)
        attachment = TabyinAttachment.objects.get()
        self.assertEqual(attachment.media_type, MediaType.OTHER)

    def test_url_sniffing_is_percent_decoded(self) -> None:
        response = self.client.post(
            LIST_URL,
            self._payload([{"url": "https://media.example.net/my%20clip.mp3"}]),
            format="json",
        )
        self.assertEqual(response.status_code, 201)
        attachment = TabyinAttachment.objects.get()
        self.assertEqual(attachment.media_type, MediaType.AUDIO)

    def test_patch_enforces_the_same_strictness(self) -> None:
        content = make_submission(self.user)
        response = self.client.patch(
            detail_url(content.pk),
            {
                "attachments": [
                    {"url": "/media/public/x/shot.png"},
                    {"url": "https://media.example.net/clip.mp4"},
                ]
            },
            format="json",
        )
        self.assertEqual(response.status_code, 400)
        # ویرایشِ نامعتبر هیچ اثری روی فهرستِ قبلی نمی‌گذارد.
        self.assertEqual(content.attachments.count(), 1)


class PublicCacheInvalidationSignalTests(TransactionTestCase):
    """
    signalهای fresh — ریشه‌ی «حذف از ادمین ولی پای ماندن روی دیوار».

    TransactionTestCase (نه TestCase) چون رفتارِ on_commit مدنظر است و
    باید commitِ واقعی رخ دهد تا callback اجرا شود.
    """

    def setUp(self) -> None:
        self.user = make_user()
        self.content = make_submission(
            self.user,
            status=SubmissionStatus.APPROVED,
            is_active=True,
            with_review=True,
        )

    def test_content_delete_invalidates_public_caches(self) -> None:
        with mock.patch.object(services, "invalidate_public_caches") as invalidate:
            self.content.delete()
        self.assertGreaterEqual(invalidate.call_count, 1)

    def test_admin_style_queryset_delete_invalidates_public_caches(self) -> None:
        with mock.patch.object(services, "invalidate_public_caches") as invalidate:
            TabyinContent.all_objects.filter(pk=self.content.pk).delete()
        self.assertGreaterEqual(invalidate.call_count, 1)

    def test_content_save_invalidates_public_caches(self) -> None:
        with mock.patch.object(services, "invalidate_public_caches") as invalidate:
            self.content.is_active = False
            self.content.save(update_fields=["is_active", "updated_at"])
        self.assertGreaterEqual(invalidate.call_count, 1)

    def test_bookkeeping_only_save_skips_invalidation(self) -> None:
        with mock.patch.object(services, "invalidate_public_caches") as invalidate:
            self.content.content_hash = "deadbeef"
            self.content.save(update_fields=["content_hash", "updated_at"])
        invalidate.assert_not_called()

    def test_attachment_change_invalidates_public_caches(self) -> None:
        attachment = self.content.attachments.get()
        with mock.patch.object(services, "invalidate_public_caches") as invalidate:
            attachment.url = "/media/public/x/mirrored.png"
            attachment.save(update_fields=["url", "updated_at"])
        self.assertGreaterEqual(invalidate.call_count, 1)

    def test_suppression_silences_signals_for_bulk_sync(self) -> None:
        with (
            mock.patch.object(services, "invalidate_public_caches") as invalidate,
            suppress_signal_invalidation(),
        ):
            self.content.title = "عنوانِ sync"
            self.content.save(update_fields=["title", "updated_at"])
        invalidate.assert_not_called()

    def test_suppression_is_scoped_and_releases(self) -> None:
        with suppress_signal_invalidation():
            pass
        with mock.patch.object(services, "invalidate_public_caches") as invalidate:
            self.content.title = "بعد از suppression"
            self.content.save(update_fields=["title", "updated_at"])
        self.assertGreaterEqual(invalidate.call_count, 1)

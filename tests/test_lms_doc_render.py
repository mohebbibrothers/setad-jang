"""رگرسیونِ «رندرِ سمتِ سرورِ صفحاتِ سند» — پاسخِ ریشه‌ای به متنِ به‌هم‌ریخته.

قرارداد: جلسه‌ی سنددار با PDFِ واقعی ⇒ صفحاتِ WebP + manifest تازه؛ پی‌لودِ
دسترسی شامل نشانیِ استریمِ امضاشده‌ی هر برگه؛ استریم با همان دو دروازه‌ی
امضا/نشست کار می‌کند. سندِ خراب ⇒ pages=[] و fallbackِ فرانت دست‌نخورده.
"""

from __future__ import annotations

import json
import pathlib

import pytest
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.urls import reverse
from rest_framework.test import APIClient

from apps.lms.pdf_pages import ensure_document_pages
from apps.lms.services import build_lesson_media_access, sign_lesson_media_token
from tests.factories.lms import (
    DocumentLessonFactory,
    EnrollmentFactory,
    PublishedCourseFactory,
)

pytestmark = pytest.mark.django_db

# فیکسچرِ واقعیِ داخل ریپو — سندِ نمونه‌ی گواهی (در CI هم هست).
SAMPLE_PDF = (
    pathlib.Path(__file__).resolve().parents[1]
    / "docs/assets/lms/basat_mardom_certificate_sample.pdf"
)


def _real_doc_lesson(settings, tmp_path):
    """جلسه‌ی سنددار با PDFِ واقعی، جداشده در MEDIA_ROOTِ موقت."""
    settings.MEDIA_ROOT = tmp_path
    lesson = DocumentLessonFactory()
    lesson.document_file.save("real-sample.pdf", ContentFile(SAMPLE_PDF.read_bytes()), save=True)
    return lesson


class TestServerRenderedPages:
    def test_render_creates_webp_pages_and_fresh_manifest(self, settings, tmp_path) -> None:
        lesson = _real_doc_lesson(settings, tmp_path)
        pages = ensure_document_pages(lesson)
        assert pages, "PDF واقعی باید رندر شود"
        assert pages[0]["n"] == 1
        for page in pages:
            assert page["width"] > 500 and page["height"] > 500
            base = f"lms/courses/{lesson.course_id}/lessons/{lesson.pk}/document-rendered"
            assert default_storage.exists(f"{base}/page-{page['n']:03d}.webp")
        with default_storage.open(f"{base}/manifest.json", "rb") as fh:
            manifest = json.loads(fh.read().decode("utf-8"))
        assert manifest["doc"]["name"] == lesson.document_file.name
        assert len(manifest["pages"]) == len(pages)

    def test_second_call_uses_cached_manifest(self, settings, tmp_path, monkeypatch) -> None:
        lesson = _real_doc_lesson(settings, tmp_path)
        first = ensure_document_pages(lesson)
        from apps.lms import pdf_pages

        def _boom(lesson_obj):
            raise AssertionError("نباید دوباره رندر شود؛ manifest تازه است")

        monkeypatch.setattr(pdf_pages, "_render_and_store", _boom)
        assert ensure_document_pages(lesson) == first

    def test_access_payload_lists_signed_page_urls(self, settings, tmp_path) -> None:
        lesson = _real_doc_lesson(settings, tmp_path)
        enrollment = EnrollmentFactory(course=lesson.course)
        payload = build_lesson_media_access(
            lesson=lesson, user=enrollment.user, media_kind="document"
        )
        pages = payload["pages"]
        assert pages, "پی‌لودِ سندِ واقعی باید صفحاتِ رندرشده داشته باشد"
        for page in pages:
            assert page["width"] > 0 and page["height"] > 0
            assert page["url"].startswith(
                f"lms/lessons/{lesson.pk}/media/docpage{page['n']}/stream/?t="
            )

    def test_stream_serves_rendered_page_with_signed_token(self, settings, tmp_path) -> None:
        lesson = _real_doc_lesson(settings, tmp_path)
        enrollment = EnrollmentFactory(course=lesson.course)
        payload = build_lesson_media_access(
            lesson=lesson, user=enrollment.user, media_kind="document"
        )
        page = payload["pages"][0]
        token = page["url"].split("?t=", 1)[1]
        path = reverse(
            "lms:lesson-media-stream",
            kwargs={"lesson_id": lesson.pk, "media_kind": f"docpage{page['n']}"},
        )
        response = APIClient().get(f"{path}?t={token}")
        assert response.status_code == 200
        assert "image/webp" in response["Content-Type"]
        body = b"".join(response.streaming_content)
        assert len(body) > 5_000  # تصویرِ واقعی، نه فایلِ خالی

    def test_document_token_cannot_open_rendered_page(self, settings, tmp_path) -> None:
        lesson = _real_doc_lesson(settings, tmp_path)
        token = sign_lesson_media_token(
            lesson=lesson, user=EnrollmentFactory(), media_kind="document"
        )
        path = reverse(
            "lms:lesson-media-stream",
            kwargs={"lesson_id": lesson.pk, "media_kind": "docpage1"},
        )
        assert APIClient().get(f"{path}?t={token}").status_code == 403

    def test_out_of_range_page_is_404(self, settings, tmp_path) -> None:
        lesson = _real_doc_lesson(settings, tmp_path)
        token = sign_lesson_media_token(
            lesson=lesson, user=EnrollmentFactory(), media_kind="docpage999"
        )
        path = reverse(
            "lms:lesson-media-stream",
            kwargs={"lesson_id": lesson.pk, "media_kind": "docpage999"},
        )
        assert APIClient().get(f"{path}?t={token}").status_code == 404

    def test_unrenderable_document_yields_empty_pages_fallback(self, settings, tmp_path) -> None:
        # فیکسچرِ بایت‌های ساختگی «%PDF-1.4 fixture» — قراردادِ fallback:
        # هیچ استثنایی بیرون نمی‌آید و قراردادِ قدیم (url خامِ استریم) پابرجاست.
        settings.MEDIA_ROOT = tmp_path
        course = PublishedCourseFactory()
        lesson = DocumentLessonFactory(course=course)
        enrollment = EnrollmentFactory(course=course)
        payload = build_lesson_media_access(
            lesson=lesson, user=enrollment.user, media_kind="document"
        )
        assert payload["pages"] == []
        assert payload["url"].startswith(f"lms/lessons/{lesson.pk}/media/document/stream/?t=")

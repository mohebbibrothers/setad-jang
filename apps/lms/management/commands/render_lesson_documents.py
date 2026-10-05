"""پیش‌رندرِ دسته‌ایِ صفحاتِ PDF جلسات — یک‌بار پس از هر دیپلوی/آپلود.

چرا؟ رندرِ تنبل هنگامِ اولین مطالعه انجام می‌شود؛ این کامند آن را برای همه‌ی
جلساتِ سنددار از قبل می‌سازد تا اولین دانش‌آموز هم لحظه‌ای منتظرِ آماده‌سازی
نماند. اجرای دوباره بی‌خطر است: فقط اسنادِ بدونِ manifest تازه رندر می‌شوند
(--force برای بازسازیِ اجباری).

    python manage.py render_lesson_documents          # همه‌ی جلساتِ سنددار
    python manage.py render_lesson_documents --lesson 12
"""

from typing import Any

from django.core.management.base import BaseCommand

from apps.lms.choices import LessonContentType
from apps.lms.models import Lesson
from apps.lms.pdf_pages import ensure_document_pages


class Command(BaseCommand):
    """پیش‌رندرِ دسته‌ایِ برگه‌های سند — یک‌بار پس از دیپلوی/آپلود."""

    help = "پیش‌رندرِ صفحاتِ PDFِ جلساتِ سنددار به WebP (موتورِ PDFium)"

    def add_arguments(self, parser: Any) -> None:
        parser.add_argument("--lesson", type=int, default=None, help="شناسه‌ی یک جلسه")
        parser.add_argument(
            "--force",
            action="store_true",
            help="حتی با manifestِ تازه هم بازسازی کن",
        )

    def handle(self, *args: Any, **options: Any) -> None:
        qs = Lesson.objects.filter(content_type=LessonContentType.DOCUMENT).exclude(
            document_file=""
        )
        lesson_id = options.get("lesson")
        if lesson_id:
            qs = qs.filter(pk=lesson_id)
        if options.get("force"):
            for lesson in qs.iterator():
                from apps.lms.pdf_pages import _render_and_store

                _render_and_store(lesson)
            self.stdout.write(self.style.SUCCESS("بازسازیِ اجباری انجام شد."))
            return
        rendered = 0
        skipped = 0
        for lesson in qs.iterator():
            pages = ensure_document_pages(lesson)
            if pages:
                rendered += 1
            else:
                skipped += 1
                self.stdout.write(self.style.WARNING(f"جلسه‌ی {lesson.pk}: سند رندرناپذیر — رد شد"))
        self.stdout.write(
            self.style.SUCCESS(f"تمام شد: {rendered} جلسه آماده، {skipped} جلسه رندرناپذیر.")
        )

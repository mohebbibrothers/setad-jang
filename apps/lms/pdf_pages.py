"""رندرِ سمتِ سرورِ صفحاتِ PDF به تصاویر WebP — پایانِ «متنِ به‌هم‌ریخته».

چرا این ماژول؟ موتورِ رندرِ سمتِ مرورگر (pdf.js) برای دسته‌ای از PDFهای واقعی —
مخصوصاً اسنادی با فونتِ فارسیِ غیراستاندارد، فونتِ embedنشده یا نگاشتِ ToUnicodeِ
خراب — گلیف‌ها را جداجدا و با فونتِ جانشینِ نامناسب می‌کشد و حتی متنِ لاتین را
هم درهم می‌ریزد. حلِ ریشه‌ای: صفحه‌ها یک‌بار روی سرور با موتور PDFium (همان
موتورِ داخلیِ مرورگر کروم) به تصویرِ WebP با وضوحِ بالا رندر می‌شوند و مرورگرِ
کاربر هرگز درگیرِ فونت‌هایِ فایل نمی‌شود — خروجی همیشه پیکسل‌پرفکت، فارسیِ
چسبیده و لاتینِ تمیز.

ذخیره‌سازی از طریقِ default_storage انجام می‌شود (نه مسیرِ خامِ دیسک) تا در
محیطِ لوکال و S3 یکسان کار کند. خروجیِ هر جلسه در کنارِ سندِ خودش و با یک
manifest.json (امضای سند = نام+حجم) نگهداری می‌شود؛ با تعویضِ فایل، رندرِ
کهنه به‌صورتِ خودکار دور ریخته و دوباره ساخته می‌شود. هر شکستِ رندر (فایلِ
خراب/رمزدار/غیر PDF) به‌صورتِ امن None برمی‌گرداند تا فرانت بدونِ نقص به
نمایشگرِ pdf.js برگردد (fallback).
"""

from __future__ import annotations

import contextlib
import io
import json
import logging
from typing import Any

from django.core.files.base import ContentFile
from django.core.files.storage import default_storage

logger = logging.getLogger(__name__)

# مقیاسِ رندر: A4 (۵۹۵pt) با ضریبِ ۲٫۵ ≈ ۱۴۸۸px عرض — برای زومِ ۱۶۰٪ هم تیز.
RENDER_SCALE = 2.5
# سقف‌های امنیتی در برابرِ اسنادِ مهندسی‌شده‌ی حجیم (decompression bomb).
MAX_PAGES = 400
MAX_WIDTH_PX = 2400
WEBP_QUALITY = 86


def _render_dir(lesson: Any) -> str:
    """پوشه‌ی خروجیِ رندرِ صفحات، هم‌خانواده با مسیرِ آپلودِ خودِ سند."""
    return f"lms/courses/{lesson.course_id}/lessons/{lesson.pk}/document-rendered"


def _manifest_path(lesson: Any) -> str:
    """مسیرِ manifestِ رندر — امضای سند + فهرستِ ابعادِ برگه‌ها."""
    return f"{_render_dir(lesson)}/manifest.json"


def _page_path(lesson: Any, page_number: int) -> str:
    """مسیرِ فایلِ WebPِ یک برگه (شماره‌گذاریِ سه‌رقمی ⇒ مرتب‌سازیِ پایدار)."""
    return f"{_render_dir(lesson)}/page-{page_number:03d}.webp"


def _doc_signature(lesson: Any) -> dict[str, Any]:
    """امضای نسخه‌ی فعلیِ سند — تعویض فایل ⇒ ابطالِ رندرِ کهنه."""
    try:
        size = lesson.document_file.size
    except Exception:
        size = -1
    return {"name": lesson.document_file.name or "", "size": size}


def _read_manifest(lesson: Any) -> dict[str, Any] | None:
    """خواندنِ manifest فعلی؛ خراب/ناقص ⇒ None تا رندرِ تازه انجام شود."""
    path = _manifest_path(lesson)
    try:
        if not default_storage.exists(path):
            return None
        with default_storage.open(path, "rb") as fh:
            data = json.loads(fh.read().decode("utf-8"))
    except Exception:
        return None
    if not isinstance(data, dict) or not isinstance(data.get("pages"), list):
        return None
    return data


def _wipe_rendered(lesson: Any) -> None:
    """حذفِ خروجیِ قبلی تا صفحه‌ی اضافه‌ی رندرِ کهنه سرو نشود."""
    directory = _render_dir(lesson)
    try:
        _dirs, files = default_storage.listdir(directory)
    except Exception:
        return
    for name in files:
        try:
            default_storage.delete(f"{directory}/{name}")
        except Exception:
            continue


def _render_and_store(lesson: Any) -> list[dict[str, int]] | None:
    """رندرِ واقعی با PDFium و نگهداشتِ WebPها + manifest در ذخیره‌ساز."""
    import pypdfium2 as pdfium

    try:
        with lesson.document_file.open("rb") as fh:
            data = fh.read()
        pdf: Any = pdfium.PdfDocument(data)
    except Exception as exc:
        logger.warning("lms.docrender: lesson %s unreadable pdf: %s", lesson.pk, exc)
        return None

    try:
        total = min(len(pdf), MAX_PAGES)
        if total <= 0:
            return None
        _wipe_rendered(lesson)
        pages: list[dict[str, int]] = []
        for index in range(total):
            page = pdf[index]
            try:
                base_width = float(page.get_width())
                if base_width <= 0:
                    continue
                scale = min(RENDER_SCALE, MAX_WIDTH_PX / base_width)
                pil_image = page.render(scale=scale).to_pil().convert("RGB")
                buf = io.BytesIO()
                pil_image.save(buf, "WEBP", quality=WEBP_QUALITY, method=4)
                default_storage.save(_page_path(lesson, index + 1), ContentFile(buf.getvalue()))
                pages.append({"n": index + 1, "width": pil_image.width, "height": pil_image.height})
            finally:
                page.close()
        if not pages:
            return None
        manifest = {
            "v": 1,
            "doc": _doc_signature(lesson),
            "pages": pages,
        }
        default_storage.save(
            _manifest_path(lesson),
            ContentFile(json.dumps(manifest, ensure_ascii=False).encode("utf-8")),
        )
        return pages
    except Exception as exc:
        logger.warning("lms.docrender: lesson %s render failed: %s", lesson.pk, exc)
        return None
    finally:
        with contextlib.suppress(Exception):
            pdf.close()


def ensure_document_pages(lesson: Any) -> list[dict[str, int]] | None:
    """مانیفستِ تازه‌ی صفحاتِ رندرشده؛ اگر نبود/کهنه بود همینجا رندر می‌کند.

    خروجی: [{"n": 1, "width": …, "height": …}, …] یا None (سندِ رندرناپذیر).
    فراخوان: هزینه‌ی مسیرِ خوش‌حال = یک exists + یک خواندنِ json کوچک.
    """
    if not getattr(lesson, "document_file", None):
        return None
    sig = _doc_signature(lesson)
    manifest = _read_manifest(lesson)
    if manifest is not None and manifest.get("doc") == sig:
        return manifest["pages"]
    return _render_and_store(lesson)


def open_rendered_document_page(*, lesson: Any, page_number: int) -> dict[str, Any] | None:
    """گشودنِ فایلِ یک صفحه‌ی رندرشده برای استریم — با همان قراردادِ file_field.

    صفحه وجود نداشت؟ تلاشِ رندرِ تنبل (شاید manifest هنوز ساخته نشده)؛ آن هم
    نشد یعنی چنین صفحه‌ای نیست ⇒ None تا ویو ۴۰۴ بدهد.
    """
    path = _page_path(lesson, page_number)
    if not default_storage.exists(path):
        pages = ensure_document_pages(lesson)
        if not pages or not any(p["n"] == page_number for p in pages):
            return None
        if not default_storage.exists(path):
            return None
    try:
        return {
            "file_field": default_storage.open(path, "rb"),
            "base_name": f"lesson-{lesson.pk}-page-{page_number}",
        }
    except Exception:
        return None

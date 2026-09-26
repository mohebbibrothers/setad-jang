"""
Pure validators for the LMS domain.

Validators here do not perform database queries. Cross-record business rules live
in services so they can be transaction-safe and easier to test.
"""

from django.core.exceptions import ValidationError

MAX_LESSON_ATTACHMENT_MB = 25
MAX_LESSON_VIDEO_FILE_MB = 1024
MAX_LESSON_DOCUMENT_MB = 100
ALLOWED_LESSON_DOCUMENT_EXTENSIONS: frozenset[str] = frozenset(
    {"pdf", "epub", "doc", "docx", "ppt", "pptx", "txt"}
)
MIN_PASSING_SCORE = 0
MAX_PASSING_SCORE = 20


def validate_duration_seconds(value: int) -> None:
    """Validate that a media duration is non-negative."""
    if value < 0:
        raise ValidationError("مدت زمان نمی‌تواند منفی باشد.")


def validate_quiz_passing_score(value: float) -> None:
    """Validate quiz passing score on the 0..20 scale."""
    if value < MIN_PASSING_SCORE or value > MAX_PASSING_SCORE:
        raise ValidationError("نمره قبولی باید بین ۰ تا ۲۰ باشد.")


def validate_positive_weight(value: float) -> None:
    """Validate positive question weight."""
    if value <= 0:
        raise ValidationError("وزن سؤال باید بزرگ‌تر از صفر باشد.")


def validate_lesson_file_size(file) -> None:
    """Validate lesson handout/attachment size."""
    max_bytes = MAX_LESSON_ATTACHMENT_MB * 1024 * 1024
    if file.size > max_bytes:
        raise ValidationError(
            f"حجم فایل جزوه نباید بیشتر از {MAX_LESSON_ATTACHMENT_MB} مگابایت باشد."
        )


def validate_lesson_video_file_size(file) -> None:
    """Validate uploaded lesson video size."""
    max_bytes = MAX_LESSON_VIDEO_FILE_MB * 1024 * 1024
    if file.size > max_bytes:
        raise ValidationError(f"حجم ویدئو نباید بیشتر از {MAX_LESSON_VIDEO_FILE_MB} مگابایت باشد.")


def validate_lesson_document_file(file) -> None:
    """اعتبارسنجی فایل سندِ جلسه (document lesson).

    دو خط قرمز: پسوندِ مجاز (سند خواندنی، نه اجرایی/فشرده) و سقف حجم.
    بررسی پسوند روی نام کوچک‌شده انجام می‌شود تا `PDF`/`Pdf` هم قبول شود؛
    این یک allowlist است — هر چیز ناشناخته رد می‌شود (secure-by-default).
    """
    name = (getattr(file, "name", "") or "").lower()
    extension = name.rsplit(".", 1)[-1] if "." in name else ""
    if extension not in ALLOWED_LESSON_DOCUMENT_EXTENSIONS:
        allowed = "، ".join(sorted(ALLOWED_LESSON_DOCUMENT_EXTENSIONS))
        raise ValidationError(f"فرمت فایل سند مجاز نیست. فرمت‌های مجاز: {allowed}.")
    max_bytes = MAX_LESSON_DOCUMENT_MB * 1024 * 1024
    if file.size > max_bytes:
        raise ValidationError(f"حجم فایل سند نباید بیشتر از {MAX_LESSON_DOCUMENT_MB} مگابایت باشد.")

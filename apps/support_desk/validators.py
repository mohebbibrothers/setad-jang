"""Validators for Support Desk domain."""

from pathlib import Path

from django.core.exceptions import ValidationError

from apps.core.file_security import validate_uploaded_file_security

ALLOWED_ATTACHMENT_EXTENSIONS = {
    ".jpg",
    ".jpeg",
    ".png",
    ".webp",
    ".pdf",
    ".txt",
    ".doc",
    ".docx",
    ".xlsx",
}
MAX_ATTACHMENT_SIZE_BYTES = 10 * 1024 * 1024


def validate_attachment_extension(file_obj) -> None:
    """Validate support attachment file extension."""
    validate_uploaded_file_security(file_obj)
    extension = Path(file_obj.name or "").suffix.lower()
    if extension not in ALLOWED_ATTACHMENT_EXTENSIONS:
        raise ValidationError("پسوند فایل ضمیمه مجاز نیست.")


def validate_attachment_size(file_obj) -> None:
    """Validate support attachment file size."""
    if getattr(file_obj, "size", 0) > MAX_ATTACHMENT_SIZE_BYTES:
        raise ValidationError("حجم فایل ضمیمه نباید بیشتر از ۱۰ مگابایت باشد.")


def validate_duplicate_score(value: int) -> None:
    """Validate duplicate score range."""
    if value < 0 or value > 100:
        raise ValidationError("امتیاز تشخیص تکراری بودن باید بین ۰ تا ۱۰۰ باشد.")

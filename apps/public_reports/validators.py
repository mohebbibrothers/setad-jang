"""
Pure validators for public report uploaded files.
"""

from django.core.exceptions import ValidationError

ALLOWED_IMAGE_EXTENSIONS = ["jpg", "jpeg", "png", "webp"]
MAX_IMAGE_SIZE_MB = 5
MAX_ATTACHMENTS_PER_REPORT = 5


def validate_image_extension(file):
    """validate_image_extension helper for the public_reports application."""
    extension = file.name.split(".")[-1].lower()
    if extension not in ALLOWED_IMAGE_EXTENSIONS:
        raise ValidationError(
            f"فرمت فایل مجاز نیست. فرمت‌های مجاز: {', '.join(ALLOWED_IMAGE_EXTENSIONS)}"
        )


def validate_image_size(file):
    """validate_image_size helper for the public_reports application."""
    max_bytes = MAX_IMAGE_SIZE_MB * 1024 * 1024
    if file.size > max_bytes:
        raise ValidationError(f"حجم فایل نباید بیشتر از {MAX_IMAGE_SIZE_MB} مگابایت باشد.")

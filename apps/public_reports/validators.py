from django.core.exceptions import ValidationError

ALLOWED_IMAGE_EXTENSIONS = ["jpg", "jpeg", "png", "webp"]
MAX_IMAGE_SIZE_MB = 5
MAX_ATTACHMENTS_PER_REPORT = 10


def validate_image_extension(file):
    extension = file.name.split(".")[-1].lower()
    if extension not in ALLOWED_IMAGE_EXTENSIONS:
        raise ValidationError(
            f"فرمت فایل مجاز نیست. فرمت‌های مجاز: {', '.join(ALLOWED_IMAGE_EXTENSIONS)}"
        )


def validate_image_size(file):
    max_bytes = MAX_IMAGE_SIZE_MB * 1024 * 1024
    if file.size > max_bytes:
        raise ValidationError(f"حجم فایل نباید بیشتر از {MAX_IMAGE_SIZE_MB} مگابایت باشد.")

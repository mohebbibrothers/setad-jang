"""Pure validators for Kindness Wall files and scores."""

from django.core.exceptions import ValidationError

ALLOWED_IMAGE_EXTENSIONS = {"jpg", "jpeg", "png", "webp"}
MAX_IMAGE_SIZE_MB = 5
MAX_IMAGES_PER_LISTING = 10


def validate_listing_image_extension(file) -> None:
    """Validate listing image extension."""
    extension = file.name.rsplit(".", 1)[-1].lower() if "." in file.name else ""
    if extension not in ALLOWED_IMAGE_EXTENSIONS:
        raise ValidationError(
            f"فرمت تصویر مجاز نیست. فرمت‌های مجاز: {', '.join(sorted(ALLOWED_IMAGE_EXTENSIONS))}"
        )


def validate_listing_image_size(file) -> None:
    """Validate listing image size."""
    if file.size > MAX_IMAGE_SIZE_MB * 1024 * 1024:
        raise ValidationError(f"حجم تصویر نباید بیشتر از {MAX_IMAGE_SIZE_MB} مگابایت باشد.")


def validate_match_score(value: int) -> None:
    """Validate match score on a 0..100 scale."""
    if value < 0 or value > 100:
        raise ValidationError("امتیاز تطبیق باید بین ۰ تا ۱۰۰ باشد.")

"""Storage backends for local, S3/MinIO and CDN-ready media handling."""

from __future__ import annotations

from django.conf import settings
from django.core.files.storage import FileSystemStorage
from storages.backends.s3boto3 import S3Boto3Storage


def _configured_acl(default: str) -> str | None:
    """Return the ACL to send with uploads, or ``None`` to send none at all.

    باکت‌های S3 که با «Object Ownership: Bucket owner enforced» ساخته شده‌اند
    — که از آوریل ۲۰۲۳ **پیش‌فرض خود AWS** است — ACL را کاملاً نمی‌پذیرند و
    هر آپلودی که هدر ACL داشته باشد با خطای ``AccessControlListNotSupported``
    رد می‌شود. یعنی مقدار ثابت ``public-read`` روی یک باکت تازه‌ساخت، همهٔ
    آپلودهای رسانه را می‌شکند.

    MinIO هم رفتار متفاوتی دارد. پس این مقدار باید پیکربندی‌پذیر باشد و
    گزینهٔ «اصلاً ACL نفرست» را داشته باشد.

    مقدار ویژهٔ ``"none"`` (یا رشتهٔ خالی) یعنی هیچ ACLی ارسال نشود؛ در این
    حالت دسترسی عمومی باید با bucket policy مدیریت شود که روش توصیه‌شدهٔ
    فعلی AWS است.
    """
    value = getattr(settings, "AWS_DEFAULT_ACL_MODE", default)
    if value is None:
        return None
    value = str(value).strip().lower()
    if value in {"", "none", "off", "disabled"}:
        return None
    if value in {"legacy", "default"}:
        # رفتار تاریخی: هر storage ACL مخصوص خودش را بفرستد.
        return default
    return value


class PublicMediaStorage(S3Boto3Storage):
    """Public S3-compatible media storage, optionally fronted by CDN."""

    location = "media/public"
    file_overwrite = False
    querystring_auth = False

    @property
    def default_acl(self):
        """ACL آپلودهای عمومی — پیکربندی‌پذیر و قابل غیرفعال‌سازی."""
        return _configured_acl("public-read")

    @property
    def custom_domain(self):
        """Return CDN/custom domain for public media when configured."""
        return getattr(settings, "AWS_S3_CUSTOM_DOMAIN", None) or None


class PrivateMediaStorage(S3Boto3Storage):
    """Private S3-compatible media storage with signed URLs."""

    location = "media/private"
    file_overwrite = False
    querystring_auth = True
    querystring_expire = 60 * 10

    @property
    def default_acl(self):
        """ACL آپلودهای خصوصی — با bucket owner enforced باید خاموش باشد."""
        return _configured_acl("private")


class LocalPrivateMediaStorage(FileSystemStorage):
    """Local development private-media storage under MEDIA_ROOT/private."""

    def __init__(self, *args, **kwargs) -> None:
        kwargs.setdefault("location", settings.MEDIA_ROOT / "private")
        kwargs.setdefault("base_url", f"{settings.MEDIA_URL.rstrip('/')}/private/")
        super().__init__(*args, **kwargs)


class LocalPublicMediaStorage(FileSystemStorage):
    """Local development public-media storage under MEDIA_ROOT/public."""

    def __init__(self, *args, **kwargs) -> None:
        kwargs.setdefault("location", settings.MEDIA_ROOT / "public")
        kwargs.setdefault("base_url", f"{settings.MEDIA_URL.rstrip('/')}/public/")
        super().__init__(*args, **kwargs)

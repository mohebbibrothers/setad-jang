"""Storage backends for local, S3/MinIO and CDN-ready media handling."""

from __future__ import annotations

from django.conf import settings
from django.core.files.storage import FileSystemStorage
from storages.backends.s3boto3 import S3Boto3Storage


class PublicMediaStorage(S3Boto3Storage):
    """Public S3-compatible media storage, optionally fronted by CDN."""

    location = "media/public"
    default_acl = "public-read"
    file_overwrite = False
    querystring_auth = False

    @property
    def custom_domain(self):
        """Return CDN/custom domain for public media when configured."""
        return getattr(settings, "AWS_S3_CUSTOM_DOMAIN", None) or None


class PrivateMediaStorage(S3Boto3Storage):
    """Private S3-compatible media storage with signed URLs."""

    location = "media/private"
    default_acl = "private"
    file_overwrite = False
    querystring_auth = True
    querystring_expire = 60 * 10


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

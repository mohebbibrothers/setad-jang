"""Production Phase 3 media/object-storage/CDN contracts."""

from __future__ import annotations

import pytest
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings

from apps.core.file_security import ExtensionBlocklistScanner, validate_uploaded_file_security
from apps.core.storage import (
    LocalPrivateMediaStorage,
    LocalPublicMediaStorage,
    PrivateMediaStorage,
    PublicMediaStorage,
)
from apps.support_desk.validators import validate_attachment_extension


class TestMediaStorageContracts:
    """Storage backend contract tests."""

    def test_local_public_and_private_storage_locations_are_separated(self) -> None:
        public = LocalPublicMediaStorage()
        private = LocalPrivateMediaStorage()

        assert str(public.location).endswith("media/public")
        assert str(private.location).endswith("media/private")
        assert public.base_url.endswith("/media/public/")
        assert private.base_url.endswith("/media/private/")

    @override_settings(AWS_S3_CUSTOM_DOMAIN="cdn.example.com")
    def test_public_s3_storage_uses_cdn_domain_without_signed_query(self) -> None:
        storage = PublicMediaStorage()

        assert storage.custom_domain == "cdn.example.com"
        assert storage.querystring_auth is False

    def test_private_s3_storage_uses_signed_urls(self) -> None:
        storage = PrivateMediaStorage()

        assert storage.querystring_auth is True
        assert storage.querystring_expire == 600

    @override_settings(AWS_DEFAULT_ACL_MODE="none")
    def test_acl_header_is_omitted_when_disabled(self) -> None:
        """پیش‌فرض پروژه: هیچ ACLی ارسال نشود.

        باکت‌های «Object Ownership: Bucket owner enforced» — پیش‌فرض AWS از
        آوریل ۲۰۲۳ — هر آپلود دارای هدر ACL را رد می‌کنند.
        """
        assert PublicMediaStorage().default_acl is None
        assert PrivateMediaStorage().default_acl is None

    @override_settings(AWS_DEFAULT_ACL_MODE="legacy")
    def test_legacy_acl_mode_restores_per_storage_defaults(self) -> None:
        """برای باکت‌های قدیمی یا MinIO باید بشود ACL را برگرداند."""
        assert PublicMediaStorage().default_acl == "public-read"
        assert PrivateMediaStorage().default_acl == "private"

    @override_settings(AWS_DEFAULT_ACL_MODE="public-read")
    def test_explicit_acl_mode_overrides_both_storages(self) -> None:
        assert PublicMediaStorage().default_acl == "public-read"
        assert PrivateMediaStorage().default_acl == "public-read"


class TestFileSecurityContracts:
    """Upload security scanner contract tests."""

    def test_extension_blocklist_scanner_rejects_dangerous_files(self) -> None:
        scanner = ExtensionBlocklistScanner()
        dangerous = SimpleUploadedFile("payload.exe", b"MZ")
        safe = SimpleUploadedFile("receipt.pdf", b"%PDF")

        assert scanner.scan(safe).clean is True
        result = scanner.scan(dangerous)
        assert result.clean is False
        assert result.reason == "dangerous_extension"

    def test_common_file_security_validator_blocks_script_like_uploads(self) -> None:
        dangerous = SimpleUploadedFile("script.sh", b"rm -rf /")

        with pytest.raises(ValidationError):
            validate_uploaded_file_security(dangerous)

    def test_support_attachment_validator_uses_file_security_contract(self) -> None:
        dangerous = SimpleUploadedFile("payload.exe", b"MZ")
        safe = SimpleUploadedFile("evidence.pdf", b"%PDF")

        validate_attachment_extension(safe)
        with pytest.raises(ValidationError):
            validate_attachment_extension(dangerous)

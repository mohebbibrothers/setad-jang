"""File upload security helpers and scanner abstraction.

The current production-ready interface supports clean/noop scanning and is built
so a ClamAV or vendor scanner can be swapped in without changing app validators.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from django.conf import settings
from django.core.exceptions import ValidationError

DANGEROUS_EXTENSIONS = {
    ".exe",
    ".dll",
    ".bat",
    ".cmd",
    ".com",
    ".scr",
    ".ps1",
    ".sh",
    ".php",
    ".jsp",
    ".js",
    ".html",
    ".svg",
}


@dataclass(frozen=True)
class FileScanResult:
    """Result returned by a file scanner provider."""

    clean: bool
    provider: str
    reason: str = ""


class FileScanner(Protocol):
    """Protocol for pluggable upload scanners."""

    def scan(self, file_obj) -> FileScanResult:
        """Scan uploaded file and return the verdict."""


class NoopFileScanner:
    """Scanner used before a real malware scanner is configured."""

    provider = "noop"

    def scan(self, file_obj) -> FileScanResult:
        """Return clean while preserving the scanner contract."""
        return FileScanResult(clean=True, provider=self.provider)


class ExtensionBlocklistScanner:
    """Lightweight defensive scanner blocking dangerous executable extensions."""

    provider = "extension_blocklist"

    def scan(self, file_obj) -> FileScanResult:
        """Block dangerous extensions even before malware scanning is integrated."""
        extension = Path(getattr(file_obj, "name", "") or "").suffix.lower()
        if extension in DANGEROUS_EXTENSIONS:
            return FileScanResult(clean=False, provider=self.provider, reason="dangerous_extension")
        return FileScanResult(clean=True, provider=self.provider)


def get_file_scanner() -> FileScanner:
    """Return configured file scanner provider."""
    provider = getattr(settings, "FILE_SCAN_PROVIDER", "extension_blocklist")
    if provider == "noop":
        return NoopFileScanner()
    return ExtensionBlocklistScanner()


def validate_uploaded_file_security(file_obj) -> None:
    """Validate uploaded file against the configured security scanner."""
    result = get_file_scanner().scan(file_obj)
    if not result.clean:
        raise ValidationError("فایل ضمیمه از نظر امنیتی مجاز نیست.")

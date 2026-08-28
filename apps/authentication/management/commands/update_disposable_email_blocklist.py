"""
Management command — update disposable email blocklist.

این command لیست دامنه‌های disposable email را از یک منبع open-source
دانلود می‌کند و در apps/authentication/data/disposable_email_domains.txt
ذخیره می‌کند. این فایل سپس توسط validator در زمان signup استفاده می‌شود
به‌صورت O(1) lookup در حافظه.

اصول طراحی:
- این command فقط در زمان maintenance یا قبل از deploy اجرا می‌شود؛
  هرگز در runtime startup صدا زده نمی‌شود تا external dependency
  در bootstrap وجود نداشته باشد.
- منبع پیش‌فرض یک repo GitHub پایدار و community-maintained است.
- در صورت failure شبکه، فایل قبلی دست‌نخورده می‌ماند (atomic write).
- محتوای دانلودی نرمالایز می‌شود: lowercase، trimmed، unique، sorted.

استفاده:
    python manage.py update_disposable_email_blocklist
    python manage.py update_disposable_email_blocklist --source <custom_url>
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import requests
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

logger = logging.getLogger("apps.authentication")


# منبع پیش‌فرض: یک repo community-maintained با ~12000+ دامنه
_DEFAULT_SOURCE_URL = (
    "https://raw.githubusercontent.com/disposable-email-domains/"
    "disposable-email-domains/master/disposable_email_blocklist.conf"
)

_TARGET_PATH = (
    Path(settings.BASE_DIR) / "apps" / "authentication" / "data" / "disposable_email_domains.txt"
)


class Command(BaseCommand):
    """Management command entrypoint for this maintenance workflow."""

    help = "Update the local blocklist of disposable email domains from a remote source."

    def add_arguments(self, parser) -> None:
        parser.add_argument(
            "--source",
            type=str,
            default=_DEFAULT_SOURCE_URL,
            help="URL to fetch the blocklist from (one domain per line).",
        )
        parser.add_argument(
            "--timeout",
            type=int,
            default=30,
            help="HTTP timeout in seconds.",
        )

    def handle(self, *args: Any, **options: Any) -> None:
        source: str = options["source"]
        timeout: int = options["timeout"]

        self.stdout.write(f"Fetching disposable-email blocklist from: {source}")

        try:
            response = requests.get(source, timeout=timeout)
            response.raise_for_status()
        except requests.RequestException as exc:
            raise CommandError(f"Failed to fetch blocklist: {exc}") from exc

        raw_lines = response.text.splitlines()
        normalized = self._normalize(raw_lines)

        if not normalized:
            raise CommandError(
                "Blocklist source returned no usable domains. Aborting to avoid wiping local file.",
            )

        self._atomic_write(_TARGET_PATH, normalized)

        self.stdout.write(
            self.style.SUCCESS(
                f"Updated blocklist with {len(normalized)} domains at {_TARGET_PATH}.",
            )
        )

    @staticmethod
    def _normalize(raw_lines: list[str]) -> list[str]:
        """
        نرمالایز کردن خطوط دانلودی:
        - حذف whitespace
        - lowercase
        - حذف comment ها (با # شروع می‌شوند)
        - حذف خطوط خالی
        - یکتاسازی + مرتب‌سازی
        """
        cleaned: set[str] = set()
        for raw in raw_lines:
            line = raw.strip().lower()
            if not line or line.startswith("#"):
                continue
            # یک بررسی sanity ساده روی دامنه (شامل نقطه باشد)
            if "." not in line:
                continue
            cleaned.add(line)
        return sorted(cleaned)

    @staticmethod
    def _atomic_write(target: Path, domains: list[str]) -> None:
        """
        نوشتن atomic روی فایل blocklist:
        - اول در یک temp file نوشته می‌شود
        - سپس rename می‌شود تا فایل قبلی never-corrupted باقی بماند
        """
        target.parent.mkdir(parents=True, exist_ok=True)
        tmp = target.with_suffix(target.suffix + ".tmp")
        content = "\n".join(domains) + "\n"
        tmp.write_text(content, encoding="utf-8")
        tmp.replace(target)

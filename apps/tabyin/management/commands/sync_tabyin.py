"""
Management command برای اجرای همگام‌سازی محتوای تبیین.

Usage:
    python manage.py sync_tabyin --mode=full
    python manage.py sync_tabyin --mode=incremental
    python manage.py sync_tabyin  (default: incremental)
"""

import logging
import sys

from django.core.management.base import BaseCommand, CommandParser

from apps.tabyin.providers import get_tabyin_provider
from apps.tabyin.sync.engine import SyncEngine

logger = logging.getLogger("tabyin.sync")


class Command(BaseCommand):
    """Management command entrypoint for this maintenance workflow."""

    help = "همگام‌سازی محتوای جهاد تبیین از سایت محتوانگار"

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument(
            "--mode",
            type=str,
            choices=["full", "incremental"],
            default="incremental",
            help="حالت همگام‌سازی: full (همه صفحات) یا incremental (فقط تغییرات اخیر)",
        )
        parser.add_argument(
            "--verbose",
            action="store_true",
            help="نمایش لاگ‌های بیشتر (DEBUG level)",
        )

    def handle(self, *args: object, **options: dict) -> None:
        mode = options["mode"]
        verbose = options["verbose"]

        # تنظیم سطح لاگ
        if verbose:
            logging.getLogger("tabyin").setLevel(logging.DEBUG)

        self.stdout.write(self.style.NOTICE(f"🔄 Starting {mode} sync..."))

        try:
            with get_tabyin_provider() as provider:
                engine = SyncEngine(provider=provider)

                if mode == "full":
                    stats = engine.sync_full()
                else:
                    stats = engine.sync_incremental()

            # نمایش نتیجه
            self.stdout.write("")
            self.stdout.write(self.style.SUCCESS("=" * 60))
            self.stdout.write(self.style.SUCCESS(f"✅ {stats.summary()}"))
            self.stdout.write(self.style.SUCCESS("=" * 60))

            if stats.errors > 0:
                self.stdout.write(self.style.WARNING(f"⚠️  {stats.errors} errors occurred"))

        except KeyboardInterrupt:
            self.stdout.write(self.style.ERROR("\n❌ Sync interrupted by user"))
            sys.exit(1)
        except Exception as e:
            logger.exception("Sync failed with unexpected error")
            self.stdout.write(self.style.ERROR(f"❌ Sync failed: {e}"))
            sys.exit(1)

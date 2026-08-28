"""Export tamper-verified audit logs as a forensic package."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.utils.dateparse import parse_datetime

from apps.audit_logs.chain import AuditChainVerificationError
from apps.audit_logs.exporters import AuditExportFilters, export_audit_package_to_path


class Command(BaseCommand):
    """Create ZIP package containing JSONL, CSV, XLSX and manifest files."""

    help = "Export audit logs as a tamper-verified forensic package."

    def add_arguments(self, parser) -> None:
        parser.add_argument(
            "--output",
            default=str(Path(settings.AUDIT_LOG_ARCHIVE_ROOT)),
            help="Output ZIP path or directory. Defaults to AUDIT_LOG_ARCHIVE_ROOT.",
        )
        parser.add_argument("--action", default=None)
        parser.add_argument("--user-id", type=int, default=None)
        parser.add_argument("--resource-type", default=None)
        parser.add_argument("--resource-id", default=None)
        parser.add_argument("--request-id", default=None)
        parser.add_argument("--ip-address", default=None)
        parser.add_argument("--method", default=None)
        parser.add_argument("--path", default=None)
        parser.add_argument("--created-after", default=None, help="ISO 8601 datetime.")
        parser.add_argument("--created-before", default=None, help="ISO 8601 datetime.")
        parser.add_argument("--search", default=None)
        parser.add_argument(
            "--no-audit-event",
            action="store_true",
            help="Do not append AUDIT_PACKAGE_EXPORTED event. Intended only for controlled tests.",
        )

    def handle(self, *args: Any, **options: Any) -> None:
        try:
            filters = AuditExportFilters(
                action=options["action"],
                user_id=options["user_id"],
                resource_type=options["resource_type"],
                resource_id=options["resource_id"],
                request_id=options["request_id"],
                ip_address=options["ip_address"],
                method=options["method"],
                path=options["path"],
                created_after=_parse_optional_datetime(options["created_after"], "created-after"),
                created_before=_parse_optional_datetime(
                    options["created_before"], "created-before"
                ),
                search=options["search"],
            )
            package = export_audit_package_to_path(
                output_path=options["output"],
                filters=filters,
                record_export_event=not options["no_audit_event"],
            )
        except AuditChainVerificationError as exc:
            raise CommandError(str(exc)) from exc
        except ValueError as exc:
            raise CommandError(str(exc)) from exc

        self.stdout.write(
            self.style.SUCCESS(
                "Audit forensic package exported successfully. "
                f"filename={package.filename} size_bytes={package.size_bytes} sha256={package.sha256}",
            ),
        )


def _parse_optional_datetime(value: str | None, option_name: str):
    """Parse optional ISO datetime CLI values with explicit error context."""
    if not value:
        return None
    parsed = parse_datetime(value)
    if parsed is None:
        raise ValueError(f"Invalid --{option_name}; expected ISO 8601 datetime.")
    return parsed

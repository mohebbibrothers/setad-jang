"""Render non-destructive audit-log retention report."""

from __future__ import annotations

import json
from typing import Any

from django.core.management.base import BaseCommand

from apps.audit_logs.retention import build_audit_retention_report


class Command(BaseCommand):
    """Report retention/archive status without deleting audit records."""

    help = "Build a non-destructive audit-log retention report."

    def handle(self, *args: Any, **options: Any) -> None:
        report = build_audit_retention_report()
        self.stdout.write(json.dumps(report, ensure_ascii=False, sort_keys=True, indent=2))

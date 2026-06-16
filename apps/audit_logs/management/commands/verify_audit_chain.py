"""Verify tamper-evident audit log hash chain."""

from __future__ import annotations

from django.core.management.base import BaseCommand, CommandError

from apps.audit_logs.models import AuditLog


class Command(BaseCommand):
    """Verify AuditLog previous_hash/event_hash chain integrity."""

    help = "Verify tamper-evident audit log hash chain integrity."

    def handle(self, *args, **options) -> None:
        previous_hash = "0" * 64
        checked = 0
        for audit in AuditLog.all_objects.order_by("created_at", "id"):
            if audit.previous_hash != previous_hash:
                raise CommandError(
                    f"Audit chain broken at id={audit.pk}: previous_hash mismatch."
                )
            expected = audit.compute_event_hash(previous_hash=previous_hash)
            if audit.event_hash != expected:
                raise CommandError(
                    f"Audit chain broken at id={audit.pk}: event_hash mismatch."
                )
            previous_hash = audit.event_hash
            checked += 1
        self.stdout.write(self.style.SUCCESS(f"Audit chain verified successfully. checked={checked}"))

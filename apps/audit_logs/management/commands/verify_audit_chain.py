"""Verify tamper-evident audit log hash chain."""

from __future__ import annotations

from django.core.management.base import BaseCommand, CommandError

from apps.audit_logs.chain import AuditChainVerificationError, verify_audit_chain_integrity


class Command(BaseCommand):
    """Verify AuditLog previous_hash/event_hash chain integrity."""

    help = "Verify tamper-evident audit log hash chain integrity."

    def handle(self, *args, **options) -> None:
        try:
            result = verify_audit_chain_integrity()
        except AuditChainVerificationError as exc:
            raise CommandError(str(exc)) from exc
        self.stdout.write(
            self.style.SUCCESS(
                "Audit chain verified successfully. "
                f"checked={result.checked} head_hash={result.head_hash}",
            ),
        )

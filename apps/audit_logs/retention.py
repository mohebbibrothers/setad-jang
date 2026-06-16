"""Retention-policy helpers for append-only audit logs."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from django.conf import settings
from django.utils import timezone

from .models import AuditLog


@dataclass(frozen=True)
class AuditRetentionPolicy:
    """Runtime audit retention policy exposed in exports and runbooks."""

    retention_days: int
    legal_hold_enabled: bool
    deletion_enabled: bool
    archive_root: str
    note: str

    def as_dict(self) -> dict[str, Any]:
        """Return a JSON-serializable policy snapshot."""
        return {
            "retention_days": self.retention_days,
            "legal_hold_enabled": self.legal_hold_enabled,
            "deletion_enabled": self.deletion_enabled,
            "archive_root": self.archive_root,
            "note": self.note,
        }


def get_audit_retention_policy() -> AuditRetentionPolicy:
    """Read audit retention settings with conservative production defaults."""
    retention_days = int(getattr(settings, "AUDIT_LOG_RETENTION_DAYS", 2555))
    legal_hold_enabled = bool(getattr(settings, "AUDIT_LOG_LEGAL_HOLD_ENABLED", True))
    deletion_enabled = bool(getattr(settings, "AUDIT_LOG_RETENTION_DELETE_ENABLED", False))
    archive_root = str(getattr(settings, "AUDIT_LOG_ARCHIVE_ROOT", settings.BASE_DIR / "audit_exports"))
    note = (
        "Audit logs are append-only. Retention automation is archive-first and does not delete "
        "records unless AUDIT_LOG_RETENTION_DELETE_ENABLED is explicitly enabled by operations."
    )
    return AuditRetentionPolicy(
        retention_days=retention_days,
        legal_hold_enabled=legal_hold_enabled,
        deletion_enabled=deletion_enabled,
        archive_root=archive_root,
        note=note,
    )


def build_audit_retention_report() -> dict[str, Any]:
    """Build a non-destructive retention report for operations and compliance."""
    policy = get_audit_retention_policy()
    cutoff = timezone.now() - timezone.timedelta(days=policy.retention_days)
    eligible_queryset = AuditLog.all_objects.filter(created_at__lt=cutoff)
    oldest = AuditLog.all_objects.order_by("created_at", "id").first()
    newest = AuditLog.all_objects.order_by("-created_at", "-id").first()
    return {
        "generated_at": timezone.now().isoformat(),
        "policy": policy.as_dict(),
        "cutoff": cutoff.isoformat(),
        "eligible_for_archive_count": eligible_queryset.count(),
        "total_count": AuditLog.all_objects.count(),
        "oldest_created_at": oldest.created_at.isoformat() if oldest else None,
        "newest_created_at": newest.created_at.isoformat() if newest else None,
        "destructive_deletion_performed": False,
    }

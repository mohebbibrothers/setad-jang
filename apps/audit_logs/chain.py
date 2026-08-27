"""Forensic verification utilities for the audit-log hash chain."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from django.utils import timezone

from .models import GENESIS_HASH, AuditLog


class AuditChainVerificationError(RuntimeError):
    """Raised when the tamper-evident audit chain is broken."""

    def __init__(self, *, audit_log_id: int | None, reason: str, checked: int) -> None:
        self.audit_log_id = audit_log_id
        self.reason = reason
        self.checked = checked
        super().__init__(self._build_message())

    def _build_message(self) -> str:
        if self.audit_log_id is None:
            return f"Audit chain verification failed: {self.reason}. checked={self.checked}"
        return (
            f"Audit chain verification failed at id={self.audit_log_id}: "
            f"{self.reason}. checked={self.checked}"
        )


@dataclass(frozen=True)
class AuditChainVerificationResult:
    """Immutable summary of a successful audit-chain verification run."""

    verified: bool
    checked: int
    head_hash: str
    verified_at: str
    hash_version: int

    def as_dict(self) -> dict[str, Any]:
        """Return JSON-serializable representation for manifests and APIs."""
        return {
            "verified": self.verified,
            "checked": self.checked,
            "head_hash": self.head_hash,
            "verified_at": self.verified_at,
            "hash_version": self.hash_version,
        }


def verify_audit_chain_integrity() -> AuditChainVerificationResult:
    """
    Verify the full append-only audit-log hash chain.

    The verification is intentionally full-chain, not filtered, because forensic
    exports must prove the complete trail was intact before packaging any slice
    of records for incident response, legal hold, or compliance review.

    ترتیب پیمایش روی `chain_index` است، نه `created_at`. دلیل: `created_at`
    یک برچسب زمانی است و می‌تواند برای دو رکورد یکسان باشد یا با انحراف ساعت
    جابه‌جا شود؛ ولی `chain_index` همان ترتیبی است که هش‌ها بر اساس آن بسته
    شده‌اند و در سطح دیتابیس یکتاست. علاوه بر آن، این ستون ایندکس دارد.
    """
    previous_hash = GENESIS_HASH
    checked = 0
    hash_version = 1

    for audit in AuditLog.all_objects.order_by("chain_index", "id").iterator(chunk_size=2000):
        if audit.previous_hash != previous_hash:
            raise AuditChainVerificationError(
                audit_log_id=audit.pk,
                reason="previous_hash mismatch",
                checked=checked,
            )
        expected = audit.compute_event_hash(previous_hash=previous_hash)
        if audit.event_hash != expected:
            raise AuditChainVerificationError(
                audit_log_id=audit.pk,
                reason="event_hash mismatch",
                checked=checked,
            )
        previous_hash = audit.event_hash
        checked += 1
        hash_version = audit.hash_version

    return AuditChainVerificationResult(
        verified=True,
        checked=checked,
        head_hash=previous_hash,
        verified_at=timezone.now().isoformat(),
        hash_version=hash_version,
    )

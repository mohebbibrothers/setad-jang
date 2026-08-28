"""
Logging utilities for authentication privacy hygiene.

Authentication flows naturally handle sensitive identifiers such as email addresses
and phone numbers. Logs must stay useful for debugging and incident response, but
must not store full PII values. This module centralizes deterministic masking so
all auth services use the same redaction policy.
"""

from __future__ import annotations

from apps.authentication.models import PrimaryIdentifierKind


def mask_identifier(identifier: str | None, *, identifier_kind: str | None = None) -> str:
    """
    Mask an email/phone/general identifier for safe logs.

    Args:
        identifier: Raw or normalized identifier value.
        identifier_kind: Optional explicit kind (`email` or `phone`). If omitted,
            a best-effort detection based on the value is used.

    Returns:
        A deterministic masked string that preserves enough shape for debugging
        without exposing the complete identifier.
    """
    if identifier is None:
        return "<none>"

    value = str(identifier).strip()
    if not value:
        return "<blank>"

    if identifier_kind == PrimaryIdentifierKind.EMAIL or (identifier_kind is None and "@" in value):
        return _mask_email(value)

    if identifier_kind == PrimaryIdentifierKind.PHONE or (
        identifier_kind is None and value.startswith("+") and value[1:].isdigit()
    ):
        return _mask_phone(value)

    return _mask_generic(value)


def _mask_email(value: str) -> str:
    """Mask an email while preserving a small amount of local/domain context."""
    local, separator, domain = value.partition("@")
    if not separator:
        return _mask_generic(value)

    visible_local = local[:2] if len(local) >= 2 else local[:1]
    domain_parts = domain.split(".")
    domain_head = domain_parts[0] if domain_parts else ""
    domain_suffix = ".".join(domain_parts[1:]) if len(domain_parts) > 1 else ""
    visible_domain = domain_head[:2] if domain_head else ""

    masked = f"{visible_local}***@{visible_domain}***"
    if domain_suffix:
        masked = f"{masked}.{domain_suffix}"
    return masked


def _mask_phone(value: str) -> str:
    """Mask a phone number while preserving country prefix and last digits."""
    if len(value) <= 6:
        return "***"
    return f"{value[:4]}***{value[-2:]}"


def _mask_generic(value: str) -> str:
    """Mask a non-email/non-phone identifier."""
    if len(value) <= 4:
        return "***"
    return f"{value[:2]}***{value[-2:]}"

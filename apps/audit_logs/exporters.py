"""Forensic export package builder for audit logs."""

from __future__ import annotations

import csv
import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime
from io import BytesIO, StringIO
from pathlib import Path
from typing import Any
from zipfile import ZIP_DEFLATED, ZipFile

from django.conf import settings
from django.db.models import QuerySet
from django.utils import timezone
from openpyxl import Workbook

from . import actions as audit_actions
from .chain import AuditChainVerificationResult, verify_audit_chain_integrity
from .models import AuditLog
from .retention import get_audit_retention_policy
from .services import create_audit_log

DANGEROUS_SPREADSHEET_PREFIXES = ("=", "+", "-", "@")
EXPORT_SCHEMA_VERSION = "audit-forensic-package/v1"


@dataclass(frozen=True)
class AuditExportFilters:
    """Supported audit export filters shared by API and management command."""

    action: str | None = None
    user_id: int | None = None
    resource_type: str | None = None
    resource_id: str | None = None
    request_id: str | None = None
    ip_address: str | None = None
    method: str | None = None
    path: str | None = None
    created_after: datetime | None = None
    created_before: datetime | None = None
    search: str | None = None

    def as_dict(self) -> dict[str, Any]:
        """Return JSON-serializable filter snapshot."""
        return {
            "action": self.action,
            "user_id": self.user_id,
            "resource_type": self.resource_type,
            "resource_id": self.resource_id,
            "request_id": self.request_id,
            "ip_address": self.ip_address,
            "method": self.method,
            "path": self.path,
            "created_after": self.created_after.isoformat() if self.created_after else None,
            "created_before": self.created_before.isoformat() if self.created_before else None,
            "search": self.search,
        }


@dataclass(frozen=True)
class AuditExportPackage:
    """Generated forensic package bytes plus manifest metadata."""

    content: bytes
    manifest: dict[str, Any]
    filename: str
    sha256: str = field(init=False)
    size_bytes: int = field(init=False)

    def __post_init__(self) -> None:
        object.__setattr__(self, "sha256", hashlib.sha256(self.content).hexdigest())
        object.__setattr__(self, "size_bytes", len(self.content))


def build_audit_export_queryset(filters: AuditExportFilters) -> QuerySet[AuditLog]:
    """Build a chronological export queryset from validated filter values."""
    queryset = AuditLog.all_objects.select_related("user").order_by("created_at", "id")
    if filters.action:
        queryset = queryset.filter(action=filters.action)
    if filters.user_id is not None:
        queryset = queryset.filter(user_id=filters.user_id)
    if filters.resource_type:
        queryset = queryset.filter(resource_type=filters.resource_type)
    if filters.resource_id:
        queryset = queryset.filter(resource_id=filters.resource_id)
    if filters.request_id:
        queryset = queryset.filter(request_id=filters.request_id)
    if filters.ip_address:
        queryset = queryset.filter(ip_address=filters.ip_address)
    if filters.method:
        queryset = queryset.filter(method__iexact=filters.method)
    if filters.path:
        queryset = queryset.filter(path__icontains=filters.path)
    if filters.created_after:
        queryset = queryset.filter(created_at__gte=filters.created_after)
    if filters.created_before:
        queryset = queryset.filter(created_at__lte=filters.created_before)
    if filters.search:
        from django.db.models import Q

        queryset = queryset.filter(
            Q(action__icontains=filters.search)
            | Q(resource_type__icontains=filters.search)
            | Q(resource_id__icontains=filters.search)
            | Q(path__icontains=filters.search),
        )
    return queryset


def build_audit_export_package(
    *,
    filters: AuditExportFilters | None = None,
    actor_user_id: int | None = None,
    actor_ip_address: str | None = None,
    actor_request_id: str | None = None,
    actor_user_agent: str = "",
    actor_path: str = "",
    actor_method: str = "",
    record_export_event: bool = True,
) -> AuditExportPackage:
    """
    Build a tamper-verified forensic audit export package.

    Security sequence:
    1. Verify the full hash chain before export.
    2. Append an AUDIT_PACKAGE_EXPORTED audit event for traceability.
    3. Verify the full hash chain again and embed that result in manifest.
    4. Package JSONL, CSV, XLSX, and manifest with per-file SHA-256 hashes.
    """
    export_filters = filters or AuditExportFilters()
    verify_audit_chain_integrity()

    if record_export_event:
        create_audit_log(
            user_id=actor_user_id,
            action=audit_actions.AUDIT_PACKAGE_EXPORTED,
            resource_type="audit_log",
            resource_id=None,
            ip_address=actor_ip_address,
            request_id=actor_request_id,
            user_agent=actor_user_agent,
            path=actor_path,
            method=actor_method,
            extra_data={
                "filters": export_filters.as_dict(),
                "formats": ["jsonl", "csv", "xlsx"],
                "trigger": "admin_api" if actor_request_id or actor_path else "management_command",
            },
        )

    chain_result = verify_audit_chain_integrity()
    max_records = int(getattr(settings, "AUDIT_LOG_EXPORT_MAX_RECORDS", 100000))
    queryset = build_audit_export_queryset(export_filters)
    total_records = queryset.count()
    if total_records > max_records:
        raise ValueError(
            f"Audit export record count {total_records} exceeds AUDIT_LOG_EXPORT_MAX_RECORDS={max_records}."
        )

    records = [_serialize_audit_log(audit) for audit in queryset]
    generated_at = timezone.now().isoformat()
    base_filename = f"audit-forensic-package-{timezone.now().strftime('%Y%m%dT%H%M%SZ')}"

    files: dict[str, bytes] = {
        "audit_logs.jsonl": _render_jsonl(records),
        "audit_logs.csv": _render_csv(records),
        "audit_logs.xlsx": _render_xlsx(records),
    }
    file_manifest = {
        filename: {
            "sha256": hashlib.sha256(content).hexdigest(),
            "size_bytes": len(content),
        }
        for filename, content in files.items()
    }
    manifest = _build_manifest(
        generated_at=generated_at,
        filters=export_filters,
        chain_result=chain_result,
        record_count=len(records),
        file_manifest=file_manifest,
    )
    manifest_bytes = _json_bytes(manifest)
    files["manifest.json"] = manifest_bytes

    package_io = BytesIO()
    with ZipFile(package_io, mode="w", compression=ZIP_DEFLATED) as archive:
        for filename in sorted(files):
            archive.writestr(filename, files[filename])

    return AuditExportPackage(
        content=package_io.getvalue(),
        manifest=manifest,
        filename=f"{base_filename}.zip",
    )


def export_audit_package_to_path(
    *,
    output_path: str | Path,
    filters: AuditExportFilters | None = None,
    record_export_event: bool = True,
) -> AuditExportPackage:
    """Build and persist a forensic package to an explicit filesystem path."""
    package = build_audit_export_package(
        filters=filters,
        record_export_event=record_export_event,
    )
    destination = Path(output_path)
    if destination.is_dir() or destination.suffix.lower() != ".zip":
        destination = destination / package.filename
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_bytes(package.content)
    return package


def _serialize_audit_log(audit: AuditLog) -> dict[str, Any]:
    """Serialize one AuditLog into the canonical forensic JSON structure."""
    user = audit.user
    return {
        "id": audit.pk,
        "created_at": audit.created_at.isoformat(),
        "user": None
        if user is None
        else {
            "id": user.pk,
            "email": user.email,
            "full_name": getattr(user, "full_name", ""),
        },
        "action": audit.action,
        "resource_type": audit.resource_type,
        "resource_id": audit.resource_id,
        "ip_address": audit.ip_address,
        "request_id": audit.request_id,
        "user_agent": audit.user_agent,
        "path": audit.path,
        "method": audit.method,
        "changes": audit.changes,
        "extra_data": audit.extra_data,
        "previous_hash": audit.previous_hash,
        "event_hash": audit.event_hash,
        "hash_version": audit.hash_version,
    }


def _build_manifest(
    *,
    generated_at: str,
    filters: AuditExportFilters,
    chain_result: AuditChainVerificationResult,
    record_count: int,
    file_manifest: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    """Build the package manifest consumed by investigators and auditors."""
    return {
        "schema_version": EXPORT_SCHEMA_VERSION,
        "generated_at": generated_at,
        "record_count": record_count,
        "filters": filters.as_dict(),
        "chain_verification": chain_result.as_dict(),
        "retention_policy": get_audit_retention_policy().as_dict(),
        "files": file_manifest,
        "integrity_note": (
            "Validate each file against its SHA-256 digest in this manifest. "
            "The package was generated only after full audit hash-chain verification."
        ),
    }


def _json_bytes(payload: Any) -> bytes:
    """Encode manifest JSON with stable ordering and UTF-8 output."""
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2).encode("utf-8")


def _render_jsonl(records: list[dict[str, Any]]) -> bytes:
    """Render newline-delimited JSON for SIEM and incident-response tooling."""
    lines = [
        json.dumps(record, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        for record in records
    ]
    return ("\n".join(lines) + ("\n" if lines else "")).encode("utf-8")


def _render_csv(records: list[dict[str, Any]]) -> bytes:
    """Render spreadsheet-safe UTF-8-SIG CSV for analysts."""
    output = StringIO()
    fieldnames = _export_fieldnames()
    writer = csv.DictWriter(output, fieldnames=fieldnames, extrasaction="ignore")
    writer.writeheader()
    for record in records:
        writer.writerow(_flatten_record_for_table(record))
    return output.getvalue().encode("utf-8-sig")


def _render_xlsx(records: list[dict[str, Any]]) -> bytes:
    """Render XLSX workbook for offline forensic review."""
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "audit_logs"
    fieldnames = _export_fieldnames()
    sheet.append(fieldnames)
    for record in records:
        flattened = _flatten_record_for_table(record)
        sheet.append([flattened[field] for field in fieldnames])

    workbook_io = BytesIO()
    workbook.save(workbook_io)
    return workbook_io.getvalue()


def _export_fieldnames() -> list[str]:
    """Return the stable tabular column order for CSV/XLSX exports."""
    return [
        "id",
        "created_at",
        "user_id",
        "user_email",
        "user_full_name",
        "action",
        "resource_type",
        "resource_id",
        "ip_address",
        "request_id",
        "user_agent",
        "path",
        "method",
        "changes",
        "extra_data",
        "previous_hash",
        "event_hash",
        "hash_version",
    ]


def _flatten_record_for_table(record: dict[str, Any]) -> dict[str, Any]:
    """Flatten nested JSON export rows into spreadsheet-friendly columns."""
    user = record.get("user") or {}
    flattened = {
        **record,
        "user_id": user.get("id"),
        "user_email": user.get("email"),
        "user_full_name": user.get("full_name"),
        "changes": json.dumps(record.get("changes"), ensure_ascii=False, sort_keys=True),
        "extra_data": json.dumps(record.get("extra_data"), ensure_ascii=False, sort_keys=True),
    }
    flattened.pop("user", None)
    return {key: _safe_spreadsheet_value(value) for key, value in flattened.items()}


def _safe_spreadsheet_value(value: Any) -> Any:
    """Neutralize CSV/XLSX formula injection while preserving readable values."""
    if not isinstance(value, str):
        return value
    if value.startswith(DANGEROUS_SPREADSHEET_PREFIXES):
        return f"'{value}"
    return value

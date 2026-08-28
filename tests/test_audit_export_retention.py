"""Audit Phase C2 tests: forensic export package and retention policy."""

from __future__ import annotations

import csv
import json
from io import BytesIO, StringIO
from pathlib import Path
from zipfile import ZipFile

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError
from django.db import connection
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken

from apps.audit_logs.actions import AUDIT_PACKAGE_EXPORTED, LOGIN_SUCCESS, LOGOUT
from apps.audit_logs.chain import AuditChainVerificationError
from apps.audit_logs.exporters import AuditExportFilters, build_audit_export_package
from apps.audit_logs.models import AuditLog
from apps.audit_logs.retention import build_audit_retention_report, get_audit_retention_policy
from apps.audit_logs.services import create_audit_log
from tests.factories.auth import AdminUserFactory

pytestmark = pytest.mark.django_db


def _zip_files(package_bytes: bytes) -> dict[str, bytes]:
    with ZipFile(BytesIO(package_bytes)) as archive:
        return {name: archive.read(name) for name in archive.namelist()}


def test_forensic_export_package_contains_manifest_jsonl_csv_and_xlsx() -> None:
    """Export package should be archive-ready and include integrity manifest."""
    first = create_audit_log(action=LOGIN_SUCCESS, resource_type="user", resource_id="1")
    create_audit_log(action=LOGOUT, resource_type="user", resource_id="1")

    package = build_audit_export_package(
        filters=AuditExportFilters(action=LOGIN_SUCCESS),
        record_export_event=False,
    )

    files = _zip_files(package.content)
    assert set(files) == {"audit_logs.csv", "audit_logs.jsonl", "audit_logs.xlsx", "manifest.json"}

    manifest = json.loads(files["manifest.json"].decode("utf-8"))
    assert manifest["schema_version"] == "audit-forensic-package/v1"
    assert manifest["record_count"] == 1
    assert manifest["filters"]["action"] == LOGIN_SUCCESS
    assert manifest["chain_verification"]["verified"] is True
    assert manifest["chain_verification"]["checked"] == 2
    assert (
        manifest["chain_verification"]["head_hash"]
        == AuditLog.objects.order_by("-created_at", "-id").first().event_hash
    )
    assert "retention_policy" in manifest

    jsonl_rows = [
        json.loads(line) for line in files["audit_logs.jsonl"].decode("utf-8").splitlines()
    ]
    assert [row["id"] for row in jsonl_rows] == [first.pk]
    assert jsonl_rows[0]["event_hash"] == first.event_hash

    csv_text = files["audit_logs.csv"].decode("utf-8-sig")
    csv_rows = list(csv.DictReader(StringIO(csv_text)))
    assert csv_rows[0]["action"] == LOGIN_SUCCESS
    assert csv_rows[0]["event_hash"] == first.event_hash
    assert files["audit_logs.xlsx"].startswith(b"PK")


def test_forensic_export_records_sensitive_export_event_by_default() -> None:
    """Audit export itself is a sensitive action and must be audit logged."""
    create_audit_log(action=LOGIN_SUCCESS, resource_type="user", resource_id="1")

    package = build_audit_export_package(filters=AuditExportFilters(search="LOGIN"))

    export_log = AuditLog.objects.get(action=AUDIT_PACKAGE_EXPORTED)
    assert export_log.resource_type == "audit_log"
    assert export_log.extra_data["formats"] == ["jsonl", "csv", "xlsx"]
    assert export_log.extra_data["filters"]["search"] == "LOGIN"

    manifest = json.loads(_zip_files(package.content)["manifest.json"].decode("utf-8"))
    assert manifest["chain_verification"]["checked"] == 2


def test_forensic_export_refuses_tampered_chain() -> None:
    """Package generation must fail when direct database tampering breaks hashes."""
    audit = create_audit_log(action=LOGIN_SUCCESS, resource_type="user", resource_id="1")
    with connection.cursor() as cursor:
        cursor.execute(
            "UPDATE audit_logs_auditlog SET action = %s WHERE id = %s",
            [LOGOUT, audit.pk],
        )

    with pytest.raises(AuditChainVerificationError, match="event_hash mismatch"):
        build_audit_export_package(record_export_event=False)


def test_export_management_command_writes_package_to_directory(tmp_path: Path) -> None:
    """Management command should persist a verified package under the output directory."""
    create_audit_log(action=LOGIN_SUCCESS, resource_type="user", resource_id="1")
    output = StringIO()

    call_command(
        "export_audit_package",
        output=str(tmp_path),
        no_audit_event=True,
        stdout=output,
    )

    packages = list(tmp_path.glob("audit-forensic-package-*.zip"))
    assert len(packages) == 1
    assert packages[0].read_bytes().startswith(b"PK")
    assert "Audit forensic package exported successfully" in output.getvalue()


def test_export_management_command_refuses_invalid_datetime(tmp_path: Path) -> None:
    """Invalid date filters should fail loudly instead of creating ambiguous exports."""
    with pytest.raises(CommandError, match="Invalid --created-after"):
        call_command(
            "export_audit_package",
            output=str(tmp_path),
            created_after="not-a-date",
        )


def test_admin_export_endpoint_returns_zip_and_logs_export() -> None:
    """Admin API should orchestrate export only and return a ZIP response."""
    admin = AdminUserFactory()
    create_audit_log(action=LOGIN_SUCCESS, resource_type="user", resource_id="1")
    client = APIClient()
    refresh = RefreshToken.for_user(admin)
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {refresh.access_token!s}")

    response = client.get(
        reverse("audit_logs:admin-log-export"),
        data={"action": LOGIN_SUCCESS},
        HTTP_X_REQUEST_ID="audit-export-req-1",
    )

    assert response.status_code == status.HTTP_200_OK
    assert response["Content-Type"] == "application/zip"
    assert response["X-Audit-Package-SHA256"]
    files = _zip_files(response.content)
    manifest = json.loads(files["manifest.json"].decode("utf-8"))
    assert manifest["filters"]["action"] == LOGIN_SUCCESS
    assert AuditLog.objects.filter(
        action=AUDIT_PACKAGE_EXPORTED, request_id="audit-export-req-1"
    ).exists()


def test_admin_export_endpoint_rejects_invalid_date_range() -> None:
    """Query serializer should prevent inverted forensic date ranges."""
    admin = AdminUserFactory()
    client = APIClient()
    refresh = RefreshToken.for_user(admin)
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {refresh.access_token!s}")

    response = client.get(
        reverse("audit_logs:admin-log-export"),
        data={
            "created_after": "2026-06-16T12:00:00Z",
            "created_before": "2026-06-15T12:00:00Z",
        },
    )

    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert response.data["success"] is False


def test_retention_policy_is_archive_first_and_non_destructive(settings) -> None:
    """Retention policy should default to legal-hold/archive-first behavior."""
    settings.AUDIT_LOG_RETENTION_DAYS = 365
    settings.AUDIT_LOG_LEGAL_HOLD_ENABLED = True
    settings.AUDIT_LOG_RETENTION_DELETE_ENABLED = False
    create_audit_log(action=LOGIN_SUCCESS, resource_type="user", resource_id="1")

    policy = get_audit_retention_policy()
    report = build_audit_retention_report()

    assert policy.retention_days == 365
    assert policy.legal_hold_enabled is True
    assert policy.deletion_enabled is False
    assert report["destructive_deletion_performed"] is False
    assert report["total_count"] == 1

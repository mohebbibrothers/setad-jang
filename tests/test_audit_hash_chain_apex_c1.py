"""Audit Apex C1 tamper-evident hash chain tests."""

from __future__ import annotations

from io import StringIO

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError
from django.db import connection

from apps.audit_logs.actions import LOGIN_SUCCESS, LOGOUT
from apps.audit_logs.services import create_audit_log
from tests.factories import UserFactory

pytestmark = pytest.mark.django_db


def test_audit_logs_receive_previous_and_event_hashes() -> None:
    """New audit logs should be linked by previous_hash/event_hash."""
    user = UserFactory()
    first = create_audit_log(user_id=user.pk, action=LOGIN_SUCCESS, resource_type="user", resource_id=str(user.pk))
    second = create_audit_log(user_id=user.pk, action=LOGOUT, resource_type="user", resource_id=str(user.pk))

    assert first.previous_hash == "0" * 64
    assert first.event_hash == first.compute_event_hash(previous_hash=first.previous_hash)
    assert second.previous_hash == first.event_hash
    assert second.event_hash == second.compute_event_hash(previous_hash=second.previous_hash)


def test_verify_audit_chain_command_succeeds_for_intact_chain() -> None:
    """verify_audit_chain should pass for intact audit logs."""
    create_audit_log(action=LOGIN_SUCCESS, resource_type="user", resource_id="1")
    create_audit_log(action=LOGOUT, resource_type="user", resource_id="1")
    output = StringIO()

    call_command("verify_audit_chain", stdout=output)

    assert "Audit chain verified successfully" in output.getvalue()
    assert "checked=2" in output.getvalue()


def test_verify_audit_chain_detects_direct_database_tampering() -> None:
    """Direct DB tampering should break event_hash verification."""
    audit = create_audit_log(action=LOGIN_SUCCESS, resource_type="user", resource_id="1")

    with connection.cursor() as cursor:
        cursor.execute(
            "UPDATE audit_logs_auditlog SET action = %s WHERE id = %s",
            [LOGOUT, audit.pk],
        )

    with pytest.raises(CommandError, match="event_hash mismatch"):
        call_command("verify_audit_chain")


def test_audit_detail_serializer_exposes_hash_fields_for_forensic_review() -> None:
    """Audit API detail serializer should expose hash-chain evidence."""
    from apps.audit_logs.serializers import AuditLogDetailSerializer

    audit = create_audit_log(action=LOGIN_SUCCESS, resource_type="user", resource_id="1")

    data = AuditLogDetailSerializer(audit).data

    assert data["previous_hash"] == audit.previous_hash
    assert data["event_hash"] == audit.event_hash
    assert data["hash_version"] == 1
    assert len(data["event_hash"]) == 64

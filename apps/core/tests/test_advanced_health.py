"""Core C2 advanced health diagnostics tests."""

from __future__ import annotations

import pytest

from apps.audit_logs.services import create_audit_log
from apps.core.health.checks import (
    STATUS_DEGRADED,
    STATUS_OK,
    build_detailed_checks,
    check_audit_chain_quick,
    check_migration_state,
    check_performance_contracts,
)

pytestmark = pytest.mark.django_db


def test_detailed_health_includes_advanced_diagnostics(settings) -> None:
    """Detailed health should include advanced production diagnostics."""
    settings.PERFORMANCE_CONTRACTS = {"/api/v1/test/*": 100}
    checks = build_detailed_checks()

    assert "migration_state" in checks
    assert "media_storage" in checks
    assert "audit_chain_quick" in checks
    assert "performance_contracts" in checks
    assert checks["performance_contracts"]["contracts_count"] == 1


def test_migration_state_reports_current_migrations() -> None:
    """Migration diagnostic should be ok when test DB is fully migrated."""
    result = check_migration_state()

    assert result["status"] == STATUS_OK
    assert result["unapplied_migrations"] == 0
    assert "latency_ms" in result


def test_audit_chain_quick_checks_latest_hash() -> None:
    """Audit quick diagnostic should validate latest audit row hash."""
    create_audit_log(action="HEALTH_TEST", resource_type="health", resource_id="1")

    result = check_audit_chain_quick()

    assert result["status"] == STATUS_OK
    assert result["checked"] == 1
    assert len(result["head_hash_prefix"]) == 12


def test_performance_contracts_detect_invalid_budget(settings) -> None:
    """Performance diagnostics should degrade on invalid contract budgets."""
    settings.DEFAULT_PERFORMANCE_BUDGET_MS = 1000
    settings.PERFORMANCE_CONTRACTS = {"/api/v1/bad/*": 0}

    result = check_performance_contracts()

    assert result["status"] == STATUS_DEGRADED
    assert result["invalid_contracts_count"] == 1

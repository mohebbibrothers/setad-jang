"""Production Phase 6 runbook and operational documentation tests."""

from __future__ import annotations

from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
PRODUCTION_DOCS = PROJECT_ROOT / "docs" / "production"


def _read_doc(name: str) -> str:
    """Read a production runbook document."""
    path = PRODUCTION_DOCS / name
    assert path.exists(), f"Missing production runbook: {name}"
    return path.read_text(encoding="utf-8")


def test_all_production_runbooks_exist_and_are_substantial() -> None:
    """All required 10/10 production runbooks must exist."""
    required = [
        "ENVIRONMENT_MATRIX.md",
        "DEPLOYMENT_RUNBOOK.md",
        "BACKUP_RESTORE_RUNBOOK.md",
        "INCIDENT_RESPONSE_RUNBOOK.md",
        "SECRET_ROTATION_RUNBOOK.md",
        "RELEASE_CHECKLIST.md",
        "PRODUCTION_10_10_STATUS.md",
    ]
    for name in required:
        content = _read_doc(name)
        assert len(content.splitlines()) >= 30


def test_deployment_runbook_covers_verify_health_metrics_and_rollback() -> None:
    """Deployment runbook must cover preflight, health, metrics and rollback."""
    content = _read_doc("DEPLOYMENT_RUNBOOK.md")

    assert "make verify" in content
    assert "/api/v1/health/ready/" in content
    assert "/api/v1/metrics/" in content
    assert "Rollback" in content
    assert "Celery" in content


def test_backup_restore_runbook_covers_database_and_media() -> None:
    """Backup runbook must cover DB and object storage/media."""
    content = _read_doc("BACKUP_RESTORE_RUNBOOK.md")

    assert "pg_dump" in content
    assert "pg_restore" in content
    assert "Object storage" in content
    assert "aws s3 sync" in content
    assert "restore" in content.lower()


def test_secret_rotation_runbook_mentions_github_jwt_database_s3() -> None:
    """Secret rotation docs must cover the sensitive credentials we actually use."""
    content = _read_doc("SECRET_ROTATION_RUNBOOK.md")

    assert "GitHub" in content
    assert "JWT_SIGNING_KEY" in content
    assert "POSTGRES_PASSWORD" in content
    assert "AWS_ACCESS_KEY_ID" in content
    assert "EMAIL_HOST_PASSWORD" in content


def test_production_status_tracks_remaining_real_world_dependencies() -> None:
    """Final status doc must be honest about real-world provider dependencies."""
    content = _read_doc("PRODUCTION_10_10_STATUS.md")

    assert "SMS provider license" in content
    assert "Zarinpal merchant id" in content
    assert "Brevo" in content
    assert "Production object storage" in content


def test_readme_links_production_runbooks() -> None:
    """README must link the production runbook directory and key runbooks."""
    readme = (PROJECT_ROOT / "README.md").read_text(encoding="utf-8")

    assert "docs/production/DEPLOYMENT_RUNBOOK.md" in readme
    assert "docs/production/BACKUP_RESTORE_RUNBOOK.md" in readme
    assert "docs/production/PRODUCTION_10_10_STATUS.md" in readme

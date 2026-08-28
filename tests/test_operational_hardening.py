"""
Operational hardening tests for production-facing configuration.

این تست‌ها رفتارهای critical غیر-domain را پوشش می‌دهند؛ مواردی که اگر
در تست‌های معمول API دیده نشوند، در deployment واقعی می‌توانند باعث incident
شوند:
- production settings باید به‌صورت پیش‌فرض PostgreSQL را انتخاب کند.
- استفاده از SQLite در production باید fail-fast و explicit باشد.
- docker-compose worker باید تمام queueهای route‌شده را consume کند.
- dependencyهای production باید driver دیتابیس production را شامل شوند.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path
from typing import Any

import yaml

PROJECT_ROOT = Path(__file__).resolve().parent.parent


def _production_env(**overrides: str) -> dict[str, str]:
    """
    ساخت environment امن و self-contained برای import کردن production settings.

    این helper عمداً به `.env` واقعی وابسته نیست تا تست deterministic بماند.
    """
    env = os.environ.copy()
    env.update(
        {
            "ALLOWED_HOSTS": "127.0.0.1,localhost,testserver",
            "CACHE_BACKEND": "redis",
            "CORS_ALLOWED_ORIGINS": "",
            # صریحاً postgres تا تست مستقل از موتورِ محیط اجرا باشد: اگر pytest
            # زیر DATABASE_ENGINE=sqlite اجرا شود (مثلاً local)، subprocess
            # بدون این خط سراغ ردکردن SQLite می‌رفت و هرگز به بررسیِ
            # POSTGRES_PASSWORD نمی‌رسید — تست‌ها فقط در اجرای PostgreSQL
            # سبز می‌شدند (وابستگی پنهان به محیط). تستِ پیش‌فرضِ production
            # خودش این کلید را pop می‌کند.
            "DATABASE_ENGINE": "postgres",
            "DEBUG": "False",
            "DJANGO_SETTINGS_MODULE": "config.settings.production",
            "POSTGRES_CONNECT_TIMEOUT": "1",
            "POSTGRES_CONN_MAX_AGE": "0",
            "POSTGRES_DB": "setadjang_test",
            "POSTGRES_HOST": "127.0.0.1",
            "POSTGRES_PASSWORD": "test-postgres-password-not-for-production",
            "POSTGRES_PORT": "5432",
            "POSTGRES_USER": "setadjang_test",
            "SECRET_KEY": "production-test-secret-key-with-more-than-fifty-characters-2026",
            "SECURE_HSTS_SECONDS": "0",
            "SECURE_SSL_REDIRECT": "False",
        }
    )
    env.update(overrides)
    return env


def _run_manage_check(env: dict[str, str]) -> subprocess.CompletedProcess[str]:
    """اجرای `manage.py check` در subprocess مستقل برای تست production settings."""
    return subprocess.run(
        [
            sys.executable,
            "manage.py",
            "check",
            "--settings=config.settings.production",
        ],
        cwd=PROJECT_ROOT,
        env=env,
        capture_output=True,
        check=False,
        text=True,
        timeout=30,
    )


def _load_compose() -> dict[str, Any]:
    """خواندن docker-compose.yml به‌صورت YAML برای assertions ساختاری."""
    return yaml.safe_load((PROJECT_ROOT / "docker-compose.yml").read_text(encoding="utf-8"))


def test_production_settings_boot_with_postgresql_by_default() -> None:
    """Production settings باید بدون DATABASE_ENGINE صریح، PostgreSQL را انتخاب کند."""
    env = _production_env()
    env.pop("DATABASE_ENGINE", None)

    result = _run_manage_check(env)

    assert result.returncode == 0, result.stderr + result.stdout
    assert "System check identified no issues" in result.stdout


def test_production_settings_reject_sample_postgres_password() -> None:
    """production.py نباید با POSTGRES_PASSWORD نمونه یا خالی boot شود."""
    result = _run_manage_check(
        _production_env(
            POSTGRES_PASSWORD="change-me-postgres-password",
        )
    )

    assert result.returncode != 0
    assert "POSTGRES_PASSWORD" in result.stderr


def test_production_settings_reject_sqlite_without_explicit_escape_hatch() -> None:
    """SQLite در production بدون ALLOW_SQLITE_IN_PRODUCTION باید fail-fast شود."""
    result = _run_manage_check(
        _production_env(
            DATABASE_ENGINE="sqlite",
            ALLOW_SQLITE_IN_PRODUCTION="False",
        )
    )

    assert result.returncode != 0
    assert "SQLite در production" in result.stderr


def _queues_of(service_command: str) -> set[str]:
    """استخراج مجموعهٔ queueهای `-Q` از command یک سرویس celery worker."""
    assert "-Q" in service_command
    queue_arg = service_command[service_command.index("-Q") + 1]
    return set(queue_arg.split(","))


def test_docker_workers_consume_all_routed_celery_queues_exactly_once() -> None:
    """پس از یافتهٔ ممیزی ۵.۲، queueهای مسیر‌دار باید بین workerها تقسیم شوند.

    - هر queue دقیقاً یک مصرف‌کننده داشته باشد (consuming دوبارهٔ یک queue
      یعنی دو worker روی یک task رقابت می‌کنند و کار مضاعف می‌شود)؛
    - اتحاد queueهای همهٔ workerها دقیقاً همان queueهای روت‌شده در
      ``CELERY_TASK_ROUTES`` + پیش‌فرض باشد؛
    - flower به هر دو worker وابسته باشد تا monitoring کامل بماند.
    """
    compose = _load_compose()
    worker_services = {
        name: service
        for name, service in compose["services"].items()
        if "celery" in str(service.get("command", ""))
        and "worker" in str(service.get("command", ""))
    }

    assert set(worker_services) == {"worker", "madadkar-worker"}

    consumed_everywhere: list[str] = []
    for _name, service in worker_services.items():
        consumed_everywhere.extend(_queues_of(service["command"]))

    assert sorted(consumed_everywhere) == sorted(set(consumed_everywhere)), (
        "یک queue باید دقیقاً توسط یک worker مصرف شود؛ "
        f"تکرار: {[q for q in consumed_everywhere if consumed_everywhere.count(q) > 1]}"
    )
    assert set(consumed_everywhere) == {"default", "tabyin_sync", "madadkar"}

    # اتصال وابستگی‌های flower (مشاهدهٔ هر دو worker)
    flower_depends = compose["services"]["flower"]["depends_on"]
    assert "worker" in flower_depends
    assert "madadkar-worker" in flower_depends


def test_docker_compose_has_postgres_service_and_web_dependency() -> None:
    """docker-compose باید PostgreSQL healthcheck و dependency صریح برای web داشته باشد."""
    compose = _load_compose()

    assert "postgres" in compose["services"]
    postgres = compose["services"]["postgres"]
    assert postgres["image"].startswith("postgres:")
    assert "healthcheck" in postgres
    assert compose["services"]["web"]["depends_on"]["postgres"]["condition"] == "service_healthy"
    assert "postgres_data" in compose["volumes"]


def test_requirements_are_utf8_and_include_postgresql_driver() -> None:
    """requirements.txt باید UTF-8 باشد و driver رسمی PostgreSQL را داشته باشد."""
    requirements_bytes = (PROJECT_ROOT / "requirements.txt").read_bytes()
    requirements_text = requirements_bytes.decode("utf-8")

    assert not requirements_bytes.startswith((b"\xff\xfe", b"\xfe\xff"))
    assert "psycopg[binary]==" in requirements_text


def test_runtime_celerybeat_schedule_is_ignored_and_not_present() -> None:
    """فایل runtime celerybeat-schedule نباید دوباره وارد version control شود."""
    gitignore = (PROJECT_ROOT / ".gitignore").read_text(encoding="utf-8")

    assert "celerybeat-schedule" in gitignore
    assert not (PROJECT_ROOT / "celerybeat-schedule").exists()


def test_dockerfile_healthcheck_uses_readiness_endpoint() -> None:
    """Container healthcheck باید readiness را بسنجد، نه صرفاً liveness را."""
    dockerfile = (PROJECT_ROOT / "Dockerfile").read_text(encoding="utf-8")

    assert "/api/v1/health/ready/" in dockerfile

"""تست‌های دروازۀ سازگاری مهاجرت (یافتۀ P2-12/۱۴ فاز ۸).

گیت روی *مخزنِ gitِ موقتِ خودش* اجرا می‌شود — نه روی history واقعیِ مخزن —
تا deterministic و مستقل از هر commit تازه باشد. سه سناریو کافی‌اند چون
خودِ گیت عمداً heuristic است: پاک / ایندکسِ قفل‌کننده / RunPythonِ
برگشت‌ناپذیر + رفتارِ policyها (auto بر پایهٔ compose، ack، warn).
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPT = REPO_ROOT / "scripts" / "migration_compat.py"

CLEAN_MIGRATION = """
from django.db import migrations, models


class Migration(migrations.Migration):
    operations = [
        migrations.AddIndexConcurrently(
            model_name="thing",
            index=models.Index(fields=["a"], name="thing_a_idx"),
        ),
        migrations.RunPython(for_sql, migrations.RunPython.noop),
    ]
"""

BLOCKING_INDEX_MIGRATION = """
from django.db import migrations, models
from django.contrib.postgres.indexes import GinIndex


class Migration(migrations.Migration):
    operations = [
        migrations.AddIndex(
            model_name="thing",
            index=GinIndex(models.Func("search_vector"), name="thing_gin"),
        ),
    ]
"""

IRREVERSIBLE_DATA_MIGRATION = """
from django.db import migrations


def forwards(apps, schema_editor):
    pass


class Migration(migrations.Migration):
    operations = [
        migrations.RunPython(forwards),
    ]
"""


def _git(repo: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-c", "user.email=t@t", "-c", "user.name=t", *args],
        cwd=repo,
        check=True,
        capture_output=True,
        text=True,
    ).stdout


@pytest.fixture(name="tmp_repo")
def tmp_repo_fixture(tmp_path: Path) -> Path:
    """مخزنِ git تمیز با کامیتِ اولیه (بدون مایگریشن) و config محلی."""
    repo = tmp_path / "repo"
    (repo / "apps" / "x" / "migrations").mkdir(parents=True)
    (repo / "docker-compose.yml").write_text(
        'services:\n  web:\n    environment:\n      RUN_MIGRATIONS: "1"\n', encoding="utf-8"
    )
    _git(repo, "init", "-q")
    _git(repo, "add", ".")
    _git(repo, "commit", "-qm", "base")
    return repo


def _add_migration(repo: Path, body: str, name: str = "0002_auto.py") -> None:
    (repo / "apps" / "x" / "migrations" / name).write_text(body, encoding="utf-8")
    _git(repo, "add", ".")
    _git(repo, "commit", "-qm", "migration")


def _run(
    repo: Path, base_rev: str, *, policy: str = "auto", compose: str | None = "docker-compose.yml"
) -> subprocess.CompletedProcess[str]:
    args = [
        sys.executable,
        str(SCRIPT),
        "--repo",
        str(repo),
        "--from",
        base_rev,
        "--to",
        "HEAD",
        "--policy",
        policy,
    ]
    if compose:
        args += ["--compose-file", str(repo / compose)]
    return subprocess.run(args, capture_output=True, text=True, check=False)


def test_clean_migration_passes(tmp_repo: Path) -> None:
    """AddIndexConcurrently + RunPython(noop) → هیچ پرچمی نه در auto."""
    base = _git(tmp_repo, "rev-parse", "HEAD").strip()
    _add_migration(tmp_repo, CLEAN_MIGRATION)
    result = _run(tmp_repo, base)
    assert result.returncode == 0
    assert "پاک" in result.stdout


def test_blocking_index_gates_under_auto_policy(tmp_repo: Path) -> None:
    """GIN بدون CONCURRENTLY با compose فعال → exit 2 و توضیحِ گزینه‌ها."""
    base = _git(tmp_repo, "rev-parse", "HEAD").strip()
    _add_migration(tmp_repo, BLOCKING_INDEX_MIGRATION)
    result = _run(tmp_repo, base)
    assert result.returncode == 2
    assert "CONCURRENTLY" in result.stderr


def test_irreversible_runpython_gates(tmp_repo: Path) -> None:
    """RunPython بدون reverse → پرچمِ بازگشت‌ناپذیری."""
    base = _git(tmp_repo, "rev-parse", "HEAD").strip()
    _add_migration(tmp_repo, IRREVERSIBLE_DATA_MIGRATION)
    result = _run(tmp_repo, base)
    assert result.returncode == 2
    assert "reverse" in result.stderr


def test_ack_policy_never_blocks_warn_always_logs(tmp_repo: Path) -> None:
    """ack = ادامهٔ آگاهانه؛ warn = لاگ بدون توقف — هر دو exit 0."""
    base = _git(tmp_repo, "rev-parse", "HEAD").strip()
    _add_migration(tmp_repo, BLOCKING_INDEX_MIGRATION)
    for policy, expect_note in (("ack", None), ("warn", "هشدار")):
        result = _run(tmp_repo, base, policy=policy)
        assert result.returncode == 0, policy
        if expect_note:
            assert expect_note in result.stderr


def test_auto_policy_downgrades_to_warn_without_automatic_migrations(tmp_repo: Path) -> None:
    """compose با RUN_MIGRATIONS=0 → auto یعنی warn؛ توقف لازم نیست چون
    migrate دستی و زمان‌بندی‌شده است — ریسک قفل را خودِ اپراتور می‌پذیرد."""
    base = _git(tmp_repo, "rev-parse", "HEAD").strip()
    _add_migration(tmp_repo, BLOCKING_INDEX_MIGRATION)
    (tmp_repo / "docker-compose.yml").write_text(
        'services:\n  web:\n    environment:\n      RUN_MIGRATIONS: "0"\n', encoding="utf-8"
    )
    result = _run(tmp_repo, base, policy="auto")
    assert result.returncode == 0
    assert "policy=warn" in result.stdout or "هشدار" in result.stderr


def test_non_migration_changes_are_ignored(tmp_repo: Path) -> None:
    """غیِرِ fileهای migrations هرگز نباید گیت را درگیر کند."""
    base = _git(tmp_repo, "rev-parse", "HEAD").strip()
    (tmp_repo / "apps" / "x" / "views.py").write_text("X = 1\n", encoding="utf-8")
    _git(tmp_repo, "add", ".")
    _git(tmp_repo, "commit", "-qm", "code-only")
    result = _run(tmp_repo, base)
    assert result.returncode == 0

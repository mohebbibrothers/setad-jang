"""قرارداد ساختاری سرویس بکاپ خودکار (یافتۀ P2-11 فاز 8).

فلسفۀ این تست‌ها: خودِ ایمیج/کانتینر را اینجا نمی‌زانیم (docker در CIِ ریپو
نیست) — اما *سازگاری لایۀ config* را که اگر به‌هم بریزد بکاپ بی‌صدا خاموش
می‌شود، صریح چک می‌کنیم: سرویس وجود دارد، به فایل‌های اسکریپت mount اشاره
می‌کند، envهایِ حیاتی‌اش پین‌اند، healthcheck دارد، postgres آرشیو WAL را
به *همان* volume می‌نویسد، و اسکریپت‌ها executable-committed‌اند.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture(name="compose")
def compose_fixture() -> dict:
    """پارسِ docker-compose.yml (syntax + ساختارِ مورد انتظارِ این تست)."""
    return yaml.safe_load((ROOT / "docker-compose.yml").read_text(encoding="utf-8"))


def test_backup_service_defined_with_locked_image(compose: dict) -> None:
    """سرویس باید از *همان نسخهٔ major/minor* ایمیج postgres بیاید (قفلِ ابزار dump)."""
    backup = compose["services"]["backup"]
    postgres = compose["services"]["postgres"]
    assert backup["image"] == postgres["image"], "نسخۀ pg_dump باید با سرور قفل باشد"
    assert backup["depends_on"]["postgres"]["condition"] == "service_healthy"
    assert "healthcheck" in backup


def test_backup_scripts_mounted_and_exist(compose: dict) -> None:
    """mount اسکریپت‌ها باید به فایل‌های موجود اشاره کند و فراخوانی صریحِ sh باشد.

    contractِ عمداً mode-محور *نیست*: entrypoint با `/bin/sh <script>` اجرا
    می‌کند، پس exec-bit در image لازم نیست — وابستن تست به core.fileMode
    شکنندگیِ بیهوده است؛ در عوض همان `sh`ِ صریح چک می‌شود.
    """
    volumes = compose["services"]["backup"]["volumes"]
    mounts = {v.split(":")[1] for v in volumes}
    assert "/backup" in mounts
    for script in ("backup_loop.sh", "verify_restore.sh"):
        assert (ROOT / "deploy/backup" / script).is_file(), f"اسکریپت بکاپ گم شده: {script}"
    entry = compose["services"]["backup"]["entrypoint"]
    assert entry[0].endswith("/sh"), "اجرا باید با sh صریح باشد (نه exec-bit)"


def test_backup_env_contract(compose: dict) -> None:
    """هر متغیری که اسکریپت می‌خواند باید از compose تزریق/override شود."""
    env = compose["services"]["backup"]["environment"]
    for key in (
        "PGHOST",
        "PGDATABASE",
        "PGUSER",
        "PGPASSWORD",
        "BACKUP_INTERVAL_SECONDS",
        "BACKUP_KEEP_DAYS",
        "BACKUP_WAL_KEEP_DAYS",
        "BACKUP_VERIFY_EVERY",
    ):
        assert key in env, f"env {key} در سرویس backup تزریق نمی‌شود"
    # PGPASSWORD عمداً fail-fast است، نه پیش‌فرض:
    assert ":?" in env["PGPASSWORD"]


def test_postgres_archives_wal_to_backup_volume(compose: dict) -> None:
    """PITR بدون نوشتن WAL روی همان volume بی‌معنی است — پیکربندی قفل شود."""
    postgres = compose["services"]["postgres"]
    command = " ".join(str(x) for x in postgres["command"])
    assert "archive_mode=on" in command
    assert "wal_level=replica" in command
    assert "/backups/wal" in command
    assert "backup_data:/backups" in postgres["volumes"]


def test_shared_backup_volume_declared(compose: dict) -> None:
    """volume مشترک باید named باشد؛ bind-mountِ /backups روی هاست یعنی
    تصادم با هر چیز دیگری که همان مسیر را داشته باشد."""
    assert "backup_data" in compose["volumes"]


def test_scripts_use_strict_sh_and_shared_flags() -> None:
    """قراردادهای in-script که بیرون از container قابل آزمون‌اند:

    - `set -eu` (خطا = شکستِ صریح، نه ادامهٔ نصفه);
    - نوشتنِ همان پرچم‌هایی که healthcheck/runbook وعده داده‌اند.
    """
    loop = (ROOT / "deploy/backup/backup_loop.sh").read_text(encoding="utf-8")
    verify = (ROOT / "deploy/backup/verify_restore.sh").read_text(encoding="utf-8")
    assert "set -eu" in loop and "set -eu" in verify
    for flag in ("/backups/.backup_ok", "/backups/.backup_failed"):
        assert flag in loop
    assert "/backups/.verify_ok" in verify
    assert "--exit-on-error" in verify  # verify بدونِ exit-on-error نمایشی است

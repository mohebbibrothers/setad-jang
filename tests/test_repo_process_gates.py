"""گیت‌های فرآیندی ریپو (رفع F3/F4/F6 ممیزی ۲۰۲۶-۰۸-۳۰).

هر چک = یک بدهیِ فرآیندی که «یادت می‌ماند» را به «CI جیغ می‌زند» تبدیل
می‌کند. همه آفلاین/سریع‌اند (جز parity آمارِ README که collect-only می‌زند).
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parent.parent
CI = ROOT / ".github/workflows/ci.yml"

# راتچتِ بدهیِ mypy: فقط *کم* شدن مجاز است، زیاد شدن = شکستِ CI.
MYPY_DISABLED_FAMILIES_AT_BUDGET = 14


def _ci_text() -> str:
    return CI.read_text(encoding="utf-8")


def test_ci_actions_are_sha_pinned() -> None:
    """F10/F3: `uses: owner/repo@vN` روی tag متحرک = زنجیرۀ تأمین شکننده؛

    قاعدۀ ریپو: فقط `@<40-hex sha>` (dependabot bumpهایش را PR می‌کند).
    """
    bad = []
    for m in re.finditer(r"uses:\s*([^\s]+)@([^\s]+)", _ci_text()):
        owner_repo, ref = m.groups()
        if owner_repo.startswith("./"):
            continue  # local uses
        if not re.fullmatch(r"[0-9a-f]{40}", ref):
            bad.append(f"{owner_repo}@{ref}")
    assert not bad, f"actionهای unpinned (باید SHA شوند): {bad}"


def test_ci_validates_compose_and_nginx() -> None:
    """F4: خطای interpolate/سینتکس نباید اولین بار روی سرور کشف شود."""
    text = _ci_text()
    assert re.search(r"docker compose .*config -q", text), "گیت «compose config» در CI نیست"
    assert re.search(r"nginx:1\.27-alpine\s+.*-t|nginx\s+-t", text), "گیت «nginx -t» در CI نیست"


def test_ci_never_materializes_env_from_example() -> None:
    """درسِ همین فاز: «cp .env.example .env» در CI محتوای نمونه را به
    decouple/اپ نشت می‌دهد (خالی‌ها defaultها را می‌کشند). موجودیتِ خالی بس است."""
    assert "cp .env.example .env" not in _ci_text(), "گام compose نباید .env را از example بسازد"
    assert ": > .env" in _ci_text()


def test_dependabot_present_and_useful() -> None:
    """F3: بدونِ dependabot، pip-auditِ CI فقط *می‌داند*؛ PRِ رفع نمی‌سازد."""
    f = ROOT / ".github/dependabot.yml"
    assert f.is_file(), ".github/dependabot.yml گم شده"
    conf = yaml.safe_load(f.read_text(encoding="utf-8"))
    ecosystems = {u["package-ecosystem"] for u in conf["updates"]}
    assert {"pip", "github-actions", "docker"} <= ecosystems, ecosystems


def test_security_policy_published() -> None:
    """F3: کانالِ افشای خصوصی باید برای محقق بیرونی پیدا باشد."""
    f = ROOT / "SECURITY.md"
    assert f.is_file(), "SECURITY.md گم شده"
    t = f.read_text(encoding="utf-8").lower()
    assert "private" in t or "خصوصی" in t


def test_nginx_trusts_forwarded_proto_only_from_private_nets() -> None:
    """F5: قراردادِ XFP باید روی «زنجیرۀ اعتماد» قفل بماند، نه بازگشتِ

    بازنویسیِ کور/اعتمادِ کور.
    """
    src = (ROOT / "deploy/nginx.conf").read_text(encoding="utf-8")
    assert "geo $trust_xfp" in src
    assert 'map "$trust_xfp$http_x_forwarded_proto" $real_proto' in src
    assert "X-Forwarded-Proto $real_proto" in src
    assert "X-Forwarded-Proto $scheme;" not in src, "بازنویسیِ کور برگشته!"


def test_mypy_debt_ratchet() -> None:
    """F6: خانوادۀ غیرفعالِ mypy فقط کم می‌شود؛ زیادکردن = بدهیِ پنهانی."""
    toml = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    m = re.search(r"disable_error_code\s*=\s*\[(.*?)\]", toml, re.S)
    assert m, "بلوکِ disable_error_code را از pyproject برداشتی؟ (عالی — ثابت را کم کن)"
    count = len(re.findall(r'"[a-z0-9-]+"', m.group(1)))
    assert count <= MYPY_DISABLED_FAMILIES_AT_BUDGET, (
        f"مypy ratchet شکست: {count} > {MYPY_DISABLED_FAMILIES_AT_BUDGET} — "
        "خانوادۀ جدیدی را غیرفعال نکن؛ بدهی را پاک کن."
    )
    if count < MYPY_DISABLED_FAMILIES_AT_BUDGET:
        pytest.fail(
            f"بدهی کم شده ({count}) — ثابت راتچت را در همین فایل به {count} برسان "
            "(قفلِ زنگ‌ولهٔ بازگشت؛ عمدی است)."
        )


def test_readme_verify_stats_match_suite() -> None:
    """F3: جدولِ آمارِ README باید با سوئیت واقعی بخواند.

    passed+skipped (از جدول) == تعدادِ collect — یعنی هر کامیتی که تست
    کم/زیاد می‌کند، این گیت را می‌ترکاند تا آمار بیات نشود.
    """
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    m = re.search(r"(\d+) passed(?: / (\d+) skipped)?", readme)
    assert m, "خطِ «N passed / M skipped» در README نیست"
    documented = int(m.group(1)) + int(m.group(2) or 0)

    proc = subprocess.run(
        [sys.executable, "-m", "pytest", "--collect-only", "-q", "-p", "no:cacheprovider"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=600,
        env={
            "DJANGO_SETTINGS_MODULE": "config.settings.test",
            "PATH": str(Path(sys.executable).parent),
        },
    )
    assert proc.returncode == 0, proc.stdout[-500:] + proc.stderr[-500:]
    col = re.search(r"(\d+) tests? collected", proc.stdout)
    assert col, "تعدادِ collect قابل خواندن نبود:\n" + proc.stdout[-500:]
    collected = int(col.group(1))
    assert documented == collected, (
        f"آمار README ({documented} = passed+skipped) با سوئیت ({collected}) نمی‌خواند — "
        "جدول §2 README را با اعدادِ واقعیِ verify به‌روز کن."
    )

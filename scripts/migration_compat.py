#!/usr/bin/env python3
"""دروازۀ سازگاری مهاجرت‌ها پیش از build/deploy — یافتۀ P2-12/۱۴ فاز ۸.

دو ریسکِ مشخص را روی *مهاجرت‌های تازهٔ* یک بازۀ rev پیش‌بینی می‌کند:

1. **DDL قفل‌کننده (P2-12):** `AddIndex`/`GinIndex`/`CREATE INDEX` بدونِ
   `Concurrently` — روی جدولِ بزرگ، نوشتن‌ها را تا پایانِ ساختِ ایندکس
   قفل می‌کند. با `RUN_MIGRATIONS=1` (پیش‌فرضِ سرویس web در compose) این
   قفل *وسطِ deployِ خودکار* می‌افتد.

2. **مهاجرتِ برگشت‌ناپذیر (P2-14):** `RunPython(` بدونِ `reverse=`/`noop` —
   اگر deploy بعد از migrate شکست بخورد، ایمیج rollback می‌شود ولی DB با
   دادهٔ مهاجرت‌شده می‌ماند؛ کدِ قدیمی روی اسکیما/دادهٔ جدید نمی‌نشیند.

خروجی: گزارشِ خواناترِ فایل‌های متخلف؛ کدِ خروج:
    0 = پاک یا warn-mode            2 = block (deploy باید متوقف شود)

طراحی خطی‌grep-محور عمده‌است: تحلیلِ کاملِ AST لازم نیست چون خودِ عملیات‌های
جانگو در `operations = [...]` تک‌خطی‌اند؛ false-negativeِ نادر (عملیاتِ چندخطی
در هم‌ریختگی) به‌عهدهِ code-review است — این گیت قرار است driftِ بی‌دقتِ
معمول را بگیرد، نه این‌که parserِ مایگریشن بنویسد. برای همین conservative
عمل می‌کند: هر فایلِ مهاجرتِ تغییریافته که *هیچ‌کدام* را داشته باشد پاک است؛
هر تطابقی = flag.

Policy:
    auto  → اگر در compose فایل، `RUN_MIGRATIONS` روی "1" بود: block؛ نه: warn.
    block → همیشه non-zero در صورت یافتنِ ریسک.
    warn  → فقط لاگ (پنجرۀ تعمیراتیِ از پیش توافق‌شده).
    ack   → سکوتِ آگاهانه (همان warn با برچسبِ override) — فقط برای زمانی که
            عملیاتِ دستیِ migrate در maintenance window برنامه‌ریزی شده.
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path

_BLOCKING_INDEX_RE = re.compile(
    r"\b(?:AddIndex|GinIndex|BTreeIndex|TrigramSimilarity)\b|CREATE\s+INDEX", re.I
)
_CONCURRENTLY_RE = re.compile(r"Concurrently")
_RUNPY_RE = re.compile(r"\bRunPython\s*\(")
_REVERSIBLE_RE = re.compile(r"reverse\s*=|migrations\.RunPython\.noop")

EXIT_OK = 0
EXIT_BLOCK = 2


def changed_migration_files(repo: Path, rev_from: str, rev_to: str) -> list[Path]:
    """فایل‌های مایگریشن تغییریافته بین دو rev (نسبت‌به‌ریشهٔ مخزن)."""
    out = subprocess.run(
        ["git", "-C", str(repo), "diff", "--name-only", rev_from, rev_to, "--"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout
    files: list[Path] = []
    for line in out.splitlines():
        if "/migrations/" in line and line.endswith(".py") and "__" not in line:
            p = repo / line
            if p.is_file():
                files.append(p)
    return files


def scan_file(path: Path) -> tuple[bool, bool]:
    """(blocking_index_risk, irreversible_risk) برای یک فایلِ مایگریشن."""
    text = path.read_text(encoding="utf-8", errors="replace")
    blocking = bool(_BLOCKING_INDEX_RE.search(text)) and not _CONCURRENTLY_RE.search(text)
    # هر RunPython بدونِ reverse در کلِ فایل: اگر فایل چند RunPython با
    # ترکیبِ reversible/irreversible داشته باشد، conservative=YES می‌گوییم.
    runpy = bool(_RUNPY_RE.search(text))
    irreversible = runpy and len(_REVERSIBLE_RE.findall(text)) < len(_RUNPY_RE.findall(text))
    return blocking, irreversible


def compose_autoruns_migrations(compose_file: Path) -> bool:
    """آیا compose، مایگریشنِ خودکارِ web را روشن گذاشته؟ (پینِ موجود = "1")."""
    if not compose_file.is_file():
        return False
    text = compose_file.read_text(encoding="utf-8", errors="replace")
    return bool(re.search(r"RUN_MIGRATIONS:\s*[\"']?1", text))


def main(argv: list[str] | None = None) -> int:
    """CLI اصلی؛ کدِ خروجِ گیت را برمی‌گرداند."""
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--repo", default=".", type=Path)
    ap.add_argument("--from", dest="rev_from", required=True)
    ap.add_argument("--to", dest="rev_to", required=True)
    ap.add_argument("--compose-file", type=Path, default=None)
    ap.add_argument("--policy", choices=("auto", "block", "warn", "ack"), default="auto")
    args = ap.parse_args(argv)

    repo = args.repo.resolve()
    files = changed_migration_files(repo, args.rev_from, args.rev_to)
    risky: list[tuple[str, str]] = []
    for f in files:
        blocking, irreversible = scan_file(f)
        rel = f.relative_to(repo).as_posix()
        if blocking:
            risky.append((rel, "index-DDL بدون CONCURRENTLY (قفلِ نوشتن روی جدولِ بزرگ)"))
        if irreversible:
            risky.append((rel, "RunPython بدونِ reverse (rollbackِ ایمیج، DB را برنمی‌گرداند)"))

    policy = args.policy
    if policy == "auto":
        compose = args.compose_file or (repo / "docker-compose.yml")
        policy = "block" if compose_autoruns_migrations(Path(compose)) else "warn"

    if not risky:
        print(
            f"migration-compat: پاک — {len(files)} فایل مایگریشن تغییریافته بررسی شد (policy={policy})."
        )
        return EXIT_OK

    print(
        f"migration-compat: {len(risky)} ریسک در {len(files)} فایل تغییریافته یافت شد (policy={policy}):",
        file=sys.stderr,
    )
    for rel, reason in risky:
        print(f"  ! {rel}: {reason}", file=sys.stderr)

    if policy == "block":
        print(
            "  → deploy متوقف شد. گزینه‌ها: (۱) پنجرۀ تعمیراتی + migrate دستی با "
            "RUN_MIGRATIONS=0 سپس RISKY_MIGRATION_POLICY=ack، (۲) تبدیل به "
            "AddIndexConcurrently/RunPython(reverse=...) در یک کامیتِ اصلاحی.",
            file=sys.stderr,
        )
        return EXIT_BLOCK
    if policy == "warn":
        print("  → فقط هشدار (policy=warn) — مسئولیت اجرا با اپراتور است.", file=sys.stderr)
    # ack: سکوتِ آگاهانه؛ گزارشِ بالا در لاگِ deploy ثبت می‌شود.
    return EXIT_OK


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python
"""تولید و بررسی فایل‌های قفل وابستگی.

چرا لازم است
------------
``requirements.txt`` وابستگی‌های سطح‌بالا را نگه می‌دارد و transitiveها را پین
نمی‌کند. نتیجه این است که دو build از یک commit یکسان می‌توانند نسخه‌های
متفاوتی بگیرند؛ یعنی image قابل بازتولید نیست و باگی که در staging دیده نشده
می‌تواند در production ظاهر شود.

دو قفل جدا تولید می‌شود:

* ``requirements-lock.txt``      → فقط runtime، مصرف‌کننده: Dockerfile
* ``requirements-dev-lock.txt``  → runtime + toolchain، مصرف‌کننده: CI

جدا بودنشان عمدی است تا ابزارهای توسعه (pytest، ruff، bandit و ...) هرگز
داخل image نهایی نروند.

استفاده
-------
    python scripts/generate_locks.py            # بازتولید
    python scripts/generate_locks.py --check    # فقط بررسی drift (برای CI)
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

PROD_HEADER = """# ============================================================
# قفل وابستگی‌های production
# ============================================================
#
# این فایل به‌صورت خودکار تولید می‌شود. دستی ویرایشش نکنید.
#
#     make lock
#
# چرا وجود دارد: `requirements.txt` بازه‌ای/سطح‌بالا است و وابستگی‌های
# غیرمستقیم را پین نمی‌کند. یعنی دو build از یک commit یکسان می‌توانند
# نسخه‌های متفاوتی از transitive dependencyها بگیرند و باگی که در staging
# نبود در production ظاهر شود. Dockerfile از همین فایل استفاده می‌کند تا
# image قابل بازتولید باشد.
#
# فقط وابستگی‌های runtime. ابزارهای توسعه در requirements-dev-lock.txt.
# ============================================================

"""

DEV_HEADER = """# ============================================================
# قفل وابستگی‌های production + development
# ============================================================
#
# تولید خودکار — دستی ویرایش نکنید:  make lock
#
# CI از این فایل استفاده می‌کند. عمداً از قفل production جداست تا
# ابزارهای توسعه (pytest، ruff، bandit، ...) هرگز وارد image نهایی نشوند.
# ============================================================

"""

TARGETS = (
    ("requirements-lock.txt", ("requirements.txt",), PROD_HEADER),
    (
        "requirements-dev-lock.txt",
        ("requirements.txt", "requirements-dev.txt"),
        DEV_HEADER,
    ),
)


def resolve(sources: tuple[str, ...]) -> list[tuple[str, str]]:
    """پین‌های کامل یک مجموعه requirements را با resolver خود pip حساب می‌کند."""
    args: list[str] = []
    for source in sources:
        args += ["-r", str(ROOT / source)]

    with tempfile.NamedTemporaryFile(suffix=".json") as report:
        subprocess.run(
            [
                sys.executable,
                "-m",
                "pip",
                "install",
                "--dry-run",
                "--ignore-installed",
                "--quiet",
                "--report",
                report.name,
                *args,
            ],
            check=True,
            cwd=ROOT,
        )
        data = json.loads(Path(report.name).read_text())

    return sorted(
        (item["metadata"]["name"], item["metadata"]["version"]) for item in data["install"]
    )


def render(sources: tuple[str, ...], header: str) -> str:
    pins = resolve(sources)
    return header + "\n".join(f"{name}=={version}" for name, version in pins) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check",
        action="store_true",
        help="فقط بررسی همگام بودن قفل‌ها؛ چیزی نوشته نمی‌شود.",
    )
    options = parser.parse_args()

    drifted: list[str] = []
    for filename, sources, header in TARGETS:
        path = ROOT / filename
        rendered = render(sources, header)

        if options.check:
            current = path.read_text() if path.exists() else ""
            if current != rendered:
                drifted.append(filename)
            continue

        path.write_text(rendered)
        print(f"نوشته شد: {filename}")

    if drifted:
        print(
            "قفل وابستگی‌ها هماهنگ نیست: " + "، ".join(drifted) + "\nبرای اصلاح: make lock",
            file=sys.stderr,
        )
        return 1

    if options.check:
        print("قفل وابستگی‌ها هماهنگ است.")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

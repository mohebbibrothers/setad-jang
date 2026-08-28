#!/usr/bin/env python
"""Regenerate STRUCTURE.md from the actual repository contents.

چرا اسکریپت و نه ویرایش دستی:
    نسخهٔ قبلی `STRUCTURE.md` دستی نگهداری می‌شد و طبیعتاً کهنه شده بود —
    تاریخ ۲۰۲۶-۰۶-۱۰، فقط ۷ اپ از ۱۳ اپ موجود، و تعداد مایگریشن‌های غلط
    (مثلاً برای r4j عدد ۲ نوشته شده بود در حالی که ۹ تا بود). سندی که
    ادعای دقت دارد ولی غلط است، از نبودِ سند بدتر است.

    همچنین `project_structure.txt` حجم بایتی هر فایل را ذخیره می‌کرد؛ یعنی
    هر تغییر کوچک در هر فایل، این سند را هم کثیف می‌کرد. اینجا عمداً هیچ
    اندازه‌ای چاپ نمی‌شود تا خروجی فقط با تغییرات *ساختاری* عوض شود.

استفاده:
    make structure        # بازتولید
    make structure-check  # تشخیص drift در CI
"""

from __future__ import annotations

import argparse
import ast
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
APPS_ROOT = REPO_ROOT / "apps"

SKIP_DIRS = {"__pycache__", ".pytest_cache", ".ruff_cache", ".git", "node_modules"}

LAYER_NOTES: dict[str, str] = {
    "models.py": "مدل‌های داده",
    "selectors.py": "خواندن داده (بدون side effect)",
    "services.py": "منطق کسب‌وکار و نوشتن",
    "serializers.py": "اعتبارسنجی ورودی/خروجی",
    "views.py": "لایهٔ HTTP",
    "filters.py": "فیلترهای queryset",
    "permissions.py": "کنترل دسترسی",
    "tasks.py": "تسک‌های Celery",
    "throttles.py": "محدودسازی نرخ",
    "choices.py": "مقادیر ثابت و انتخاب‌ها",
    "export.py": "خروجی اکسل",
    "urls.py": "مسیرها",
}


def _count_nodes(path: Path, base: type[ast.AST], base_names: set[str]) -> int:
    """Count class definitions inheriting from any of ``base_names``."""
    if not path.exists():
        return 0
    try:
        tree = ast.parse(path.read_text(encoding="utf-8-sig"))
    except SyntaxError:
        return 0
    count = 0
    for node in ast.walk(tree):
        if not isinstance(node, ast.ClassDef):
            continue
        for parent in node.bases:
            name = ""
            if isinstance(parent, ast.Attribute):
                name = parent.attr
            elif isinstance(parent, ast.Name):
                name = parent.id
            if name in base_names:
                count += 1
                break
    return count


def _app_rows() -> list[tuple[str, int, int, int, int]]:
    """Collect per-app counts: models, migrations, views, endpoints."""
    rows: list[tuple[str, int, int, int, int]] = []
    for app_dir in sorted(APPS_ROOT.iterdir()):
        if not app_dir.is_dir() or app_dir.name in SKIP_DIRS:
            continue
        if not (app_dir / "__init__.py").exists():
            continue

        models = _count_nodes(
            app_dir / "models.py", ast.ClassDef, {"Model", "BaseModel", "AbstractUser"}
        )
        migrations_dir = app_dir / "migrations"
        migrations = (
            len([p for p in migrations_dir.glob("0*.py")]) if migrations_dir.exists() else 0
        )
        views = _count_nodes(
            app_dir / "views.py",
            ast.ClassDef,
            {"APIView", "ServiceBackedListAPIView", "GenericAPIView"},
        )
        urls_path = app_dir / "urls.py"
        endpoints = 0
        if urls_path.exists():
            source = urls_path.read_text(encoding="utf-8-sig")
            endpoints = source.count("path(") + source.count("re_path(")
        rows.append((app_dir.name, models, migrations, views, endpoints))
    return rows


def _tree_lines(root: Path, prefix: str = "", depth: int = 0, max_depth: int = 2) -> list[str]:
    """Render a compact directory tree without file sizes."""
    if depth > max_depth:
        return []
    entries = sorted(
        (p for p in root.iterdir() if p.name not in SKIP_DIRS and not p.name.startswith(".")),
        key=lambda p: (p.is_file(), p.name),
    )
    lines: list[str] = []
    for index, entry in enumerate(entries):
        last = index == len(entries) - 1
        connector = "└── " if last else "├── "
        if entry.is_dir():
            lines.append(f"{prefix}{connector}{entry.name}/")
            lines.extend(
                _tree_lines(entry, prefix + ("    " if last else "│   "), depth + 1, max_depth)
            )
        elif entry.suffix == ".py":
            note = LAYER_NOTES.get(entry.name, "")
            suffix = f"  # {note}" if note else ""
            lines.append(f"{prefix}{connector}{entry.name}{suffix}")
    return lines


def build_document() -> str:
    """Return the full STRUCTURE.md content."""
    rows = _app_rows()
    total_models = sum(r[1] for r in rows)
    total_migrations = sum(r[2] for r in rows)
    total_views = sum(r[3] for r in rows)
    total_endpoints = sum(r[4] for r in rows)

    lines: list[str] = [
        "# ساختار پروژه",
        "",
        "> این فایل **تولیدشده** است. دستی ویرایشش نکنید.",
        "> بازتولید: `make structure` — بررسی drift در CI: `make structure-check`",
        "",
        "نسخهٔ قبلی این سند دستی نگهداری می‌شد و کهنه شده بود: شش اپ در آن غایب",
        "بودند و تعداد مایگریشن‌ها غلط بود. حالا از روی خود مخزن ساخته می‌شود و",
        "یک گیت CI اختلافش با کد را می‌گیرد، پس دیگر نمی‌تواند بی‌صدا کهنه شود.",
        "",
        "## اپلیکیشن‌ها",
        "",
        f"مجموع: **{len(rows)} اپ** · {total_models} مدل · {total_migrations} مایگریشن · "
        f"{total_views} ویو · {total_endpoints} مسیر",
        "",
        "| اپ | مدل | مایگریشن | ویو | مسیر |",
        "|---|---:|---:|---:|---:|",
    ]
    for name, models, migrations, views, endpoints in rows:
        lines.append(f"| `{name}` | {models} | {migrations} | {views} | {endpoints} |")

    lines += [
        "",
        "## قرارداد لایه‌ها",
        "",
        "هر اپ از یک تفکیک ثابت پیروی می‌کند:",
        "",
        "| فایل | مسئولیت |",
        "|---|---|",
    ]
    for filename, note in LAYER_NOTES.items():
        lines.append(f"| `{filename}` | {note} |")

    lines += [
        "",
        "قواعدی که با تست معماری (`tests/test_architecture_discipline.py`) اجرا می‌شوند:",
        "",
        "- هر ماژول production باید docstring سطح ماژول داشته باشد.",
        "- `views.py` نباید مستقیماً روی manager یا queryset مدل بنویسد؛",
        "  نوشتن از طریق لایهٔ `services.py` انجام می‌شود.",
        "- `TODO`/`FIXME` مجاز است ولی باید شمارهٔ issue داشته باشد و از سقف",
        "  تعیین‌شده بیشتر نشود — بدهی فنی باید ثبت شود، نه پنهان.",
        "",
        "## درخت دایرکتوری",
        "",
        "```text",
        "setad-jang/",
    ]
    lines.extend(_tree_lines(REPO_ROOT / "apps", max_depth=1))
    lines += [
        "```",
        "",
        "## زیرساخت مشترک (`apps/core`)",
        "",
        "```text",
        "apps/core/",
    ]
    lines.extend(_tree_lines(REPO_ROOT / "apps" / "core", max_depth=0))
    lines += ["```", ""]

    return "\n".join(lines)


def main() -> int:
    """Write or verify STRUCTURE.md."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="فقط drift را گزارش کن")
    args = parser.parse_args()

    target = REPO_ROOT / "STRUCTURE.md"
    content = build_document()

    if args.check:
        current = target.read_text(encoding="utf-8") if target.exists() else ""
        if current != content:
            sys.stderr.write(
                "STRUCTURE.md با ساختار واقعی مخزن همگام نیست. "
                "«make structure» را اجرا و نتیجه را commit کن.\n"
            )
            return 1
        return 0

    target.write_text(content, encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

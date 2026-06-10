"""
Architecture discipline tests for production code hygiene.

این تست‌ها نقش quality gate معماری را دارند و جلوی برگشتن debtهای خطرناک را
می‌گیرند. هدف آن‌ها style سلیقه‌ای نیست؛ بلکه enforce کردن قراردادهایی است که
برای یک codebase بزرگ و چنداپلیکیشنی حیاتی‌اند:
- هر ماژول production باید docstring داشته باشد.
- هر class/function سطح ماژول باید حداقل توضیح معماری داشته باشد.
- placeholder/TODO/pass/NotImplementedError نباید در کد production برگردد.
- viewها نباید مستقیماً mutationهای دیتابیس را انجام دهند؛ mutation باید از
  service layer عبور کند.
"""

from __future__ import annotations

import ast
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
PRODUCTION_ROOTS = (PROJECT_ROOT / "apps", PROJECT_ROOT / "config")
FORBIDDEN_MARKERS = (
    "TODO",
    "FIXME",
    "NotImplementedError",
    "placeholder",
    "pass",
)
VIEW_DB_MUTATION_METHODS = {
    "bulk_create",
    "bulk_update",
    "create",
    "delete",
    "get_or_create",
    "save",
    "update",
    "update_or_create",
}


def _production_python_files() -> list[Path]:
    """برگرداندن فایل‌های Python production، بدون tests/migrations/cache."""
    files: list[Path] = []
    for root in PRODUCTION_ROOTS:
        for path in root.rglob("*.py"):
            if any(part in {"migrations", "tests", "__pycache__"} for part in path.parts):
                continue
            files.append(path)
    return sorted(files)


def _parse(path: Path) -> ast.Module:
    """Parse کردن فایل با پشتیبانی از BOM احتمالی."""
    return ast.parse(path.read_text(encoding="utf-8-sig"), filename=str(path))


def test_production_modules_have_module_docstrings() -> None:
    """تمام ماژول‌های production باید module-level docstring داشته باشند."""
    missing = []
    for path in _production_python_files():
        tree = _parse(path)
        if ast.get_docstring(tree) is None:
            missing.append(path.relative_to(PROJECT_ROOT).as_posix())

    assert missing == []


def test_top_level_production_classes_and_functions_have_docstrings() -> None:
    """class/functionهای سطح ماژول در کد production باید docstring داشته باشند."""
    missing = []
    for path in _production_python_files():
        if path.name == "__init__.py":
            continue
        tree = _parse(path)
        for node in tree.body:
            if isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)) and ast.get_docstring(node) is None:
                missing.append(
                    f"{path.relative_to(PROJECT_ROOT).as_posix()}:{node.lineno}:{node.name}"
                )

    assert missing == []


def test_no_forbidden_placeholder_markers_in_production_code() -> None:
    """کد production نباید TODO/pass/placeholder/NotImplementedError داشته باشد."""
    violations = []
    for path in _production_python_files():
        for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
            stripped = line.strip()
            for marker in FORBIDDEN_MARKERS:
                if marker == "pass":
                    if stripped == "pass":
                        violations.append(
                            f"{path.relative_to(PROJECT_ROOT).as_posix()}:{line_number}:{marker}"
                        )
                elif marker in line:
                    violations.append(
                        f"{path.relative_to(PROJECT_ROOT).as_posix()}:{line_number}:{marker}"
                    )

    assert violations == []


def test_views_do_not_call_database_mutation_methods_directly() -> None:
    """View modules نباید مستقیماً save/create/update/delete انجام دهند."""
    violations = []
    for path in _production_python_files():
        if path.name != "views.py":
            continue
        tree = _parse(path)
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and node.func.attr in VIEW_DB_MUTATION_METHODS
            ):
                violations.append(
                    f"{path.relative_to(PROJECT_ROOT).as_posix()}:{node.lineno}:{node.func.attr}"
                )

    assert violations == []

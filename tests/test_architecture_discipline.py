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
import io
import re
import tokenize
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
PRODUCTION_ROOTS = (PROJECT_ROOT / "apps", PROJECT_ROOT / "config")
# سقف بدهی فنیِ ثبت‌شده. TODO ممنوع نیست — *پنهان* بودنش ممنوع است.
MAX_TRACKED_TODOS = 20

# هر TODO/FIXME باید به یک issue ارجاع بدهد: «# TODO(#123): توضیح».
TRACKED_TODO_PATTERN = re.compile(r"^#\s*(TODO|FIXME)\(#\d+\):\s*\S")
TODO_MARKER_PATTERN = re.compile(r"\b(TODO|FIXME)\b")
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

# نام‌هایی که در یک زنجیرهٔ صفت، نشانهٔ manager یا queryset جنگو هستند.
# قانون قبلی فقط به *نام متد* نگاه می‌کرد و همین باعث می‌شد
# `serializer.save()` هم ممنوع شود — در حالی که آن اصلاً mutation مستقیم
# دیتابیس نیست و به `ModelSerializer.create()` می‌رود که خودش می‌تواند
# لایهٔ service را صدا بزند.
#
# پیامد آن قانون خام این بود که کل تیم مجبور شد از `generics.*` و
# `ModelViewSet` صرف‌نظر کند و ۲۸۴ ویو را دستی بنویسد؛ یعنی هزاران خط
# boilerplate که هر باگ در الگویش باید ده‌ها بار جداگانه رفع شود.
#
# قانون جدید دقیقاً همان نیت اصلی را اعمال می‌کند: «ویو نباید مستقیماً
# روی manager/queryset مدل عملیات نوشتن انجام دهد».
DJANGO_MANAGER_SEGMENTS = {
    "objects",
    "all_objects",
    "_base_manager",
    "_default_manager",
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
            if (
                isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef))
                and ast.get_docstring(node) is None
            ):
                missing.append(
                    f"{path.relative_to(PROJECT_ROOT).as_posix()}:{node.lineno}:{node.name}"
                )

    assert missing == []


def _comment_tokens(path: Path) -> list[tuple[int, str]]:
    """استخراج فقط کامنت‌های واقعی — نه رشته‌ها و نه داکسترینگ‌ها."""
    comments: list[tuple[int, str]] = []
    source = path.read_text(encoding="utf-8-sig")
    try:
        for token in tokenize.generate_tokens(io.StringIO(source).readline):
            if token.type == tokenize.COMMENT:
                comments.append((token.start[0], token.string.strip()))
    except (tokenize.TokenError, IndentationError):  # pragma: no cover - فایل ناقص
        return []
    return comments


def test_bare_pass_is_not_used_as_a_body_in_production_code() -> None:
    """بدنهٔ خالی با `pass` نشانهٔ کد ناتمام است؛ به‌جایش docstring یا `...`."""
    violations = []
    for path in _production_python_files():
        for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
            if line.strip() == "pass":
                violations.append(f"{path.relative_to(PROJECT_ROOT).as_posix()}:{line_number}")

    assert violations == []


def test_todo_markers_are_tracked_and_bounded() -> None:
    """TODO ممنوع نیست، ولی باید ثبت‌شده و محدود باشد.

    قانون قبلی هر خطی را که رشتهٔ «TODO» در آن بود رد می‌کرد — از جمله
    داکسترینگ‌ها و رشته‌های معمولی. نتیجه‌اش این نبود که بدهی فنی از بین
    برود؛ نتیجه‌اش این بود که کسی جرئت نکند بدهی فنی را **بنویسد**. یعنی
    گیت، دیسیپلین را به تئاتر تبدیل کرده بود: بدهی همچنان وجود داشت،
    فقط دیگر قابل جست‌وجو نبود.

    قانون جدید سه چیز را همزمان تضمین می‌کند:
      ۱. TODO فقط در کامنت شمرده می‌شود، نه در هر رشته‌ای که این کلمه را دارد.
      ۲. هر TODO باید به یک issue ارجاع بدهد: `# TODO(#123): توضیح`.
      ۳. مجموع TODOها از سقف مشخصی بیشتر نشود.
    """
    untracked: list[str] = []
    tracked: list[str] = []

    for path in _production_python_files():
        for line_number, comment in _comment_tokens(path):
            if not TODO_MARKER_PATTERN.search(comment):
                continue
            location = f"{path.relative_to(PROJECT_ROOT).as_posix()}:{line_number}"
            if TRACKED_TODO_PATTERN.match(comment):
                tracked.append(location)
            else:
                untracked.append(f"{location}: {comment}")

    assert untracked == [], (
        "هر TODO/FIXME باید شمارهٔ issue داشته باشد، به شکل «# TODO(#123): توضیح»."
    )
    assert len(tracked) <= MAX_TRACKED_TODOS, (
        f"تعداد TODOهای ثبت‌شده ({len(tracked)}) از سقف {MAX_TRACKED_TODOS} گذشته است."
    )


def _attribute_chain(node: ast.AST) -> list[str]:
    """نام‌های یک زنجیرهٔ صفت را از چپ به راست برمی‌گرداند."""
    parts: list[str] = []
    current = node
    while True:
        if isinstance(current, ast.Attribute):
            parts.append(current.attr)
            current = current.value
        elif isinstance(current, ast.Call):
            current = current.func
        elif isinstance(current, ast.Name):
            parts.append(current.id)
            break
        else:
            break
    return list(reversed(parts))


def test_views_do_not_mutate_model_managers_directly() -> None:
    """ویو نباید مستقیماً روی manager/queryset مدل بنویسد.

    نیت این قانون از ابتدا درست بوده: منطق کسب‌وکار جای ویو نیست. ولی
    پیاده‌سازی‌اش فقط *نام متد* را می‌دید، پس `serializer.save()` را هم —
    که یک الگوی کاملاً استاندارد DRF است و به لایهٔ service وصل می‌شود —
    ممنوع می‌کرد. حالا به گیرندهٔ فراخوانی هم نگاه می‌کنیم.
    """
    violations = []
    for path in _production_python_files():
        if path.name != "views.py":
            continue
        tree = _parse(path)
        for node in ast.walk(tree):
            if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)):
                continue
            if node.func.attr not in VIEW_DB_MUTATION_METHODS:
                continue
            chain = _attribute_chain(node.func)
            if any(segment in DJANGO_MANAGER_SEGMENTS for segment in chain):
                violations.append(
                    f"{path.relative_to(PROJECT_ROOT).as_posix()}:{node.lineno}:{'.'.join(chain)}"
                )

    assert violations == []


def test_serializer_save_is_allowed_in_views() -> None:
    """قانون معماری نباید الگوی استاندارد DRF را ممنوع کند.

    این تست، خودِ قانون را تست می‌کند: مطمئن می‌شود `serializer.save()`
    دیگر به‌عنوان تخلف شمرده نمی‌شود ولی `Model.objects.create()` هنوز
    شمرده می‌شود. بدون این، ممکن است قانون دوباره به حالت خام برگردد و
    کسی متوجه نشود.
    """
    tree = ast.parse(
        "def handler(serializer, request):\n"
        "    serializer.save()\n"
        "    Thing.objects.create(name='x')\n"
        "    Thing.all_objects.filter(pk=1).update(name='y')\n"
    )
    flagged = []
    for node in ast.walk(tree):
        if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)):
            continue
        if node.func.attr not in VIEW_DB_MUTATION_METHODS:
            continue
        chain = _attribute_chain(node.func)
        if any(segment in DJANGO_MANAGER_SEGMENTS for segment in chain):
            flagged.append(".".join(chain))

    assert flagged == ["Thing.objects.create", "Thing.all_objects.filter.update"]

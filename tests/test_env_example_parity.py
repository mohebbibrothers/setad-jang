"""
نگهبانِ «پاریتهٔ .env.example» — یافتهٔ P2 ممیزی مستقل.

مشکل اثبات‌شده در ممیزی:
    ۶۲+ کلید env در کد خوانده می‌شوند ولی در `.env.example` مستند نبودند؛
    یعنی operator استقرار بدون آگاهی از آن‌ها deploy می‌کند و تنظیمات
    امنیتی/عملیاتی (مثلاً NUM_PROXIES یا آستانه‌های ریسک) ناخواسته روی
    پیش‌فرض می‌مانند.

قرارداد این تست (فقط یک جهت؛ سمت معکوس عمداً سخت‌گیرانه نیست):
    هر کلیدی که در کدِ Python (apps/ و config/) از طریق
    `config("KEY")` یا `os.environ[...]`/`os.getenv("KEY")` خوانده
    می‌شود، باید در `.env.example` به‌صورت `KEY=` ظاهر شود (کامنت‌شده
    هم حساب می‌شود). سمت معکوس آزاد است: کلیدهای مستند مثل
    `GUNICORN_*`/`FLOWER_*` توسط compose/اسکریپت مصرف می‌شوند نه Python.

نتیجهٔ فاز رفع: صفر کلید ناقص؛ این تست آن را قفل می‌کند.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent

_CODE_ROOTS = ("apps", "config")
_DOC_FILE = PROJECT_ROOT / ".env.example"

_CONFIG_PATTERN = re.compile(r"config\(\s*[\"']([A-Z0-9_]+)[\"']", re.S)
_ENV_PATTERN = re.compile(
    r"os\.(?:environ|getenv)\(\s*[\"']([A-Z0-9_]+)[\"']|getenv\(\s*[\"']([A-Z0-9_]+)[\"']",
    re.S,
)
# فقط خطوط «تعریف» (KEY=value بدون متن دنباله‌دار) شمرده می‌شوند؛
# کامنت‌های توضیحی مثل «# LOG_FORMAT=text برای dev خوانا» تعریف نیستند.
_DOC_LINE_PATTERN = re.compile(r"^#?\s*([A-Z0-9_]+)=([A-Za-z0-9_\-.,:/\[\]@ ]*)$")


def _used_keys() -> set[str]:
    """تمام کلیدهای env که کد Python (apps/config) می‌خواند."""
    used: set[str] = set()
    for root in _CODE_ROOTS:
        for path in (PROJECT_ROOT / root).rglob("*.py"):
            if "__pycache__" in str(path) or "/migrations/" in str(path).replace("\\", "/"):
                continue
            text = path.read_text(encoding="utf-8", errors="ignore")
            for match in _CONFIG_PATTERN.finditer(text):
                used.add(match.group(1))
            for match in _ENV_PATTERN.finditer(text):
                used.add(match.group(1) or match.group(2))
    return used


def _documented_keys() -> set[str]:
    """کلیدهای `KEY=` در .env.example (نمونه‌های کامنت‌شده هم حساب می‌شوند)."""
    documented: set[str] = set()
    for line in _DOC_FILE.read_text(encoding="utf-8").splitlines():
        match = _DOC_LINE_PATTERN.match(line)
        if match:
            documented.add(match.group(1))
    return documented


def test_every_env_key_read_in_code_is_documented() -> None:
    """هر کلید env خوانده‌شده در کد باید در .env.example مستند باشد."""
    missing = sorted(_used_keys() - _documented_keys())
    assert not missing, (
        "کلیدهای env زیر در کد خوانده می‌شوند ولی در .env.example مستند نیستند "
        f"(یافتهٔ P2 ممیزی): {missing}"
    )


def test_documented_keys_have_no_duplicates() -> None:
    """کلید تکراری در .env.example گمراه‌کننده است (مقدار دوم بی‌صدا برنده است)."""
    seen: list[str] = []
    for line in _DOC_FILE.read_text(encoding="utf-8").splitlines():
        match = _DOC_LINE_PATTERN.match(line)
        if match:
            seen.append(match.group(1))
    duplicates = sorted({key for key in seen if seen.count(key) > 1})
    assert not duplicates, f"کلیدهای تکراری در .env.example: {duplicates}"


# ============================================================
# پاریتۀ «مقدار» — یافتۀ P2-10 فاز 8
# ============================================================
# تستِ کلیدِ خالی کافی نبود: اپراتوری که .env.example را کپی می‌کند،
# «مقدارِ» نوشته‌شده را می‌گیرد — و نمونه‌ای با 2621440 درحالی‌که کد
# عامداً 25MB انتخاب کرده، دقیقاً همان تله‌ای است که کامنتِ base.py
# هشدارش را می‌دهد. این تست مقدارِ مستندشده را با defaultِ واقعیِ کد
# (production.py وگرنه base.py) مقایسه می‌کند.

_SETTINGS_ROOTS = ("config/settings/production.py", "config/settings/base.py")

# واگرشی‌هایِ *عمدیِ* مستندشده‌درکامنت — هرکدام با دلیل؛ افزودن به این
# لیست باید با کامنتِ دلیلی در .env.example همراه باشد (قانونِ بازبینی).
_ALLOWED_VALUE_DIFFERENCES: dict[str, str] = {
    "DEBUG": "نمونهٔ onboard کردنِ dev؛ production.py همیشه False پین می‌کند.",
    "SECURE_HSTS_SECONDS": "نمونهٔ 0 برای docker-local (کامنت دارد)؛ prod پیش‌فرض 31536000.",
    "SECURE_SSL_REDIRECT": "نمونهٔ False برای پشتِ reverse-proxy لوکال؛ prod True.",
    "WHITENOISE_AUTOREFRESH": "راحتیِ dev در نمونهٔ؛ prod False.",
    "WHITENOISE_USE_FINDERS": "راحتیِ dev در نمونهٔ؛ prod False.",
    "MADADKAR_PAYMENT_CALLBACK_BASE_URL": "placeholderِ example.com به‌جای localhostِ کد.",
    "OPENAPI_SERVER_URL": "خالی‌گذاشتن = مشتق‌ازِ request؛ بهتر از پینِ localhost در نمونهٔ.",
    "FRONTEND_REVALIDATION_SECRET": "placeholderِ change-me؛ خالی‌بودنِ واقعی یعنی غیرفعال.",
    "SECRET_KEY": "placeholderِ change-me؛ مقدارِ واقعی هرگز مستند نمی‌شود.",
}

_PLACEHOLDER_MARKERS = ("change-me", "changeme", "example.com", "your-", "replace")


def _safe_literal(expr: str) -> object | None:
    """ارزیابیِ امنِ defaultهایِ سادهٔ کد: literal، arithmetic ساده، timedelta روز."""
    tree = ast.parse(expr.strip(), mode="eval")

    def _ev(node: ast.AST) -> object:
        match node:
            case ast.Constant(value=v) if isinstance(v, (int, float, str, bool)) or v is None:
                return v
            case ast.BinOp(left=l, op=ast.Mult() | ast.Add(), right=r):
                lv, rv = _ev(l), _ev(r)
                if None in (lv, rv):
                    raise ValueError
                return lv * rv if isinstance(node.op, ast.Mult) else lv + rv  # type: ignore[operator]
            case ast.Call(
                func=ast.Name(id="timedelta"),
                keywords=[ast.keyword(arg="days", value=ast.Constant(days))],
            ):  # type: ignore[misc]
                return ("timedelta-days", days)
            case _:
                raise ValueError

    try:
        return _ev(tree.body)
    except (ValueError, SyntaxError, TypeError):
        return None


def _code_defaults() -> dict[str, object]:
    """defaultهایِ واقعیِ config() در کد؛ production.py بر base.py اولویت دارد."""
    pattern = re.compile(r"config\(\s*[\"']([A-Z0-9_]+)[\"']\s*,([^)]*)\)", re.S)
    defaults: dict[str, object] = {}
    for rel in reversed(_SETTINGS_ROOTS):  # base اول، production بعد (override)
        text = (PROJECT_ROOT / rel).read_text(encoding="utf-8")
        for m in pattern.finditer(text):
            key, rest = m.group(1), m.group(2)
            dm = re.search(r"default=([^\n]+?)(?=,\s*cast=|\)|,\s*$)", rest, re.S)
            if not dm:
                continue
            value = _safe_literal(dm.group(1))
            if value is not None:
                defaults[key] = value
    return defaults


def _documented_values() -> dict[str, str]:
    """فقط خطوطِ *فعالِ* KEY=value (کامنت‌ها نمونه‌گذاریِ اختیاری‌اند، نه قرارداد)."""
    values: dict[str, str] = {}
    for line in _DOC_FILE.read_text(encoding="utf-8").splitlines():
        if line.lstrip().startswith("#"):
            continue
        match = re.match(r"^([A-Z0-9_]+)=(.*)$", line)
        if match:
            values.setdefault(match.group(1), match.group(2).strip())
    return values


def test_documented_values_match_code_defaults() -> None:
    """مقدارِ هر کلیدِ فعال در .env.example = پیش‌فرضِ واقعیِ کد (یا allowlist دلیل‌دار)."""
    defaults = _code_defaults()
    mismatches: list[str] = []
    for key, doc_raw in _documented_values().items():
        if key in _ALLOWED_VALUE_DIFFERENCES or any(mk in doc_raw for mk in _PLACEHOLDER_MARKERS):
            continue
        if key not in defaults:
            continue
        default = defaults[key]
        if isinstance(default, tuple):  # timedelta(days=N) — واحدِ متفاوت، skipِ صریح
            continue
        ok = False
        if isinstance(default, bool):
            parsed = doc_raw.lower() in ("true", "1", "yes")
            ok = parsed == bool(default)
        elif isinstance(default, (int, float)):
            try:
                ok = float(doc_raw) == float(default)
            except ValueError:
                ok = False
        else:
            ok = doc_raw == str(default)
        if not ok:
            mismatches.append(f"{key}: example={doc_raw!r} vs code-default={default!r}")
    assert not mismatches, (
        "مقادیرِ .env.example با پیش‌فرضِ واقعیِ کد واگراست — یافتۀ P2-10 فاز 8 "
        f"(کپی‌کردنِ نمونه نباید رفتار را عوض کند): {mismatches}"
    )

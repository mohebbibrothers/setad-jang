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

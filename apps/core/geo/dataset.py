"""بارگذاری و کوئری‌های خالصِ دیتاستِ جغرافیایی.

قواعد این ماژول:
  • **فقط خواندنی و بی‌حالت**: یک بار در حافظه بارگذاری می‌شود (`lru_cache`) و
    همهٔ لایه‌ها (مدل، سریالایزر، فیلتر، API، ادمین) از همین توابع می‌خوانند.
  • **بدون کوئری دیتابیس**: جدولِ استان/شهر لازم نیست؛ دیتاست کوچک (~۳۲KB) است و
    تغییرش سالی یک‌بار. اگر روزی به روستاهای ۱۰۰هزارتایی رسیدیم، همین ماژول
    نقطهٔ جایگزینی با جدولِ DB است (قراردادِ توابع تغییر نمی‌کند).
  • **نرمال‌سازیِ فارسی**: ی/ك عربی، نیم‌فاصله، فاصله‌های تکراری و اعدادِ پایانی
    («تهران ۱») یکسان می‌شوند تا `iexact` دیتابیس و مقایسهٔ پایتونی یک نتیجه بدهند.
"""

from __future__ import annotations

import json
import logging
import re
from functools import lru_cache
from pathlib import Path
from typing import Any

from django.conf import settings

logger = logging.getLogger(__name__)

DATA_FILE = Path(__file__).resolve().parent / "data" / "iran-places.json"

#: نویسه‌های عربی → فارسی (کلیدِ تطبیق، نه نمایش).
_AR_MAP = {"\u064a": "ی", "\u0643": "ک", "\u0629": "ه", "\u06c0": "ه"}
_WS_RE = re.compile(r"[\s\u200c\u200e\u200f]+")
_TRAILING_NUM_RE = re.compile(r"\s*[0-9\u06f0-\u06f9]+\s*$")


def _normalize(text: str) -> str:
    """کلیدِ مقایسه: حروفِ عربی، نیم‌فاصله، فاصله و عددِ پایانی حذف/یکسان می‌شوند."""
    out = (text or "").strip()
    for src, dst in _AR_MAP.items():
        out = out.replace(src, dst)
    out = _TRAILING_NUM_RE.sub("", out)
    return _WS_RE.sub(" ", out).strip()


def _compact(text: str) -> str:
    """کلیدِ تطبیقِ سخت‌گیرانه‌تر: بدونِ هیچ فاصله/نیم‌فاصله (اسلام‌شهر == اسلام شهر)."""
    return _WS_RE.sub("", _normalize(text))


@lru_cache(maxsize=1)
def _catalog() -> dict[str, Any]:
    """خواندنِ یک‌بارهٔ دیتاست با اعتبارسنجیِ ساختار (خرابی زودتر دیده شود)."""
    with DATA_FILE.open(encoding="utf-8") as fh:
        raw = json.load(fh)
    provinces = raw.get("provinces")
    if not isinstance(provinces, list) or not provinces:
        raise RuntimeError("iran-places.json نامعتبر است: کلید provinces خالی است.")
    return raw


@lru_cache(maxsize=1)
def province_index() -> dict[str, dict[str, Any]]:
    """نگاشتِ «کلیدِ نرمال‌شدهٔ استان → {name, tel_prefix, cities[]}»."""
    index: dict[str, dict[str, Any]] = {}
    for row in _catalog()["provinces"]:
        name = str(row.get("name", "")).strip()
        if not name:
            continue
        cities = [str(c).strip() for c in row.get("cities", []) if str(c).strip()]
        index[_compact(name)] = {
            "name": name,
            "tel_prefix": str(row.get("tel_prefix", "")).strip(),
            "cities": cities,
        }
    return index


@lru_cache(maxsize=1)
def PROVINCE_NAMES() -> tuple[str, ...]:
    """نامِ رسمیِ ۳۱ استان، به ترتیبِ دیتاست."""
    return tuple(entry["name"] for entry in province_index().values())


@lru_cache(maxsize=1)
def PROVINCE_CHOICES() -> tuple[tuple[str, str], ...]:
    """(value, label) مناسبِ `choices` جنگو — مقدار = نامِ رسمی."""
    return tuple((name, name) for name in PROVINCE_NAMES())


@lru_cache(maxsize=1)
def PROVINCE_TEL_PREFIXES() -> dict[str, str]:
    """پیش‌شمارهٔ تلفنِ هر استان (برای راهنمای فرم و اعتبارسنجیِ نرمِ شماره)."""
    return {entry["name"]: entry["tel_prefix"] for entry in province_index().values()}


def normalize_province(value: str) -> str:
    """نامِ استان را به شکلِ رسمیِ دیتاست برمی‌گرداند؛ ناشناخته → ''."""
    entry = province_index().get(_compact(value))
    return entry["name"] if entry else ""


def is_known_province(value: str) -> bool:
    """آیا این رشته یک استانِ رسمی است؟"""
    return bool(normalize_province(value))


def cities_of(province: str) -> list[str]:
    """شهرهای رسمیِ یک استان (فهرستِ خالی برای استانِ ناشناخته)."""
    entry = province_index().get(_compact(province))
    return list(entry["cities"]) if entry else []


def normalize_city(province: str, value: str) -> str:
    """شکلِ رسمیِ شهر در آن استان؛ ناشناخته → ''."""
    entry = province_index().get(_compact(province))
    if not entry:
        return ""
    key = _compact(value)
    for city in entry["cities"]:
        if _compact(city) == key:
            return city
    return ""


def is_known_city(province: str, value: str) -> bool:
    """آیا این شهر در فهرستِ رسمیِ آن استان است؟"""
    return bool(normalize_city(province, value))


@lru_cache(maxsize=1)
def _localities() -> dict[str, list[str]]:
    """روستا/محله‌های اختیاری از `IRAN_LOCALITIES_JSON` (پیش‌فرض: خالی).

    ساختارِ پذیرفته‌شده: `{"تهران": ["روستا الف", …], …}` یا لیستِ تخت
    `["تهران::روستا الف", …]`. فایلِ رسمی (~۳۲MB) آگاهانه در مخزن نیست.
    """
    raw_path = str(getattr(settings, "IRAN_LOCALITIES_JSON", "") or "").strip()
    if not raw_path:
        return {}
    path = Path(raw_path)
    if not path.is_file():
        logger.warning("IRAN_LOCALITIES_JSON موجود نیست: %s", path)
        return {}
    try:
        with path.open(encoding="utf-8") as fh:
            payload = json.load(fh)
    except (OSError, json.JSONDecodeError):
        logger.exception("خواندنِ IRAN_LOCALITIES_JSON ناموفق بود: %s", path)
        return {}

    out: dict[str, list[str]] = {}
    if isinstance(payload, dict):
        for province, items in payload.items():
            key = normalize_province(str(province))
            if not key or not isinstance(items, list):
                continue
            out[key] = sorted({str(i).strip() for i in items if str(i).strip()})
    elif isinstance(payload, list):
        for row in payload:
            text = str(row)
            if "::" not in text:
                continue
            province_raw, local = text.split("::", 1)
            key = normalize_province(province_raw)
            if key and local.strip():
                out.setdefault(key, []).append(local.strip())
        for key in out:
            out[key] = sorted(set(out[key]))
    return out


def localities_of(province: str) -> list[str]:
    """روستا/محله‌های همان استان (اگر دیتاستِ اختیاری متصل باشد)."""
    entry = province_index().get(_compact(province))
    if not entry:
        return []
    return list(_localities().get(entry["name"], []))


def places_catalog(
    *, with_counts: bool = False, counts: dict[str, int] | None = None
) -> list[dict]:
    """کاتالوگِ کامل برای API: استان + شهرها + (اختیاری) شمارندهٔ آگهی‌های جاری."""
    catalog: list[dict] = []
    for entry in province_index().values():
        name = entry["name"]
        row: dict[str, Any] = {
            "name": name,
            "tel_prefix": entry["tel_prefix"],
            "cities": entry["cities"],
        }
        if with_counts:
            row["listings_count"] = int((counts or {}).get(name, 0))
        catalog.append(row)
    return catalog


def validate_place_pair(province: str, city: str) -> tuple[str, str, list[str]]:
    """اعتبارسنجیِ جفتِ (استان، شهر).

    برمی‌گرداند `(province_normalized, city_normalized, errors)`:
      • استانِ خالی مجاز است (یعنی «سراسر کشور») — با شهرِ پرشده ناسازگار است.
      • شهر باید در فهرستِ رسمیِ همان استان باشد؛ ناشناخته ⇒ خطا با پیشنهادِ
        نزدیک‌ترین نام (کمکِ ادمین بدونِ حدس زدن).
    """
    errors: list[str] = []
    province_raw = (province or "").strip()
    city_raw = (city or "").strip()

    if not province_raw:
        if city_raw:
            errors.append(
                "برای ثبتِ شهر، ابتدا استان را انتخاب کنید (یا هر دو را خالی بگذارید = سراسر کشور)."
            )
        return "", "", errors

    province_norm = normalize_province(province_raw)
    if not province_norm:
        errors.append(f"استانِ «{province_raw}» در فهرستِ رسمی نیست.")
        return "", "", errors

    if not city_raw:
        return province_norm, "", errors

    city_norm = normalize_city(province_norm, city_raw)
    if not city_norm:
        suggestions = _suggest_cities(province_norm, city_raw)
        hint = f" نزدیک‌ترین گزینه‌ها: {'، '.join(suggestions)}." if suggestions else ""
        errors.append(f"شهرِ «{city_raw}» در استانِ {province_norm} نیست.{hint}")
        return province_norm, "", errors

    return province_norm, city_norm, errors


def _suggest_cities(province: str, value: str, limit: int = 3) -> list[str]:
    """سه شهرِ نزدیک از نظرِ اشتراکِ نویسه‌ها — راهنمای ادمین، نه حدسِ خودکار."""
    target = _compact(value)
    if not target:
        return []
    scored: list[tuple[int, str]] = []
    for city in cities_of(province):
        candidate = _compact(city)
        score = len({c for c in target} & {c for c in candidate})
        if target[:2] and candidate.startswith(target[:2]):
            score += 3
        scored.append((score, city))
    scored.sort(key=lambda pair: (-pair[0], len(pair[1])))
    return [city for score, city in scored[:limit] if score > 0]

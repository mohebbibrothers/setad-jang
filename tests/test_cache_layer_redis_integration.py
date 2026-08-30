"""تست یکپارچگیِ لایهٔ کش روی **Redis واقعی** — یافتۀ P2-7 فاز 8.

چرا این فایل وجود دارد:
    لایۀ کشِ پروژه (django_redis + JSONSerializer + ZlibCompressor +
    namespace-version + SWR) روی production دقیقاً همین stack اجرا می‌شود،
    ولی تا پیش از این، همهٔ تست‌ها روی locmem/mock بودند — یعنی یک باگِ
    serializer می‌توانست کل کشِ prod را بی‌صدا از کار بیندازد و CI سبز بماند.
    این فایل همان حلقهٔ مفقود است: روی Redisِ واقعیِ CI اجرا می‌شود و
    رفتارِ *سریالایزیشن* را نه رفتارِ فرضی، می‌نویسد.

شرایط اجرا:
    - `CACHE_BACKEND=redis` (CI: گام «Cache layer on real Redis»)
    - redis در REDIS_URL پاسخ ping بدهد؛ وگرنه کل ماژول skip می‌شود
      (الگوی postgres-only‌ها؛ local بدونِ redis هیچ‌وقت قرمز نمی‌شود).

اتفاقِ مهمی که اینجا *مستند* می‌شود (و نه به‌عنوان باگِ جدید):
    JSONSerializer = json.dumps با DjangoJSONEncoder → Decimal به **float**
    و datetime به **رشتهٔ ISO** تبدیل می‌شود و tuple به list. اگر روزی کسی
    مقدارِ پولیِ Decimal را عیناً برگرداند، شکند — پس این تست عمداً float بودن
    را assert می‌کند تا «انتظارِ غلطِ بعدی» همین‌جا خفه شود.
"""

from __future__ import annotations

import datetime as dt
import json
from decimal import Decimal

import pytest
from django.core.cache import cache

from apps.core.cache import (
    cache_delete_namespace,
    cache_get_or_set,
    cache_get_or_set_swr,
    get_namespace_version,
    make_cache_key,
)


def _redis_connection():  # pragma: no cover - helper
    from django_redis import get_redis_connection

    return get_redis_connection("default")


def _redis_is_live() -> bool:
    """pingِ کوتاه؛ failure یعنی محیط Redis ندارد → skip منطقیِ کل ماژول."""
    try:
        conn = _redis_connection()
        return bool(conn.ping())
    except Exception:
        return False


pytestmark = [
    pytest.mark.redis,
    pytest.mark.skipif(
        "redis" not in str(cache.__class__.__module__),
        reason="این تست‌ها فقط با CACHE_BACKEND=redis معنادارند (django_redis فعال باشد).",
    ),
]


@pytest.fixture(name="redis_conn")
def redis_conn_fixture():
    """کانکشنِ خامِ redis برای سنجشِ آنچه *واقعاً* در سرور ذخیره شده."""
    if not _redis_is_live():
        pytest.skip("Redis در REDIS_URL در دسترس نیست؛ این تست‌ها CI-محورند.")
    return _redis_connection()


@pytest.fixture(autouse=True)
def _isolate_namespace():
    """هر تست namespace و keys‌های تازه می‌گیرد؛ هیچ آلودگیِ متقابل‌ای نه."""
    yield
    cache.clear()


def _unique(ns: str) -> str:
    return f"pg8test:{ns}"


def test_json_serializer_roundtrip_of_json_safe_types(redis_conn) -> None:
    """dict/list/str-fa/int/bool/None باید سالم و *دقیق* برگردند."""
    payload = {
        "عنوان": "سهمِ مردمی ✔",
        "counts": [1, 2, 3],
        "flag": True,
        "nil": None,
        "nested": {"x": {"y": -17.5}},
    }
    key = _unique("roundtrip")
    cache.set(key, payload, 60)
    assert cache.get(key) == payload


def test_decimal_and_datetime_are_coerced_by_design(redis_conn) -> None:
    """Decimal→float، datetime→ISO-string؛ این قراردادِ JSONSerializer است.

    اگر کسی روزی این‌ها را «همان نوعِ اصلی» انتظار داشت، این تست می‌گوید
    لایهٔ کشِ این پروژه جایِ پولِ Decimal نیست: یا int/strِ پولی ذخیره کن،
    یاسریال‌سازِ سفارشی اضافه کن — ولی انتظارت را به واقعیتِ بک‌اند گره بزن.
    """
    key = _unique("coercion")
    cache.set(
        key,
        {
            "amount": Decimal("1234.56"),
            "when": dt.datetime(2026, 8, 30, 12, 30, tzinfo=dt.UTC),
            "pair": (1, 2),
        },
        60,
    )
    got = cache.get(key)
    assert got["amount"] == 1234.56
    assert isinstance(got["amount"], float)
    assert got["when"] == "2026-08-30T12:30:00+00:00"
    assert got["pair"] == [1, 2]  # tuple→list در json


def test_zlib_compressor_actually_compresses_on_server(redis_conn) -> None:
    """valueٔ ذخیره‌شده در redis باید gzip/zlib-magic باشد، نه plain json.

    اگر روزی COMPRESSOR از تنظیمات بیفتد، این تست (و نه لاگِ prod) می‌گوید:
    پیکربندی drift کرده و مصرفِپهنای‌باندِ کش بالا رفته است.
    """
    key = make_cache_key(_unique("compress"), "x" * 200)
    cache.set(key, {"big": "compress me " * 100}, 120)
    stored = redis_conn.get(cache.make_key(key))
    assert stored is not None, "کلید باید در redis وجود داشته باشد"
    assert stored[:1] in {b"\x78"}, f"امضایِ zlib انتظار است، دریافت شد: {stored[:4]!r}"
    # و حالا roundtrip کامل از همان مسیرِ decompress:
    assert cache.get(key)["big"] == "compress me " * 100


def test_key_prefix_isolates_namespace(redis_conn) -> None:
    """KEY_PREFIX= setadjang + version در نامِ واقعیِ کلید باید دیده شود."""
    key = _unique("prefix")
    cache.set(key, 1, 60)
    real = cache.make_key(key)
    assert "setadjang" in real


def test_swr_envelope_is_plain_json_not_pickle(redis_conn) -> None:
    """ساختارِ SWR باید JSONِ خالص باشد تا با serializerِ پروژه سازگار بماند.

    اگر envelope به objectِ سفارشی (با __dict__) تبدیل شود، روی redis
    می‌شکند — این تست همان قراردادِ «JSON-safe envelope» را قفل می‌کند.
    """

    def loader() -> dict:
        return {"v": 1}

    key = _unique("swr")
    first = cache_get_or_set_swr(key=key, factory=loader, soft_ttl=30, hard_ttl=60)
    assert first == {"v": 1}
    raw = redis_conn.get(cache.make_key(key))
    decoded = json.loads(raw)
    assert decoded["__swr_cache_envelope__"] is True
    assert decoded["value"] == {"v": 1}
    assert isinstance(decoded["soft_expires_at"], (int, float))


def test_namespace_version_bump_invalidates_old_keys(redis_conn) -> None:
    """invalidateٔ namespace باید کلیدهایِ نسخهٔ قدیم را از مسیرِخواندن محو کند."""
    ns = _unique("nsv")
    v1 = get_namespace_version(ns)
    key_v1 = make_cache_key(ns, v1, "page-1")
    cache.set(key_v1, "old", 120)
    assert cache.get(key_v1) == "old"

    cache_delete_namespace(ns)
    v2 = get_namespace_version(ns)
    assert v2 == v1 + 1

    key_v2 = make_cache_key(ns, v2, "page-1")
    assert cache.get(key_v2) is None  # نسخهٔ تازه، داده ندارد
    # داده‌های نسخهٔ کهنه دیگر هرگز خوانده نمی‌شوند (کلیدِ ساخته‌شده عوض شده):
    assert make_cache_key(ns, v2, "page-1") != key_v1


def test_cache_get_or_set_populates_once(redis_conn) -> None:
    """get_or_set باید فراخوانیِ compute را به یک‌بار برساند (حالتِ گرم/سرد)."""
    calls = {"n": 0}

    def compute() -> str:
        calls["n"] += 1
        return "computed"

    key = _unique("getorset")
    assert cache_get_or_set(key, lambda: compute(), timeout=60) == "computed"
    assert cache_get_or_set(key, lambda: compute(), timeout=60) == "computed"
    assert calls["n"] == 1


def test_ttl_reaches_the_server(redis_conn) -> None:
    """TTLِ داده‌شده به cache باید ttlِ واقعیِ redis بماند (نه بی‌نهایت)."""
    key = _unique("ttl")
    cache.set(key, "x", 5)
    remaining = redis_conn.ttl(cache.make_key(key))
    assert 0 < remaining <= 5

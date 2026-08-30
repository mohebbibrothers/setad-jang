"""قراردادِ k6 ↔ OpenAPI (رفع F2 ممیزی ۲۰۲۶-۰۸-۳۰).

درسِ F2: اسکریپت بارسنجیِ اول، مسیر/فیلدها را حدسی نوشته بود و checkها
404 را «پاس» می‌گرفتند — یعنی ابزارِ سبزِ بی‌معنا. این گیت همان را
ریاضی‌وار می‌بندد: هر endpointِ موجود در JS باید در schema.yaml وجود
داشته باشد و کلیدهای payloadش زیرمجموعۀ propertiesِ همان operation.
driftِ مسیر/فیلدِ API = شکستِ CI، نه سکریپتِ خاموش.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
import yaml

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parent.parent
JS_PATH = ROOT / "deploy/loadtest/k6_auth_participation.js"
SCHEMA_PATH = ROOT / "schema.yaml"


@pytest.fixture(name="schema")
def schema_fixture() -> dict:
    return yaml.safe_load(SCHEMA_PATH.read_text(encoding="utf-8"))


def _js_paths() -> list[str]:
    """${BASE}<literal-path>های داخل http.post() — با paramها به‌صورت {…} نرمال."""
    src = JS_PATH.read_text(encoding="utf-8")
    raw = re.findall(r"`\$\{BASE\}([^`]*)`", src)
    out = []
    for item in raw:
        # split('/'),
        # encodeURIComponent(...) segments -> {param}
        segs = item.split("/")
        norm = []
        for seg in segs:
            if seg.startswith("${"):
                norm.append("{param}")
            else:
                norm.append(seg)
        out.append("/".join(norm))
    assert out, "هیچ endpointی در k6 پیدا نشد — فایل دست‌کاری شده؟"
    return out


def _js_payloads() -> dict[str, list[str]]:
    """نگاشت path → کلیدهای JSON.stringify({...})ِ بعداز آن http.post."""
    src = JS_PATH.read_text(encoding="utf-8")
    pairs: dict[str, list[str]] = {}
    for m in re.finditer(
        r"http\.post\(\s*`\$\{BASE\}([^`]*)`,\s*JSON\.stringify\(\{([^}]*)\}\)",
        src,
        re.S,
    ):
        path = "/".join("{param}" if seg.startswith("${") else seg for seg in m.group(1).split("/"))
        keys = re.findall(r"([A-Za-z_][A-Za-z0-9_]*)\s*:", m.group(2))
        pairs[path] = keys
    return pairs


def _match_schema_path(schema: dict, js_path: str) -> str:
    """مسیر JS (با {param} نرمال) را به کلیدِ schema نگاشت می‌کند."""
    for key in schema.get("paths", {}):
        if re.sub(r"\{[^}]+\}", "{param}", key) == js_path:
            return key
    pytest.fail(f"مسیر k6 در OpenAPI نیست: {js_path!r} — مسیر عوض شده یا اسکریپت پوسیده")


def _op_request_props(schema: dict, path_key: str, method: str = "post") -> set[str]:
    op = schema["paths"][path_key][method]
    body = op.get("requestBody", {}).get("content", {})
    for media in body.values():
        ref = media.get("schema", {}).get("$ref")
        if ref:
            name = ref.rsplit("/", 1)[-1]
            props = schema["components"]["schemas"][name].get("properties", {})
            return set(props)
        inline = media.get("schema", {}).get("properties")
        if inline:
            return set(inline)
    return set()


@pytest.mark.parametrize("js_path", _js_paths())
def test_endpoint_exists_in_openapi(js_path: str) -> None:
    schema = yaml.safe_load(SCHEMA_PATH.read_text(encoding="utf-8"))
    _match_schema_path(schema, js_path)


def test_payload_fields_are_valid_against_openapi() -> None:
    schema = yaml.safe_load(SCHEMA_PATH.read_text(encoding="utf-8"))
    payloads = _js_payloads()
    assert len(payloads) >= 3, "انتظار ۳ POST با payload داشتیم"
    for js_path, keys in payloads.items():
        path_key = _match_schema_path(schema, js_path)
        props = _op_request_props(schema, path_key)
        if not props:
            continue  # endpoint بدون body (نظیر GET) — برای POST رخ نمی‌دهد
        unknown = set(keys) - props
        assert not unknown, f"فیلد(های) جعلی k6 در {path_key}: {sorted(unknown)}"


def test_checks_reject_404() -> None:
    """ضدِ «سبزِ بی‌معنا»: چک‌ها باید 404/405 را شکست بدانند."""
    src = JS_PATH.read_text(encoding="utf-8")
    assert "route alive" in src
    assert "404" in src and "405" in src
    # الگوی قدیمیِ (not-5xx تنها) نباید برگردد:
    assert "r.status < 500" in src  # مجاز، ولی باید *در کنارش* routeAlive باشد
    assert src.count("routeAlive(r)") >= 3

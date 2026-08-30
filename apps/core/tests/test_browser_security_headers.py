"""تست‌های هدرهای امنیتی مرورگری (یافتهٔ P2-۹ فاز ۸).

قراردادها:
- /admin/ و صفحه‌های docs هرکدام CSPِ پروفایلِ خودشان را می‌گیرند؛ ادمین هیچ
  origin خارجی ندارد و docs فقط CDNِ تنظیم‌شده در SPECTACULAR_SETTINGS را.
- پاسخ‌های API (JSON) CSP نمی‌گیرند (ریسکِ render ندارند و شکستنِ clientها
  با header بی‌مورد است) ولی Permissions-Policy روی همه‌چیز هست.
- SECURE_CSP_ENFORCE=False → Report-Only وگرنه enforce؛ flagِ خاموشیِ کلی هم
  باید واقعاً همه‌چیز را بردارد (مسیرِ incident).
- تنظیمِ production روی COOP در خودِ فایلِ settings پین است (guard متنی مثل
  تست‌های runbook) تا کسی بی‌خبر حذفش نکند.
"""

from __future__ import annotations

import pytest
from django.conf import settings as dj_settings

pytestmark = pytest.mark.django_db


def test_admin_gets_strict_csp_without_external_origins(client) -> None:
    """ادمین: frame-ancestors none، بدون jsdelivr/CDN؛ inline فقط برای admin."""
    response = client.get("/admin/login/")
    csp = response["Content-Security-Policy"]
    assert "frame-ancestors 'none'" in csp
    assert "default-src 'none'" in csp
    assert "cdn." not in csp  # هیچ origin خارجی در CSPِ ادمین مجاز نیست


def test_docs_csp_includes_configured_spectacular_cdn(client) -> None:
    """پروفایل docs باید CDNِ واقعیِ SPECTACULAR را منعکس کند (نه hardcode)."""
    response = client.get("/api/docs/")
    csp = response["Content-Security-Policy"]
    assert "frame-ancestors 'none'" in csp
    # در این تست environment مقدارِ پیش‌فرضِ spectacular (jsdelivr) ست است؛
    # اگر روزی اپراتور عوض کند، همین تست از همان تنظیم می‌خواند.
    from urllib.parse import urlsplit

    spectacular = dj_settings.SPECTACULAR_SETTINGS
    dist = str(
        spectacular.get("SWAGGER_UI_DIST") or "https://cdn.jsdelivr.net/npm/swagger-ui-dist@latest"
    )
    parts = urlsplit(dist)
    assert f"{parts.scheme}://{parts.netloc}" in csp


def test_docs_csp_tracks_custom_cdn(client, settings) -> None:
    """تغییرِ SWAGGER_UI_DIST باید CSP را هم جابه‌جا کند — ضدِ driftِ دستی."""
    settings.SPECTACULAR_SETTINGS = {
        **dj_settings.SPECTACULAR_SETTINGS,
        "SWAGGER_UI_DIST": "https://cdn.example-mirror.test/swagger-ui-bundle.js",
    }
    response = client.get("/api/docs/")
    assert "https://cdn.example-mirror.test" in response["Content-Security-Policy"]


def test_api_responses_get_permissions_policy_but_no_csp(client) -> None:
    """کل API بسته است و JSON بی‌دلیل CSP نمی‌گیرد."""
    response = client.get("/api/v1/health/")
    policy = response["Permissions-Policy"]
    assert "camera=()" in policy
    assert "microphone=()" in policy
    assert "geolocation=()" in policy
    assert "Content-Security-Policy" not in response
    assert "Content-Security-Policy-Report-Only" not in response


def test_report_only_mode(client, settings) -> None:
    """چرخهٔ اولِ استقرار: هدرِ Report-Only و بدونِ enforce."""
    settings.SECURE_CSP_ENFORCE = False
    response = client.get("/admin/login/")
    assert "Content-Security-Policy-Report-Only" in response
    assert "Content-Security-Policy" not in response


def test_kill_switch_removes_all_headers(client, settings) -> None:
    """flagِ خاموشیِ اضطراری باید واقعاً همه‌چیز را بردارد."""
    settings.SECURE_BROWSER_HEADERS_ENABLED = False
    response = client.get("/admin/login/")
    assert "Content-Security-Policy" not in response
    assert "Permissions-Policy" not in response


def test_explicit_csp_on_response_is_not_overridden() -> None:
    """middleware باید viewی را که خودش CSP ست کرده بپوشاند (setdefault نیست).

    چکِ ترتیبِ 'header not in response' با نمونه‌سازیِ پاسخِ سفارشی:
    یک view سرِ‌مسیرِ admin که هدر را خودش می‌دهد را نمی‌توان اینجا ساخت،
    پس مستقیماً روی __call__ِ middleware تست می‌شود.
    """
    from django.http import HttpResponse

    from apps.core.browser_headers import BrowserSecurityHeadersMiddleware

    def inner(request):
        response = HttpResponse("x")
        response["Content-Security-Policy"] = "script-src 'self'"
        return response

    middleware = BrowserSecurityHeadersMiddleware(inner)
    request = _admin_login_request()
    response = middleware(request)
    assert response["Content-Security-Policy"] == "script-src 'self'"
    assert "Permissions-Policy" in response  # بقیهٔ هدرها دست‌نخورده می‌مانند


def _admin_login_request():
    """ساختِ HttpRequestِ /admin/login/ بدونِ client — برای تستِ واحدِ middleware."""
    from django.test import RequestFactory

    return RequestFactory().get("/admin/login/")


def test_production_settings_pin_coop() -> None:
    """guard متنی: production.py باید COOP را صریح تنظیم کند (P2-9)."""
    from pathlib import Path

    source = Path(dj_settings.BASE_DIR, "config/settings/production.py").read_text(encoding="utf-8")
    assert "SECURE_CROSS_ORIGIN_OPENER_POLICY" in source

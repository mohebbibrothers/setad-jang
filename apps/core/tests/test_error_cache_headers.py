"""قراردادِ «خطا هرگز کش نمی‌شود» (حادثهٔ ۴۰۴ِ یک‌هفته‌ای روی لبهٔ CDN).

چرا این تست وجود دارد
---------------------
روی استقرارِ واقعی، `/media/...` و `/static/...` با استاتوسِ ۴۰۴ ولی بدنهٔ
درست برگشتند و همان پاسخ با `Cache-Control: public, max-age=604800` روی لبهٔ
CDN کش شد. بعد از رفعِ ریشه (سیم‌لینکِ assets)، همان URLها تا یک هفته
«خراب» می‌ماندند چون کش پاسخِ خطا را سرو می‌کرد.

قاعده‌ای که اینجا پین می‌شود:
    - پاسخِ موفق همان سیاستِ کشِ خودش را نگه می‌دارد (SWR/immutable/...)
    - هر پاسخِ ۴xx/۵xx باید `no-store` بگیرد، حتی اگر view هدرِ دیگری ست کرده باشد
"""

from __future__ import annotations

import pytest
from django.http import HttpResponse
from django.test import RequestFactory, override_settings

from apps.core.browser_headers import BrowserSecurityHeadersMiddleware


def _run(status_code: int, headers: dict[str, str] | None = None) -> HttpResponse:
    def get_response(_request):
        response = HttpResponse("x", status=status_code)
        for key, value in (headers or {}).items():
            response[key] = value
        return response

    middleware = BrowserSecurityHeadersMiddleware(get_response)
    return middleware(RequestFactory().get("/whatever/"))


@pytest.mark.parametrize("status_code", [400, 401, 403, 404, 410, 429, 500, 502, 504])
def test_error_responses_are_never_cacheable(status_code: int) -> None:
    response = _run(status_code, {"Cache-Control": "public, max-age=604800"})

    assert response.status_code == status_code
    cache_control = response["Cache-Control"]
    assert "no-store" in cache_control
    assert "max-age=0" in cache_control
    assert "public" not in cache_control
    assert "604800" not in cache_control
    assert response["Pragma"] == "no-cache"


@pytest.mark.parametrize("status_code", [200, 201, 204, 206, 301, 302, 304])
def test_success_and_redirects_keep_their_own_policy(status_code: int) -> None:
    response = _run(status_code, {"Cache-Control": "public, max-age=604800"})

    assert response.status_code == status_code
    assert response["Cache-Control"] == "public, max-age=604800"


@override_settings(SECURE_BROWSER_HEADERS_ENABLED=False)
def test_error_cache_neutralisation_survives_the_kill_switch() -> None:
    """پرچمِ خاموشیِ اضطراری باید فقط هدرهای *امنیتی* را بردارد، نه این قاعده را.

    کشِ یک‌هفته‌ایِ یک ۴۰۴ ربطی به CSP/COOP ندارد؛ خاموش‌کردنِ آن نباید
    دوباره در را باز کند.
    """
    response = _run(404, {"Cache-Control": "public, max-age=604800"})

    assert "no-store" in response["Cache-Control"]
    assert "Permissions-Policy" not in response

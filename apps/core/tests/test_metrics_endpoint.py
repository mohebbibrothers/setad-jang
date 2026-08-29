"""دروازهٔ دسترسی و صحتِ aggregate در endpoint متریک‌ها (یافتهٔ P1 فاز ۷).

سه قرارداد که این فایل قفل می‌کند:
1. production بدونِ `PROMETHEUS_METRICS_TOKEN` → endpoint عملاً وجود ندارد (404).
2. توکنِ درست در هدر Bearer → 200 و بدنهٔ exposition واقعی؛ توکنِ غلط/خالی → 404.
3. حالت multiprocess: `exposition_registry()` در وجود env متغیر یک registry
   تازهٔ MultiProcessCollector برمی‌گرداند و در نبودِ آن None (registry
   پیش‌فرض) — تفکیکی که بی‌آن، متریک‌ها در gunicorn چندworkerی ~۱/N واقعیت
   را نشان می‌دادند.
"""

from __future__ import annotations

import pytest
from rest_framework.test import APIClient

from apps.core.metrics import exposition_registry, multiprocess_mode_enabled

_METRICS_URL = "/api/v1/metrics/"


def _get(client: APIClient | None = None):
    return (client or APIClient()).get(_METRICS_URL)


def test_open_in_debug(settings) -> None:
    """محیط توسعه بدون ceremonial باز است (dev/local scrape)."""
    settings.DEBUG = True
    response = _get()
    assert response.status_code == 200
    assert b"setadjang_http_requests_total" in response.content


def test_production_without_token_is_fail_closed_404(settings) -> None:
    """اپراتور توکن تنظیم نکرده؟ endpoint نباید باز بماند (P1-2)."""
    settings.DEBUG = False
    settings.PROMETHEUS_METRICS_TOKEN = ""
    assert _get().status_code == 404


def test_production_requires_bearer_token(settings) -> None:
    """فقط Bearerِ درست می‌گذرد؛ غلط/بدون هدر همان 404 را می‌گیرند."""
    settings.DEBUG = False
    settings.PROMETHEUS_METRICS_TOKEN = "s3cret-scraper-token"

    assert _get().status_code == 404

    wrong = APIClient()
    wrong.credentials(HTTP_AUTHORIZATION="Bearer wrong-token")
    assert _get(wrong).status_code == 404

    sneaky = APIClient()
    sneaky.credentials(HTTP_AUTHORIZATION="Token s3cret-scraper-token")
    assert _get(sneaky).status_code == 404

    ok = APIClient()
    ok.credentials(HTTP_AUTHORIZATION="Bearer s3cret-scraper-token")
    response = _get(ok)
    assert response.status_code == 200
    assert b"setadjang_" in response.content


def test_disabled_flag_still_404_even_with_token(settings) -> None:
    """PROMETHEUS_METRICS_ENABLED=False یعنی خاموش، حتی با توکن معتبر."""
    settings.DEBUG = False
    settings.PROMETHEUS_METRICS_ENABLED = False
    settings.PROMETHEUS_METRICS_TOKEN = "s3cret-scraper-token"

    ok = APIClient()
    ok.credentials(HTTP_AUTHORIZATION="Bearer s3cret-scraper-token")
    assert _get(ok).status_code == 404


def test_multiprocess_mode_detection(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    """با env ست‌شده حالت multiprocess فعال و registry تازه است."""
    monkeypatch.setenv("PROMETHEUS_MULTIPROC_DIR", str(tmp_path))
    assert multiprocess_mode_enabled() is True

    from prometheus_client import CollectorRegistry

    registry = exposition_registry()
    assert isinstance(registry, CollectorRegistry)
    assert registry is not None

    # دایرکتوری خالی = هنوز هیچ workerی چیزی ننوشته؛ رندر نباید منفجر شود.
    from prometheus_client import generate_latest

    assert isinstance(generate_latest(registry), bytes)


def test_single_process_mode_uses_default_registry(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """بدون env، خودِ REGISTRY پیش‌فرض سرو می‌شود (بدون wrapper اضافه)."""
    from prometheus_client import REGISTRY

    monkeypatch.delenv("PROMETHEUS_MULTIPROC_DIR", raising=False)
    assert multiprocess_mode_enabled() is False
    assert exposition_registry() is REGISTRY

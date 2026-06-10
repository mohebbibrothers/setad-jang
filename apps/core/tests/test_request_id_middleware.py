"""
Tests — apps.core.middleware.RequestIDMiddleware

این تست‌ها contract کامل middleware را verify می‌کنند:
- وقتی client هیچ X-Request-ID نمی‌فرستد، سرور یک id جدید می‌سازد
- وقتی client یک X-Request-ID معتبر می‌فرستد، همان مقدار حفظ می‌شود
- وقتی client مقدار نامعتبر/خطرناک می‌فرستد، سرور آن را drop کرده و id جدید می‌سازد
- response هم header `X-Request-ID` را شامل می‌شود
- خارج از HTTP request، get_current_request_id() مقدار پیش‌فرض "-" برمی‌گرداند

اصول طراحی:
- از `RequestFactory` و یک view ساختگی استفاده می‌شود تا تست:
  * مستقل از urlconf، DB، auth و throttling باشد
  * به سرعت و deterministic اجرا شود
  * فقط همان مرز middleware را verify کند، نه چیز دیگر
- این الگوی صنعتی برای تست middleware در Django است.
"""

from __future__ import annotations

import pytest
from django.http import HttpResponse
from django.test import RequestFactory

from apps.core.middleware import (
    REQUEST_ID_HEADER,
    RequestIDMiddleware,
    get_current_request_id,
)


@pytest.fixture
def request_factory() -> RequestFactory:
    return RequestFactory()


def _dummy_view(request) -> HttpResponse:
    """
    یک view ساختگی برای ارسال به middleware.

    عمداً ساده نگه‌داشته شده تا تست مستقل از view logic باشد.
    """
    return HttpResponse("ok")


def _run_middleware(
    factory: RequestFactory,
    *,
    inbound: str | None = None,
) -> HttpResponse:
    """
    اجرای middleware با یک GET request ساختگی روی مسیر `/`.

    اگر inbound داده شود، به‌عنوان X-Request-ID در درخواست ست می‌شود.
    """
    middleware = RequestIDMiddleware(_dummy_view)

    extra = {}
    if inbound is not None:
        extra["HTTP_X_REQUEST_ID"] = inbound

    request = factory.get("/", **extra)
    return middleware(request)


# ============================================================
# Server-generated request id
# ============================================================


class TestRequestIDGeneration:
    """وقتی client هیچ id نفرستد، سرور باید یک id جدید بسازد."""

    def test_response_contains_generated_request_id(self, request_factory: RequestFactory) -> None:
        response = _run_middleware(request_factory)

        request_id = response.headers.get(REQUEST_ID_HEADER)
        assert isinstance(request_id, str)
        assert request_id  # غیرخالی
        assert all(ch.isalnum() or ch in {"-", "_"} for ch in request_id)


# ============================================================
# Client-provided request id (valid)
# ============================================================


class TestRequestIDPropagation:
    """اگر client یک id معتبر بفرستد، باید همان حفظ شود."""

    def test_inbound_valid_request_id_is_preserved(self, request_factory: RequestFactory) -> None:
        inbound = "client-trace-abc123"

        response = _run_middleware(request_factory, inbound=inbound)

        assert response.headers.get(REQUEST_ID_HEADER) == inbound


# ============================================================
# Client-provided request id (invalid → must be replaced)
# ============================================================


class TestRequestIDSanitization:
    """ورودی نامعتبر باید drop شود و id جدید سرور جایگزین شود."""

    def test_too_long_request_id_is_replaced(self, request_factory: RequestFactory) -> None:
        too_long = "a" * 500

        response = _run_middleware(request_factory, inbound=too_long)

        returned = response.headers.get(REQUEST_ID_HEADER)
        assert returned is not None
        assert returned != too_long
        assert len(returned) <= 128

    def test_request_id_with_unsafe_chars_is_replaced(
        self, request_factory: RequestFactory
    ) -> None:
        unsafe = "value with spaces and ;injection"

        response = _run_middleware(request_factory, inbound=unsafe)

        returned = response.headers.get(REQUEST_ID_HEADER)
        assert returned is not None
        assert returned != unsafe

    def test_empty_request_id_is_replaced(self, request_factory: RequestFactory) -> None:
        response = _run_middleware(request_factory, inbound="   ")

        returned = response.headers.get(REQUEST_ID_HEADER)
        assert returned is not None
        assert returned.strip() != ""


# ============================================================
# Context variable behavior outside HTTP request
# ============================================================


class TestRequestIDContextDefault:
    """خارج از HTTP request باید مقدار پیش‌فرض '-' برگردد."""

    def test_get_current_request_id_returns_dash_outside_request(self) -> None:
        # هیچ middleware در این لحظه فعال نیست → باید مقدار default برگردد
        assert get_current_request_id() == "-"

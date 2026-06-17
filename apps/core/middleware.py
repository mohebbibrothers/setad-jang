"""
Cross-cutting middlewares for Setad Jang project.

این ماژول شامل middlewareهایی است که cross-cutting concerns را پوشش می‌دهند
و به هیچ اپ خاصی تعلق ندارند. الان فقط شامل RequestIDMiddleware است.

اصول طراحی:
- middlewareها باید سبک باشند تا overhead به request lifecycle اضافه نکنند.
- هیچ business logic داخل middleware نیست؛ صرفاً enrich کردن request/response.
- request_id با استفاده از contextvars نگه‌داری می‌شود تا در هر context async/threading
  ایزوله بماند (سازگار با gunicorn workers و asyncio).

دلیل وجود این middleware:
- در محیط production، logها از چندین منبع جمع می‌شوند (web, worker, beat, ...).
- بدون یک شناسه‌ی مشترک، debugging یک flow کامل غیرعملی است.
- این middleware یک شناسه‌ی پایدار به هر درخواست می‌دهد که در logs و response headers
  منعکس می‌شود تا client و سرور بتوانند یک flow را track کنند.
"""

from __future__ import annotations

import contextvars
import logging
import uuid
from collections.abc import Callable

from django.conf import settings
from django.http import HttpRequest, HttpResponse

logger = logging.getLogger("apps.core.middleware")


# ============================================================
# Public constants
# ============================================================

#: نام HTTP header استاندارد برای ارسال/دریافت Request ID.
#: این نام در صنعت رایج است (مثل ابزارهای Heroku, AWS, Cloudflare).
REQUEST_ID_HEADER = "X-Request-ID"

#: حداکثر طول مجاز برای request_id ورودی از client. هر چیزی بلندتر از این
#: مقدار به‌صورت دفاعی drop شده و یک id جدید سرور تولید می‌شود.
_MAX_INBOUND_REQUEST_ID_LENGTH = 128


# ============================================================
# Context variable
# ============================================================

#: متغیر context-local برای نگه‌داری request_id فعلی.
#: فرمتر logging از اینجا مقدار را می‌خواند تا در پیام log درج کند.
_request_id_var: contextvars.ContextVar[str] = contextvars.ContextVar(
    "setadjang_request_id",
    default="-",
)


def get_current_request_id() -> str:
    """
    دسترسی read-only به request_id فعلی.

    اگر هیچ middleware راه‌اندازی نشده باشد یا خارج از یک HTTP request
    صدا زده شود (مثل اجرای task در Celery)، مقدار پیش‌فرض "-" برمی‌گردد.
    """
    return _request_id_var.get()


def _coerce_inbound_request_id(value: str | None) -> str | None:
    """
    اعتبارسنجی دفاعی request_id ورودی از client.

    اگر مقدار بلند، خالی، یا حاوی خطر injection باشد، None برمی‌گرداند
    تا middleware یک id جدید بسازد.
    """
    if not value:
        return None

    candidate = value.strip()
    if not candidate:
        return None

    if len(candidate) > _MAX_INBOUND_REQUEST_ID_LENGTH:
        return None

    # فقط کاراکترهای امن: حروف، اعداد، خط فاصله و زیرخط
    safe = all(ch.isalnum() or ch in {"-", "_"} for ch in candidate)
    if not safe:
        return None

    return candidate


# ============================================================
# Middleware
# ============================================================


class RequestIDMiddleware:
    """
    Middleware برای ضمیمه کردن یک شناسه‌ی یکتا به هر HTTP request.

    رفتار:
    - اگر header ورودی `X-Request-ID` معتبر بود، همان مقدار استفاده می‌شود
      (برای حفظ correlation در reverse-proxyها و microserviceها).
    - در غیر این صورت، یک UUID4 جدید تولید می‌شود.
    - مقدار نهایی هم در response header برگردانده می‌شود
      تا client بتواند برای پشتیبانی به آن ارجاع دهد.

    اگر یک اپ نیاز داشته باشد به این مقدار دسترسی داشته باشد، باید از
    `apps.core.middleware.get_current_request_id()` استفاده کند.
    """

    def __init__(
        self,
        get_response: Callable[[HttpRequest], HttpResponse],
    ) -> None:
        self._get_response = get_response

    def __call__(self, request: HttpRequest) -> HttpResponse:
        inbound = request.META.get("HTTP_X_REQUEST_ID")
        request_id = _coerce_inbound_request_id(inbound) or uuid.uuid4().hex

        token = _request_id_var.set(request_id)
        request.request_id = request_id  # type: ignore[attr-defined]

        try:
            response = self._get_response(request)
        finally:
            _request_id_var.reset(token)

        # ست کردن header در response برای client
        response[REQUEST_ID_HEADER] = request_id
        return response


# ============================================================
# Logging filter
# ============================================================


class PrometheusMetricsMiddleware:
    """Middleware that records bounded-cardinality Prometheus HTTP metrics."""

    def __init__(self, get_response: Callable[[HttpRequest], HttpResponse]) -> None:
        self._get_response = get_response

    def __call__(self, request: HttpRequest) -> HttpResponse:
        if not getattr(settings, "PROMETHEUS_METRICS_ENABLED", True):
            return self._get_response(request)
        from apps.core import metrics

        started_at = metrics.monotonic_time()
        if getattr(settings, "DB_QUERY_TELEMETRY_ENABLED", True):
            from apps.core.db_performance import collect_request_db_telemetry

            response, db_snapshot = collect_request_db_telemetry(request=request, get_response=self._get_response)
        else:
            response = self._get_response(request)
            db_snapshot = None
        normalized_path = metrics.normalize_path(request.path)
        duration = metrics.monotonic_time() - started_at
        duration_ms = duration * 1000
        from apps.core.performance import (
            is_slow_request,
            log_slow_request,
            resolve_performance_contract,
        )

        contract = resolve_performance_contract(method=request.method, path=request.path)
        for header_name, header_value in contract.as_headers(duration_ms=duration_ms).items():
            response[header_name] = header_value
        metrics.HTTP_REQUESTS_TOTAL.labels(
            method=request.method,
            path=normalized_path,
            status=str(response.status_code),
        ).inc()
        metrics.HTTP_REQUEST_DURATION_SECONDS.labels(
            method=request.method,
            path=normalized_path,
        ).observe(duration)
        if db_snapshot is not None:
            from apps.core.db_performance import log_db_telemetry_warning, should_log_db_telemetry

            for header_name, header_value in db_snapshot.as_headers().items():
                response[header_name] = header_value
            metrics.HTTP_DB_QUERY_COUNT.labels(method=request.method, path=normalized_path).observe(db_snapshot.query_count)
            metrics.HTTP_DB_QUERY_TIME_SECONDS.labels(method=request.method, path=normalized_path).observe(db_snapshot.total_query_time_ms / 1000)
            if db_snapshot.slow_query_count:
                metrics.HTTP_DB_SLOW_QUERIES_TOTAL.labels(method=request.method, path=normalized_path).inc(db_snapshot.slow_query_count)
            if should_log_db_telemetry(snapshot=db_snapshot):
                log_db_telemetry_warning(path=normalized_path, method=request.method, snapshot=db_snapshot)
        if is_slow_request(duration_ms=duration_ms, contract=contract):
            metrics.HTTP_SLOW_REQUESTS_TOTAL.labels(method=request.method, path=normalized_path).inc()
            log_slow_request(contract=contract, duration_ms=duration_ms, status_code=response.status_code)
        return response


class RequestIDLogFilter(logging.Filter):
    """
    Logging filter برای تزریق request_id به هر log record.

    این filter باعث می‌شود formatter بتواند `%(request_id)s` را در فرمت خود
    استفاده کند. اگر request_id موجود نباشد (مثلاً اجرای CLI یا task)، مقدار
    پیش‌فرض "-" استفاده می‌شود تا فرمت log همیشه consistent بماند.
    """

    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = get_current_request_id()
        return True

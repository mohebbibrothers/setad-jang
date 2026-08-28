"""پوشش تست یافته‌های اولویت پایین (P3) و باگ‌های کشف‌شده در فاز چهارم.

این ماژول قراردادهایی را قفل می‌کند که تا پیش از این فاز یا اصلاً تست
نداشتند (`apps/core/tasks.py` با ۳۰٪ و `apps/core/frontend_revalidation.py`
با ۱۵٪ پوشش) یا رفتار اشتباهی را به‌عنوان درست تثبیت کرده بودند.
"""

from __future__ import annotations

import re
from datetime import timedelta
from itertools import pairwise
from pathlib import Path

import pytest
import requests
from django.utils import timezone

from apps.core import frontend_revalidation as fr, tasks as core_tasks

ROOT = Path(__file__).resolve().parent.parent


# ============================================================
# ۶.۱ — حذف کلاس‌های صفحه‌بندی بلااستفاده
# ============================================================


class TestPaginationSurface:
    """صفحه‌بندی باید فقط چیزی را صادر کند که واقعاً استفاده می‌شود."""

    def test_unused_pagination_classes_are_gone(self) -> None:
        from apps.core import pagination

        assert not hasattr(pagination, "SmallPagination")
        assert not hasattr(pagination, "LargePagination")

    def test_standard_pagination_still_wraps_envelope(self) -> None:
        from apps.core.pagination import StandardPagination

        assert StandardPagination.page_size == 20
        assert StandardPagination.max_page_size == 100
        assert hasattr(StandardPagination, "get_paginated_response")


class TestDeadModules:
    """فایل «نقطهٔ توسعه»ی خالی نباید در مخزن بماند."""

    def test_public_reports_permissions_module_removed(self) -> None:
        assert not (ROOT / "apps" / "public_reports" / "permissions.py").exists()

    def test_public_reports_views_still_import(self) -> None:
        import apps.public_reports.views as views

        assert views is not None


# ============================================================
# ۶.۴ — honeypot نباید مقدار falsy را bot بداند
# ============================================================


class TestHoneypotFalsePositives:
    """`website: 0` یک کلاینت ناقص است، نه یک bot."""

    @pytest.mark.parametrize("value", [0, False, "", "   ", [], {}, None])
    def test_falsy_values_do_not_trigger(self, value: object) -> None:
        from apps.authentication.anti_abuse import (
            HONEYPOT_FIELD_NAME,
            is_honeypot_triggered,
        )

        assert is_honeypot_triggered({HONEYPOT_FIELD_NAME: value}) is False

    @pytest.mark.parametrize("value", ["spam", 1, True, ["x"], {"a": 1}])
    def test_meaningful_values_still_trigger(self, value: object) -> None:
        from apps.authentication.anti_abuse import (
            HONEYPOT_FIELD_NAME,
            is_honeypot_triggered,
        )

        assert is_honeypot_triggered({HONEYPOT_FIELD_NAME: value}) is True

    def test_absent_field_does_not_trigger(self) -> None:
        from apps.authentication.anti_abuse import is_honeypot_triggered

        assert is_honeypot_triggered({"phone": "0912"}) is False


# ============================================================
# ۶.۶ — قفل وابستگی‌ها واقعاً مصرف می‌شود
# ============================================================


class TestDependencyLocks:
    """قفلی که هیچ‌کس نمی‌خواندش، امنیت کاذب است."""

    def test_both_lock_files_exist(self) -> None:
        assert (ROOT / "requirements-lock.txt").is_file()
        assert (ROOT / "requirements-dev-lock.txt").is_file()

    def test_dockerfile_installs_from_the_lock(self) -> None:
        dockerfile = (ROOT / "Dockerfile").read_text()

        assert "-r requirements-lock.txt" in dockerfile
        assert "pip wheel --wheel-dir=/wheels -r requirements.txt" not in dockerfile

    def test_production_lock_excludes_development_tooling(self) -> None:
        """pytest/ruff/bandit هرگز نباید داخل image نهایی بروند."""
        lock = (ROOT / "requirements-lock.txt").read_text().lower()
        names = {
            line.split("==")[0].strip()
            for line in lock.splitlines()
            if "==" in line and not line.startswith("#")
        }

        assert not names & {"pytest", "ruff", "bandit", "pip-audit", "detect-secrets"}

    def test_production_lock_pins_every_requirement(self) -> None:
        lock = (ROOT / "requirements-lock.txt").read_text()
        pins = [line for line in lock.splitlines() if line and not line.startswith("#")]

        assert pins, "قفل production خالی است"
        assert all("==" in pin for pin in pins), "همهٔ وابستگی‌ها باید پین شده باشند"

    def test_ci_enforces_lock_drift(self) -> None:
        ci = (ROOT / ".github" / "workflows" / "ci.yml").read_text()

        assert "make lock-check" in ci


# ============================================================
# ۶.۷ — connection pooling درگاه پرداخت
# ============================================================


class TestZarinpalTransport:
    """هر پرداخت نباید یک TLS handshake تازه بپردازد."""

    def teardown_method(self) -> None:
        from apps.madadkar.payment_providers import zarinpal

        zarinpal.reset_session()

    def test_session_is_reused_across_calls(self) -> None:
        from apps.madadkar.payment_providers import zarinpal

        zarinpal.reset_session()
        first = zarinpal._get_session()
        second = zarinpal._get_session()

        assert first is second
        assert isinstance(first, requests.Session)

    def test_https_adapter_has_a_connection_pool(self) -> None:
        from apps.madadkar.payment_providers import zarinpal

        zarinpal.reset_session()
        adapter = zarinpal._get_session().get_adapter("https://api.zarinpal.com/")

        assert adapter._pool_maxsize >= 4

    def test_transport_never_retries_non_idempotent_payment_posts(self) -> None:
        """retry شفاف روی POST پرداخت می‌تواند authority تکراری بسازد."""
        from apps.madadkar.payment_providers import zarinpal

        zarinpal.reset_session()
        adapter = zarinpal._get_session().get_adapter("https://api.zarinpal.com/")

        assert adapter.max_retries.total == 0

    def test_module_no_longer_uses_the_global_requests_post(self) -> None:
        source = (ROOT / "apps" / "madadkar" / "payment_providers" / "zarinpal.py").read_text()

        assert "requests.post(" not in source
        assert "_get_session().post(" in source


# ============================================================
# باگ کشف‌شده در فاز ۴ — نبود backoff در outbox
# ============================================================


class TestOutboxRetryBackoff:
    """رویداد شکست‌خورده نباید بلافاصله دوباره سررسید شود.

    sweeper هر دقیقه اجرا می‌شود. با `next_attempt_at = now()` یک رویداد
    دائماً خراب کل بودجهٔ ۱۰ تلاشش را در ۱۰ دقیقه می‌سوزاند.
    """

    def test_delay_grows_exponentially(self) -> None:
        delays = [core_tasks.outbox_retry_delay_seconds(n) for n in range(1, 7)]

        for earlier, later in pairwise(delays):
            assert later > earlier

    def test_first_delay_is_never_zero(self) -> None:
        assert core_tasks.outbox_retry_delay_seconds(1) > 0

    def test_delay_is_capped(self, settings) -> None:
        settings.CACHE_INVALIDATION_RETRY_MAX_SECONDS = 300
        settings.CACHE_INVALIDATION_RETRY_BASE_SECONDS = 10

        # سقف + حداکثر ۱۰٪ jitter
        assert core_tasks.outbox_retry_delay_seconds(50) <= 300 * 1.1

    def test_huge_attempt_count_does_not_overflow(self, settings) -> None:
        settings.CACHE_INVALIDATION_RETRY_MAX_SECONDS = 3600

        assert core_tasks.outbox_retry_delay_seconds(10_000) <= 3600 * 1.1

    def test_backoff_window_outlives_the_one_minute_sweeper(self, settings) -> None:
        """مجموع تأخیرها باید خیلی بیشتر از ۱۰ دقیقه باشد."""
        settings.CACHE_INVALIDATION_RETRY_BASE_SECONDS = 10
        settings.CACHE_INVALIDATION_RETRY_MAX_SECONDS = 3600

        total = sum(core_tasks.outbox_retry_delay_seconds(n) for n in range(1, 10))

        assert total > 3600, "پنجرهٔ backoff باید دست‌کم یک ساعت باشد"

    @pytest.mark.django_db
    def test_failed_event_is_scheduled_into_the_future(self, monkeypatch, settings) -> None:
        from apps.core.models import CacheInvalidationEvent

        settings.CACHE_INVALIDATION_RETRY_BASE_SECONDS = 60

        event = CacheInvalidationEvent.objects.create(domain="public", tags=["t"], paths=["/p"])

        def _boom(**kwargs):
            raise requests.RequestException("frontend down")

        monkeypatch.setattr(core_tasks.revalidate_frontend_task, "run", _boom)

        before = timezone.now()
        with pytest.raises(requests.RequestException):
            core_tasks.process_cache_invalidation_event_task.run(event_id=event.pk)

        event.refresh_from_db()

        assert event.status == CacheInvalidationEvent.STATUS_FAILED
        assert event.attempts == 1
        assert event.next_attempt_at is not None
        assert event.next_attempt_at > before + timedelta(seconds=30)

    @pytest.mark.django_db
    def test_backed_off_event_is_not_picked_up_by_the_sweeper(self, settings) -> None:
        from apps.core.models import CacheInvalidationEvent

        CacheInvalidationEvent.objects.create(
            domain="public",
            tags=["t"],
            status=CacheInvalidationEvent.STATUS_FAILED,
            attempts=3,
            next_attempt_at=timezone.now() + timedelta(minutes=30),
        )

        queued = core_tasks.process_pending_cache_invalidation_events_task.run()

        assert queued == 0

    @pytest.mark.django_db
    def test_event_becomes_due_once_backoff_elapses(self, monkeypatch) -> None:
        from apps.core.models import CacheInvalidationEvent

        CacheInvalidationEvent.objects.create(
            domain="public",
            tags=["t"],
            status=CacheInvalidationEvent.STATUS_FAILED,
            attempts=3,
            next_attempt_at=timezone.now() - timedelta(seconds=1),
        )

        sent: list[int] = []
        monkeypatch.setattr(
            core_tasks.process_cache_invalidation_event_task,
            "delay",
            lambda **kw: sent.append(kw["event_id"]),
        )

        assert core_tasks.process_pending_cache_invalidation_events_task.run() == 1
        assert len(sent) == 1


# ============================================================
# ۶.۸ — پوشش تست ابطال کش فرانت‌اند
# ============================================================


class TestNormalizeTags:
    def test_strips_and_deduplicates(self) -> None:
        assert fr.normalize_tags([" a ", "a", "b", ""]) == ["a", "b"]

    def test_handles_none(self) -> None:
        assert fr.normalize_tags(None) == []

    def test_caps_at_fifty(self) -> None:
        assert len(fr.normalize_tags([f"tag-{i}" for i in range(120)])) == 50

    def test_preserves_order(self) -> None:
        assert fr.normalize_tags(["z", "a", "m"]) == ["z", "a", "m"]

    def test_coerces_non_strings(self) -> None:
        assert fr.normalize_tags([1, 2]) == ["1", "2"]


class TestNormalizePaths:
    def test_rejects_relative_paths(self) -> None:
        assert fr.normalize_paths(["no-slash", "/ok"]) == ["/ok"]

    def test_rejects_protocol_relative_paths(self) -> None:
        """`//evil.com` در مرورگر یعنی یک host دیگر — نباید عبور کند."""
        assert fr.normalize_paths(["//evil.com"]) == []

    def test_deduplicates(self) -> None:
        assert fr.normalize_paths(["/a", "/a", "/b"]) == ["/a", "/b"]

    def test_handles_none(self) -> None:
        assert fr.normalize_paths(None) == []

    def test_caps_at_fifty(self) -> None:
        assert len(fr.normalize_paths([f"/p/{i}" for i in range(120)])) == 50


class TestRevalidateFrontendDispatch:
    def test_empty_payload_is_a_noop(self, settings, monkeypatch) -> None:
        settings.FRONTEND_REVALIDATION_ENABLED = True
        settings.FRONTEND_REVALIDATION_URL = "https://front.example/api/revalidate"

        called: list[dict] = []
        monkeypatch.setattr(
            core_tasks.revalidate_frontend_task, "delay", lambda **kw: called.append(kw)
        )

        fr.revalidate_frontend(tags=[], paths=[])

        assert called == []

    def test_disabled_flag_short_circuits(self, settings, monkeypatch) -> None:
        settings.FRONTEND_REVALIDATION_ENABLED = False

        called: list[dict] = []
        monkeypatch.setattr(
            core_tasks.revalidate_frontend_task, "delay", lambda **kw: called.append(kw)
        )

        fr.revalidate_frontend(tags=["a"])

        assert called == []

    def test_missing_url_short_circuits(self, settings, monkeypatch) -> None:
        settings.FRONTEND_REVALIDATION_ENABLED = True
        settings.FRONTEND_REVALIDATION_URL = ""

        called: list[dict] = []
        monkeypatch.setattr(
            core_tasks.revalidate_frontend_task, "delay", lambda **kw: called.append(kw)
        )

        fr.revalidate_frontend(tags=["a"])

        assert called == []

    def test_queues_normalized_payload(self, settings, monkeypatch) -> None:
        settings.FRONTEND_REVALIDATION_ENABLED = True
        settings.FRONTEND_REVALIDATION_URL = "https://front.example/api/revalidate"

        called: list[dict] = []
        monkeypatch.setattr(
            core_tasks.revalidate_frontend_task, "delay", lambda **kw: called.append(kw)
        )

        fr.revalidate_frontend(tags=[" a ", "a"], paths=["/x", "bad"])

        assert called == [{"tags": ["a"], "paths": ["/x"]}]

    def test_broker_outage_never_breaks_the_caller(self, settings, monkeypatch) -> None:
        """ابطال کش best-effort است؛ نباید یک mutation تجاری را بشکند."""
        settings.FRONTEND_REVALIDATION_ENABLED = True
        settings.FRONTEND_REVALIDATION_URL = "https://front.example/api/revalidate"

        def _broker_down(**kwargs):
            raise OSError("broker unreachable")

        monkeypatch.setattr(core_tasks.revalidate_frontend_task, "delay", _broker_down)

        fr.revalidate_frontend(tags=["a"])  # نباید exception بدهد


class _FakeResponse:
    def __init__(self, status_code: int, text: str = "{}") -> None:
        self.status_code = status_code
        self.text = text

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise requests.HTTPError(f"status {self.status_code}")


class TestRevalidateFrontendTask:
    """مسیرهای خروجی task که پیش‌تر اصلاً اجرا نمی‌شدند."""

    @pytest.fixture(autouse=True)
    def _configure(self, settings):
        settings.FRONTEND_REVALIDATION_ENABLED = True
        settings.FRONTEND_REVALIDATION_URL = "https://front.example/api/revalidate"
        settings.FRONTEND_REVALIDATION_SECRET = "s3cret"
        settings.FRONTEND_REVALIDATION_TIMEOUT = 3

    def test_disabled_returns_early(self, settings, monkeypatch) -> None:
        settings.FRONTEND_REVALIDATION_ENABLED = False
        monkeypatch.setattr(
            core_tasks.requests, "post", lambda *a, **k: pytest.fail("نباید صدا زده شود")
        )

        core_tasks.revalidate_frontend_task.run(tags=["a"])

    def test_missing_secret_returns_early(self, settings, monkeypatch) -> None:
        settings.FRONTEND_REVALIDATION_SECRET = ""
        monkeypatch.setattr(
            core_tasks.requests, "post", lambda *a, **k: pytest.fail("نباید صدا زده شود")
        )

        core_tasks.revalidate_frontend_task.run(tags=["a"])

    def test_empty_payload_returns_early(self, monkeypatch) -> None:
        monkeypatch.setattr(
            core_tasks.requests, "post", lambda *a, **k: pytest.fail("نباید صدا زده شود")
        )

        core_tasks.revalidate_frontend_task.run(tags=[], paths=[])

    def test_success_sends_bearer_token_and_payload(self, monkeypatch) -> None:
        captured: dict = {}

        def _post(url, **kwargs):
            captured["url"] = url
            captured.update(kwargs)
            return _FakeResponse(200)

        monkeypatch.setattr(core_tasks.requests, "post", _post)

        core_tasks.revalidate_frontend_task.run(tags=["a"], paths=["/x"])

        assert captured["url"] == "https://front.example/api/revalidate"
        assert captured["json"] == {"tags": ["a"], "paths": ["/x"]}
        assert captured["headers"]["Authorization"] == "Bearer s3cret"
        assert captured["timeout"] == 3

    def test_client_rejection_is_swallowed(self, monkeypatch) -> None:
        """۴xx یعنی «نپذیرفتم»؛ retry کردنش فایده‌ای ندارد."""
        monkeypatch.setattr(core_tasks.requests, "post", lambda *a, **k: _FakeResponse(403, "nope"))

        core_tasks.revalidate_frontend_task.run(tags=["a"])

    def test_server_error_raises_for_retry(self, monkeypatch) -> None:
        """۵xx یعنی «الان نمی‌توانم»؛ باید retry شود."""
        monkeypatch.setattr(core_tasks.requests, "post", lambda *a, **k: _FakeResponse(503, "down"))

        with pytest.raises(requests.HTTPError):
            core_tasks.revalidate_frontend_task.run(tags=["a"])

    def test_network_error_propagates(self, monkeypatch) -> None:
        def _post(*a, **k):
            raise requests.ConnectionError("dns")

        monkeypatch.setattr(core_tasks.requests, "post", _post)

        with pytest.raises(requests.ConnectionError):
            core_tasks.revalidate_frontend_task.run(tags=["a"])


class TestOutboxTerminalStates:
    """گاردهای مسیر outbox که پوشش نداشتند."""

    @pytest.mark.django_db
    def test_missing_event_is_tolerated(self) -> None:
        core_tasks.process_cache_invalidation_event_task.run(event_id=9_999_999)

    @pytest.mark.django_db
    def test_already_succeeded_event_is_skipped(self, monkeypatch) -> None:
        from apps.core.models import CacheInvalidationEvent

        event = CacheInvalidationEvent.objects.create(
            domain="public", tags=["t"], status=CacheInvalidationEvent.STATUS_SUCCEEDED
        )
        monkeypatch.setattr(
            core_tasks.revalidate_frontend_task,
            "run",
            lambda **kw: pytest.fail("نباید اجرا شود"),
        )

        core_tasks.process_cache_invalidation_event_task.run(event_id=event.pk)

    @pytest.mark.django_db
    def test_exhausted_event_moves_to_dead_letter(self, settings) -> None:
        from apps.core.models import CacheInvalidationEvent

        settings.CACHE_INVALIDATION_MAX_ATTEMPTS = 3
        event = CacheInvalidationEvent.objects.create(
            domain="public",
            tags=["t"],
            status=CacheInvalidationEvent.STATUS_FAILED,
            attempts=3,
        )

        core_tasks.process_cache_invalidation_event_task.run(event_id=event.pk)
        event.refresh_from_db()

        assert event.status == CacheInvalidationEvent.STATUS_DEAD
        assert "Maximum attempts" in event.last_error

    @pytest.mark.django_db
    def test_successful_event_is_marked_processed(self, monkeypatch) -> None:
        from apps.core.models import CacheInvalidationEvent

        event = CacheInvalidationEvent.objects.create(domain="public", tags=["t"])
        monkeypatch.setattr(core_tasks.revalidate_frontend_task, "run", lambda **kw: None)

        core_tasks.process_cache_invalidation_event_task.run(event_id=event.pk)
        event.refresh_from_db()

        assert event.status == CacheInvalidationEvent.STATUS_SUCCEEDED
        assert event.processed_at is not None
        assert event.last_error == ""

    @pytest.mark.django_db
    def test_last_attempt_failure_dead_letters_immediately(self, monkeypatch, settings) -> None:
        from apps.core.models import CacheInvalidationEvent

        settings.CACHE_INVALIDATION_MAX_ATTEMPTS = 2
        event = CacheInvalidationEvent.objects.create(domain="public", tags=["t"], attempts=1)

        def _boom(**kwargs):
            raise requests.RequestException("still down")

        monkeypatch.setattr(core_tasks.revalidate_frontend_task, "run", _boom)

        with pytest.raises(requests.RequestException):
            core_tasks.process_cache_invalidation_event_task.run(event_id=event.pk)

        event.refresh_from_db()

        assert event.status == CacheInvalidationEvent.STATUS_DEAD


# ============================================================
# ۶.۹ — اثبات استفادهٔ واقعی از ایندکس‌ها با EXPLAIN
# ============================================================


@pytest.mark.django_db
class TestHotQueriesUseIndexes:
    """۵۹ `db_index` و ۱۵۸ `models.Index` تعریف شده — ولی هیچ‌کدام اثبات نشده بود.

    ایندکس تعریف‌شده تضمین نمی‌کند planner از آن استفاده کند: ترتیب ستون‌ها،
    تابع روی ستون، یا نوع ناسازگار می‌تواند ایندکس را دور بزند و کسی متوجه
    نشود تا وقتی جدول بزرگ شود. این تست‌ها plan واقعی را می‌خوانند.
    """

    @staticmethod
    def _plan(queryset) -> str:
        return queryset.explain()

    @staticmethod
    def _assert_no_full_scan(plan: str, table: str) -> None:
        """SQLite: «SCAN <table>» یعنی پیمایش کامل؛ «SEARCH» یعنی ایندکس."""
        full_scan = re.search(rf"\bSCAN\b\s+(?:TABLE\s+)?{re.escape(table)}\b", plan)
        assert not full_scan, f"پرس‌وجو روی {table} full scan می‌کند:\n{plan}"

    def test_outbox_due_query_uses_the_composite_index(self) -> None:
        from django.db.models import Q

        from apps.core.models import CacheInvalidationEvent

        now = timezone.now()
        plan = self._plan(
            CacheInvalidationEvent.all_objects.filter(
                Q(status=CacheInvalidationEvent.STATUS_PENDING)
                | Q(status=CacheInvalidationEvent.STATUS_FAILED, next_attempt_at__lte=now),
                attempts__lt=10,
            ).order_by("created_at")
        )

        # هر دو شاخهٔ OR باید ایندکس بخورند و نام ایندکس ترکیبی دیده شود.
        assert "core_cache_event_due_idx" in plan, plan
        self._assert_no_full_scan(plan, "core_cacheinvalidationevent")

    def test_outbox_status_lookup_is_index_backed(self) -> None:
        from apps.core.models import CacheInvalidationEvent

        plan = self._plan(
            CacheInvalidationEvent.all_objects.filter(status=CacheInvalidationEvent.STATUS_PENDING)
        )

        self._assert_no_full_scan(plan, "core_cacheinvalidationevent")

    def test_outbox_domain_history_is_index_backed(self) -> None:
        from apps.core.models import CacheInvalidationEvent

        plan = self._plan(
            CacheInvalidationEvent.all_objects.filter(domain="public").order_by("-created_at")
        )

        self._assert_no_full_scan(plan, "core_cacheinvalidationevent")

    def test_explain_is_available_on_the_test_backend(self) -> None:
        """اگر این بشکند یعنی تست‌های بالا بی‌صدا بی‌اثر شده‌اند."""
        from apps.core.models import CacheInvalidationEvent

        plan = self._plan(CacheInvalidationEvent.all_objects.filter(domain="x"))

        assert plan.strip(), "خروجی EXPLAIN خالی است"

    def test_full_scan_detector_actually_detects_a_full_scan(self) -> None:
        """کنترل منفی.

        بدون این تست، `_assert_no_full_scan` می‌توانست به‌خاطر تغییر قالب
        خروجی EXPLAIN بی‌صدا به یک no-op تبدیل شود و همهٔ تست‌های ایندکس
        بالا سبز بمانند در حالی که هیچ‌چیز را بررسی نمی‌کنند.

        `last_error` عمداً ایندکس ندارد، پس *باید* full scan شود.
        """
        from apps.core.models import CacheInvalidationEvent

        plan = self._plan(CacheInvalidationEvent.all_objects.filter(last_error="x"))

        with pytest.raises(AssertionError):
            self._assert_no_full_scan(plan, "core_cacheinvalidationevent")

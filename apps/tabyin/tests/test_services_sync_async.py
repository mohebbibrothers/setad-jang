"""
Tests — apps.tabyin.services / apps.tabyin.tasks (async sync orchestration)

این تست‌ها رفتار سه بخش را verify می‌کنند:

1. dispatch_sync_task:
   - بسته به mode، task درست enqueue می‌شود
   - شناسه task برمی‌گرداند
   - backward compatibility بدون metadata حفظ می‌شود

2. metadata propagation:
   - metadata مربوط به trigger انسانی از service به task می‌رسد
   - task outcome audit آن را دریافت می‌کند

3. task outcome audit:
   - STARTED و SUCCEEDED ثبت می‌شوند
   - در failureهای transient فقط STARTED ثبت می‌شود
   - در failure نهایی FAILED ثبت می‌شود
   - اگر خود audit log write fail شود، business task نباید بشکند

اصول طراحی:
- mocking در مرز business logic انجام می‌شود.
- external I/O واقعی رخ نمی‌دهد.
- audit write به‌جای DB با monkeypatch روی log_action capture می‌شود.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pytest

from apps.audit_logs import actions as audit_actions
from apps.tabyin import services, tasks as tabyin_tasks

pytestmark = [pytest.mark.celery]


# ============================================================
# Fake stats — ساختار سازگار با SyncStats واقعی
# ============================================================


@dataclass
class _FakeSyncStats:
    """
    یک نسخه‌ی dataclass-shaped سازگار با SyncStats واقعی.

    دلیل استفاده از dataclass:
    لایه‌ی tasks خروجی run_sync را با asdict() به dict تبدیل می‌کند،
    پس dataclass رفتار واقعی production را شبیه‌سازی می‌کند.
    """

    pages_fetched: int = 1
    items_processed: int = 30
    created: int = 0
    updated: int = 0
    unchanged: int = 30
    soft_deleted: int = 0
    errors: int = 0
    skipped: int = 0
    duration_seconds: float = 1.23
    started_at: str = "2026-01-01T00:00:00+00:00"


# ============================================================
# Fake AsyncResult — برای تست contract get_sync_task_status
# ============================================================


class _FakeAsyncResult:
    """
    شبیه‌ساز سبک AsyncResult با همان interface مورد استفاده در service.

    دلیل استفاده:
    در Celery eager mode، نتیجه‌ی task در backend persist نمی‌شود،
    پس AsyncResult واقعی همیشه PENDING برمی‌گرداند. این کلاس به ما اجازه
    می‌دهد contract سرویس را به‌صورت deterministic verify کنیم.
    """

    def __init__(
        self,
        task_id: str,
        *,
        state: str,
        result: Any,
        successful: bool,
    ) -> None:
        self.id = task_id
        self.state = state
        self._result = result
        self._successful = successful

    @property
    def result(self) -> Any:
        return self._result

    def ready(self) -> bool:
        return self.state in {"SUCCESS", "FAILURE", "REVOKED"}

    def successful(self) -> bool:
        return self._successful


# ============================================================
# dispatch_sync_task
# ============================================================


class TestDispatchSyncTask:
    """رفتار dispatch_sync_task با mock شدن run_sync در service/task layer."""

    def test_incremental_mode_invokes_incremental_task(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        called_modes: list[str] = []

        def fake_run_sync(*, mode: str) -> _FakeSyncStats:
            called_modes.append(mode)
            return _FakeSyncStats()

        monkeypatch.setattr("apps.tabyin.services.run_sync", fake_run_sync)
        monkeypatch.setattr("apps.tabyin.tasks.run_sync", fake_run_sync)
        monkeypatch.setattr("apps.tabyin.tasks.log_action", lambda **kwargs: None)

        task_id = services.dispatch_sync_task(mode="incremental")

        assert isinstance(task_id, str)
        assert task_id != ""
        assert called_modes == ["incremental"]

    def test_full_mode_invokes_full_task(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        called_modes: list[str] = []

        def fake_run_sync(*, mode: str) -> _FakeSyncStats:
            called_modes.append(mode)
            return _FakeSyncStats()

        monkeypatch.setattr("apps.tabyin.services.run_sync", fake_run_sync)
        monkeypatch.setattr("apps.tabyin.tasks.run_sync", fake_run_sync)
        monkeypatch.setattr("apps.tabyin.tasks.log_action", lambda **kwargs: None)

        task_id = services.dispatch_sync_task(mode="full")

        assert isinstance(task_id, str)
        assert task_id != ""
        assert called_modes == ["full"]

    def test_dispatch_propagates_metadata_to_task_outcome_audit(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """
        metadata مربوط به trigger باید از service به task برسد
        و در audit outcome task قابل مشاهده باشد.
        """
        called_modes: list[str] = []
        audit_calls: list[dict[str, Any]] = []

        def fake_run_sync(*, mode: str) -> _FakeSyncStats:
            called_modes.append(mode)
            return _FakeSyncStats()

        def fake_log_action(**kwargs: Any) -> None:
            audit_calls.append(kwargs)

        monkeypatch.setattr("apps.tabyin.services.run_sync", fake_run_sync)
        monkeypatch.setattr("apps.tabyin.tasks.run_sync", fake_run_sync)
        monkeypatch.setattr("apps.tabyin.tasks.log_action", fake_log_action)

        task_id = services.dispatch_sync_task(
            mode="incremental",
            triggered_by_user_id=77,
            request_id="req-sync-123",
            dispatch_ip="10.10.10.10",
        )

        assert isinstance(task_id, str)
        assert called_modes == ["incremental"]
        assert len(audit_calls) == 2

        assert audit_calls[0]["action"] == audit_actions.TABYIN_SYNC_STARTED
        assert audit_calls[1]["action"] == audit_actions.TABYIN_SYNC_SUCCEEDED

        assert all(call["user_id"] == 77 for call in audit_calls)
        assert all(call["request_id"] == "req-sync-123" for call in audit_calls)
        assert all(call["ip_address"] == "10.10.10.10" for call in audit_calls)
        assert audit_calls[0]["resource_id"] == task_id
        assert audit_calls[1]["resource_id"] == task_id


# ============================================================
# get_sync_task_status — success path
# ============================================================


class TestGetSyncTaskStatusSuccess:
    """contract سرویس برای task موفق."""

    def test_returns_success_state_with_serialized_result(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        fake_payload = {
            "pages_fetched": 1,
            "items_processed": 30,
            "created": 0,
            "updated": 0,
            "unchanged": 30,
            "soft_deleted": 0,
            "errors": 0,
            "skipped": 0,
            "duration_seconds": 1.23,
            "started_at": "2026-01-01T00:00:00+00:00",
        }

        fake_async_result = _FakeAsyncResult(
            task_id="fake-task-id-success",
            state="SUCCESS",
            result=fake_payload,
            successful=True,
        )

        monkeypatch.setattr(
            "apps.tabyin.services.AsyncResult",
            lambda task_id: fake_async_result,
        )

        status_payload = services.get_sync_task_status(
            task_id="fake-task-id-success",
        )

        assert status_payload["task_id"] == "fake-task-id-success"
        assert status_payload["state"] == "SUCCESS"
        assert status_payload["ready"] is True
        assert status_payload["successful"] is True
        assert status_payload["error"] is None
        assert status_payload["result"] == fake_payload


# ============================================================
# get_sync_task_status — failure path
# ============================================================


class TestGetSyncTaskStatusFailure:
    """contract سرویس برای task شکست‌خورده."""

    def test_returns_failure_state_with_error_message(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        fake_async_result = _FakeAsyncResult(
            task_id="fake-task-id-failure",
            state="FAILURE",
            result=RuntimeError("simulated sync failure"),
            successful=False,
        )

        monkeypatch.setattr(
            "apps.tabyin.services.AsyncResult",
            lambda task_id: fake_async_result,
        )

        status_payload = services.get_sync_task_status(
            task_id="fake-task-id-failure",
        )

        assert status_payload["task_id"] == "fake-task-id-failure"
        assert status_payload["state"] == "FAILURE"
        assert status_payload["ready"] is True
        assert status_payload["successful"] is False
        assert status_payload["result"] is None
        assert status_payload["error"] is not None
        assert "RuntimeError" in status_payload["error"]
        assert "simulated sync failure" in status_payload["error"]


# ============================================================
# task outcome audit
# ============================================================


class TestTaskOutcomeAudit:
    """تست‌های outcome audit در worker/task layer."""

    def test_run_sync_task_logs_started_and_succeeded_with_metadata(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        audit_calls: list[dict[str, Any]] = []

        def fake_run_sync(*, mode: str) -> _FakeSyncStats:
            assert mode == "incremental"
            return _FakeSyncStats()

        def fake_log_action(**kwargs: Any) -> None:
            audit_calls.append(kwargs)

        monkeypatch.setattr("apps.tabyin.tasks.run_sync", fake_run_sync)
        monkeypatch.setattr("apps.tabyin.tasks.log_action", fake_log_action)

        result = tabyin_tasks._run_sync_task(
            mode="incremental",
            task_id="task-001",
            retries=0,
            max_retries=3,
            triggered_by_user_id=91,
            request_id="req-001",
            dispatch_ip="127.0.0.1",
        )

        assert result["unchanged"] == 30
        assert [call["action"] for call in audit_calls] == [
            audit_actions.TABYIN_SYNC_STARTED,
            audit_actions.TABYIN_SYNC_SUCCEEDED,
        ]
        assert all(call["user_id"] == 91 for call in audit_calls)
        assert all(call["request_id"] == "req-001" for call in audit_calls)
        assert all(call["ip_address"] == "127.0.0.1" for call in audit_calls)
        assert audit_calls[1]["extra_data"]["stats"]["unchanged"] == 30

    def test_run_sync_task_logs_only_started_on_transient_failure(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """
        اگر failure هنوز final نباشد، فقط STARTED ثبت می‌شود
        و FAILED ثبت نمی‌شود.
        """
        audit_calls: list[dict[str, Any]] = []

        def fake_run_sync(*, mode: str) -> _FakeSyncStats:
            raise RuntimeError("temporary upstream failure")

        def fake_log_action(**kwargs: Any) -> None:
            audit_calls.append(kwargs)

        monkeypatch.setattr("apps.tabyin.tasks.run_sync", fake_run_sync)
        monkeypatch.setattr("apps.tabyin.tasks.log_action", fake_log_action)

        with pytest.raises(RuntimeError):
            tabyin_tasks._run_sync_task(
                mode="incremental",
                task_id="task-transient",
                retries=0,
                max_retries=3,
                triggered_by_user_id=51,
                request_id="req-transient",
                dispatch_ip="10.0.0.2",
            )

        assert [call["action"] for call in audit_calls] == [
            audit_actions.TABYIN_SYNC_STARTED,
        ]

    def test_run_sync_task_logs_failed_on_final_failure(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """در failure نهایی باید FAILED ثبت شود."""
        audit_calls: list[dict[str, Any]] = []

        def fake_run_sync(*, mode: str) -> _FakeSyncStats:
            raise RuntimeError("final sync failure")

        def fake_log_action(**kwargs: Any) -> None:
            audit_calls.append(kwargs)

        monkeypatch.setattr("apps.tabyin.tasks.run_sync", fake_run_sync)
        monkeypatch.setattr("apps.tabyin.tasks.log_action", fake_log_action)

        with pytest.raises(RuntimeError):
            tabyin_tasks._run_sync_task(
                mode="full",
                task_id="task-final-failure",
                retries=2,
                max_retries=2,
                triggered_by_user_id=52,
                request_id="req-final",
                dispatch_ip="10.0.0.3",
            )

        assert [call["action"] for call in audit_calls] == [
            audit_actions.TABYIN_SYNC_STARTED,
            audit_actions.TABYIN_SYNC_FAILED,
        ]
        assert audit_calls[1]["extra_data"]["error_type"] == "RuntimeError"
        assert "final sync failure" in audit_calls[1]["extra_data"]["error_message"]

    def test_audit_write_failure_does_not_break_sync_task(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """
        اگر خود audit write fail شود، business task نباید fail شود.
        """

        def fake_run_sync(*, mode: str) -> _FakeSyncStats:
            return _FakeSyncStats()

        def fake_log_action(**kwargs: Any) -> None:
            raise RuntimeError("audit storage temporarily unavailable")

        monkeypatch.setattr("apps.tabyin.tasks.run_sync", fake_run_sync)
        monkeypatch.setattr("apps.tabyin.tasks.log_action", fake_log_action)

        result = tabyin_tasks._run_sync_task(
            mode="incremental",
            task_id="task-audit-failure",
            retries=0,
            max_retries=3,
            triggered_by_user_id=53,
            request_id="req-audit-failure",
            dispatch_ip="10.0.0.4",
        )

        assert result["unchanged"] == 30

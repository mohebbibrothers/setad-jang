from __future__ import annotations

import pytest

from apps.core.models import CacheInvalidationEvent
from apps.core.tasks import process_pending_cache_invalidation_events_task

pytestmark = [pytest.mark.django_db]


def test_process_pending_cache_invalidation_events_dispatches_due_events(monkeypatch) -> None:
    first = CacheInvalidationEvent.objects.create(domain="r4j", tags=["r4j"], paths=["/"])
    CacheInvalidationEvent.objects.create(
        domain="tabyin",
        tags=["tabyin"],
        paths=["/tabyin"],
        status=CacheInvalidationEvent.STATUS_SUCCEEDED,
    )
    queued: list[int] = []

    class _FakeTask:
        @staticmethod
        def delay(*, event_id: int) -> None:
            queued.append(event_id)

    monkeypatch.setattr("apps.core.tasks.process_cache_invalidation_event_task", _FakeTask)

    assert process_pending_cache_invalidation_events_task(limit=10) == 1
    assert queued == [first.pk]

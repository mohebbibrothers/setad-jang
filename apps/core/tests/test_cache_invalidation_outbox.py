from __future__ import annotations

import pytest

from apps.core.cache_invalidation import enqueue_cache_invalidation_event, invalidate_public_domain
from apps.core.models import CacheInvalidationEvent

pytestmark = [pytest.mark.django_db]


def test_enqueue_cache_invalidation_event_persists_and_dispatches(monkeypatch) -> None:
    queued: list[int] = []

    class _FakeTask:
        @staticmethod
        def delay(*, event_id: int) -> None:
            queued.append(event_id)

    monkeypatch.setattr("apps.core.tasks.process_cache_invalidation_event_task", _FakeTask)

    enqueue_cache_invalidation_event(domain="r4j", tags=["homepage", "r4j"], paths=["/"])

    event = CacheInvalidationEvent.objects.get(domain="r4j")
    assert event.status == CacheInvalidationEvent.STATUS_PENDING
    assert event.tags == ["homepage", "r4j"]
    assert event.paths == ["/"]
    assert queued == [event.pk]


def test_invalidate_public_domain_validates_known_domains() -> None:
    with pytest.raises(ValueError):
        invalidate_public_domain("unknown-domain")

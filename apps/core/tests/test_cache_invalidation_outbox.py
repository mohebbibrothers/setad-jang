from __future__ import annotations

import pytest

from apps.core.cache_invalidation import invalidate_public_domain
from apps.core.models import CacheInvalidationEvent

pytestmark = [pytest.mark.django_db]


def test_invalidate_public_domain_creates_outbox_event(settings, monkeypatch) -> None:
    settings.CACHE_INVALIDATION_OUTBOX_ENABLED = True
    settings.FRONTEND_REVALIDATION_ENABLED = False

    queued: list[int] = []

    class _FakeTask:
        @staticmethod
        def delay(*, event_id: int) -> None:
            queued.append(event_id)

    monkeypatch.setattr("apps.core.tasks.process_cache_invalidation_event_task", _FakeTask)

    invalidate_public_domain("r4j")

    event = CacheInvalidationEvent.objects.get(domain="r4j")
    assert event.status == CacheInvalidationEvent.STATUS_PENDING
    assert "r4j" in event.tags
    assert "homepage" in event.tags
    assert "/" in event.paths
    assert queued == [event.pk]

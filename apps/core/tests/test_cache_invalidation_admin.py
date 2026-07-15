from __future__ import annotations

from django.contrib import admin

from apps.core.admin import CacheInvalidationEventAdmin
from apps.core.models import CacheInvalidationEvent


def test_cache_invalidation_event_is_registered_in_admin() -> None:
    """Cache invalidation outbox events must be operable from Django admin."""
    registered = admin.site._registry[CacheInvalidationEvent]
    assert isinstance(registered, CacheInvalidationEventAdmin)
    assert "retry_selected_events" in registered.actions
    assert "mark_selected_as_dead" in registered.actions
    assert "mark_selected_as_pending" in registered.actions

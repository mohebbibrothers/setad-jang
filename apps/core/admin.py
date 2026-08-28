"""Django admin for core infrastructure models."""

from __future__ import annotations

from django.contrib import admin, messages
from django.db.models import QuerySet
from django.http import HttpRequest
from django.utils import timezone

from apps.core.models import CacheInvalidationEvent


@admin.register(CacheInvalidationEvent)
class CacheInvalidationEventAdmin(admin.ModelAdmin):
    """Operational admin for durable cache invalidation outbox events."""

    list_display = (
        "id",
        "domain",
        "status",
        "attempts",
        "tags_summary",
        "paths_summary",
        "next_attempt_at",
        "processed_at",
        "created_at",
    )
    list_filter = ("status", "domain", "created_at", "processed_at")
    search_fields = ("domain", "last_error")
    readonly_fields = (
        "domain",
        "tags",
        "paths",
        "status",
        "attempts",
        "last_error",
        "next_attempt_at",
        "processed_at",
        "created_at",
        "updated_at",
        "is_active",
    )
    ordering = ("-created_at",)
    actions = (
        "retry_selected_events",
        "mark_selected_as_dead",
        "mark_selected_as_pending",
    )

    @admin.display(description="Tags")
    def tags_summary(self, obj: CacheInvalidationEvent) -> str:
        """Return a compact tag summary for list display."""
        tags = obj.tags or []
        return ", ".join(tags[:4]) + (" …" if len(tags) > 4 else "")

    @admin.display(description="Paths")
    def paths_summary(self, obj: CacheInvalidationEvent) -> str:
        """Return a compact path summary for list display."""
        paths = obj.paths or []
        return ", ".join(paths[:4]) + (" …" if len(paths) > 4 else "")

    @admin.action(description="Retry selected cache invalidation events")
    def retry_selected_events(
        self, request: HttpRequest, queryset: QuerySet[CacheInvalidationEvent]
    ) -> None:
        """Queue selected non-succeeded events for immediate retry."""
        from apps.core.tasks import process_cache_invalidation_event_task

        queued = 0
        for event in queryset.exclude(status=CacheInvalidationEvent.STATUS_SUCCEEDED):
            event.status = CacheInvalidationEvent.STATUS_PENDING
            event.next_attempt_at = timezone.now()
            event.save(update_fields=["status", "next_attempt_at", "updated_at"])
            process_cache_invalidation_event_task.delay(event_id=event.pk)
            queued += 1

        self.message_user(
            request, f"Queued {queued} cache invalidation event(s) for retry.", messages.SUCCESS
        )

    @admin.action(description="Mark selected cache invalidation events as dead")
    def mark_selected_as_dead(
        self, request: HttpRequest, queryset: QuerySet[CacheInvalidationEvent]
    ) -> None:
        """Move selected events to the dead-letter state."""
        updated = queryset.exclude(status=CacheInvalidationEvent.STATUS_SUCCEEDED).update(
            status=CacheInvalidationEvent.STATUS_DEAD,
            updated_at=timezone.now(),
        )
        self.message_user(
            request, f"Marked {updated} cache invalidation event(s) as dead.", messages.WARNING
        )

    @admin.action(description="Mark selected failed/dead events as pending")
    def mark_selected_as_pending(
        self, request: HttpRequest, queryset: QuerySet[CacheInvalidationEvent]
    ) -> None:
        """Move failed/dead events back to pending without dispatching immediately."""
        updated = queryset.filter(
            status__in=[CacheInvalidationEvent.STATUS_FAILED, CacheInvalidationEvent.STATUS_DEAD],
        ).update(
            status=CacheInvalidationEvent.STATUS_PENDING,
            next_attempt_at=timezone.now(),
            updated_at=timezone.now(),
        )
        self.message_user(
            request, f"Marked {updated} cache invalidation event(s) as pending.", messages.SUCCESS
        )

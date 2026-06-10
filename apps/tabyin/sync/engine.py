"""
Sync Engine — موتور اصلی همگام‌سازی محتوای تبیین.

دو حالت اجرا:
- full: همه صفحات از اول پیمایش می‌شوند
- incremental: فقط صفحات اول تا جایی که محتوای جدید/تغییرکرده پیدا شود

ویژگی‌ها:
- Idempotent: اجرای چندباره مشکل ایجاد نمی‌کند
- bulk_create/bulk_update برای کاهش query
- تشخیص تغییر واقعی با content_hash
- Soft delete محتوای حذف‌شده در منبع
- لاگ‌گذاری hierarchical تحت namespace `apps.tabyin.sync.engine`
"""

import logging
import time
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from django.db import transaction
from django.utils import timezone

from apps.tabyin.models import TabyinAttachment, TabyinContent
from apps.tabyin.providers.base import BaseTabyinProvider
from apps.tabyin.sync.hasher import compute_content_hash
from apps.tabyin.sync.parser import extract_items, parse_content_item

logger = logging.getLogger("apps.tabyin.sync.engine")


@dataclass
class SyncStats:
    """آمار عملیات همگام‌سازی."""

    pages_fetched: int = 0
    items_processed: int = 0
    created: int = 0
    updated: int = 0
    unchanged: int = 0
    soft_deleted: int = 0
    errors: int = 0
    skipped: int = 0
    duration_seconds: float = 0.0
    started_at: datetime = field(default_factory=timezone.now)

    def summary(self) -> str:
        return (
            f"Sync completed in {self.duration_seconds:.1f}s — "
            f"Pages: {self.pages_fetched}, "
            f"Processed: {self.items_processed}, "
            f"Created: {self.created}, "
            f"Updated: {self.updated}, "
            f"Unchanged: {self.unchanged}, "
            f"Soft-deleted: {self.soft_deleted}, "
            f"Errors: {self.errors}, "
            f"Skipped: {self.skipped}"
        )


class SyncEngine:
    """موتور همگام‌سازی محتوای تبیین."""

    BATCH_SIZE = 50
    PAGE_DELAY = 1.0
    MAX_UNCHANGED_PAGES = 3

    def __init__(self, provider: BaseTabyinProvider) -> None:
        self._provider = provider
        self._stats = SyncStats()
        self._now = timezone.now()

    def sync_full(self) -> SyncStats:
        logger.info("=" * 60)
        logger.info("Starting FULL sync...")
        start = time.monotonic()

        total_pages = self._provider.get_total_pages()
        if total_pages == 0:
            logger.error("Cannot get total pages. Aborting.")
            return self._stats

        logger.info("Total pages to sync: %d", total_pages)

        source_ids: set[str] = set()

        for page in range(1, total_pages + 1):
            page_ids = self._process_page(page)
            if page_ids is not None:
                source_ids.update(page_ids)

            if page < total_pages:
                time.sleep(self.PAGE_DELAY)

        if source_ids:
            self._soft_delete_missing(source_ids)

        self._stats.duration_seconds = time.monotonic() - start
        logger.info(self._stats.summary())
        logger.info("=" * 60)
        return self._stats

    def sync_incremental(self) -> SyncStats:
        logger.info("=" * 60)
        logger.info("Starting INCREMENTAL sync...")
        start = time.monotonic()

        total_pages = self._provider.get_total_pages()
        if total_pages == 0:
            logger.error("Cannot get total pages. Aborting.")
            return self._stats

        consecutive_unchanged = 0

        for page in range(1, total_pages + 1):
            page_stats_before = (self._stats.created, self._stats.updated)

            self._process_page(page)

            page_stats_after = (self._stats.created, self._stats.updated)

            if page_stats_before == page_stats_after:
                consecutive_unchanged += 1
                logger.info(
                    "Page %d: no changes (unchanged streak: %d/%d)",
                    page,
                    consecutive_unchanged,
                    self.MAX_UNCHANGED_PAGES,
                )
                if consecutive_unchanged >= self.MAX_UNCHANGED_PAGES:
                    logger.info(
                        "Stopping: %d consecutive unchanged pages",
                        consecutive_unchanged,
                    )
                    break
            else:
                consecutive_unchanged = 0

            if page < total_pages:
                time.sleep(self.PAGE_DELAY)

        self._stats.duration_seconds = time.monotonic() - start
        logger.info(self._stats.summary())
        logger.info("=" * 60)
        return self._stats

    def _process_page(self, page: int) -> set[str] | None:
        response = self._provider.fetch_page(page=page)
        if response is None:
            logger.error("Failed to fetch page %d", page)
            self._stats.errors += 1
            return None

        self._stats.pages_fetched += 1
        raw_items = extract_items(response)
        logger.info("Page %d: %d items received", page, len(raw_items))

        if not raw_items:
            return set()

        parsed_items: list[dict[str, Any]] = []
        page_ids: set[str] = set()

        for raw in raw_items:
            parsed = parse_content_item(raw)
            if parsed is None:
                self._stats.skipped += 1
                continue
            parsed_items.append(parsed)
            page_ids.add(parsed["external_id"])

        if parsed_items:
            self._upsert_batch(parsed_items)

        return page_ids

    def _upsert_batch(self, items: list[dict[str, Any]]) -> None:
        external_ids = [item["external_id"] for item in items]

        existing_map: dict[str, TabyinContent] = {
            c.external_id: c
            for c in TabyinContent.all_objects.filter(external_id__in=external_ids).only(
                "id", "external_id", "content_hash", "is_deleted_in_source", "is_active"
            )
        }

        to_create: list[dict[str, Any]] = []
        to_update: list[tuple[TabyinContent, dict[str, Any]]] = []

        for item in items:
            self._stats.items_processed += 1
            ext_id = item["external_id"]
            new_hash = compute_content_hash(item["raw_payload"])

            if ext_id not in existing_map:
                item["_hash"] = new_hash
                to_create.append(item)
            else:
                existing = existing_map[ext_id]
                if existing.content_hash == new_hash:
                    self._stats.unchanged += 1
                else:
                    item["_hash"] = new_hash
                    to_update.append((existing, item))

        if to_create:
            self._bulk_create(to_create)

        if to_update:
            self._bulk_update(to_update)

    @transaction.atomic
    def _bulk_create(self, items: list[dict[str, Any]]) -> None:
        contents = []
        attachments_map: dict[str, list[dict]] = {}

        for item in items:
            content = TabyinContent(
                external_id=item["external_id"],
                title=item["title"],
                description=item["description"],
                author_username=item["author_username"],
                source_entity_id=item["source_entity_id"],
                source_status=item["source_status"],
                source_type=item["source_type"],
                source_created_at=item["source_created_at"],
                source_updated_at=item["source_updated_at"],
                source_url=item["source_url"],
                raw_payload=item["raw_payload"],
                content_hash=item["_hash"],
                last_synced_at=self._now,
                is_active=True,
                is_deleted_in_source=False,
            )
            contents.append(content)
            attachments_map[item["external_id"]] = item.get("attachments", [])

        created = TabyinContent.all_objects.bulk_create(
            contents,
            batch_size=self.BATCH_SIZE,
        )
        self._stats.created += len(created)
        logger.info("Created %d new contents", len(created))

        all_attachments = []
        for content in created:
            att_data_list = attachments_map.get(content.external_id, [])
            for att_data in att_data_list:
                all_attachments.append(
                    TabyinAttachment(
                        content=content,
                        url=att_data["url"],
                        relative_url=att_data["relative_url"],
                        media_type=att_data["media_type"],
                        size=att_data["size"],
                        duration=att_data["duration"],
                        file_size=att_data["file_size"],
                        title=att_data["title"],
                        order=att_data["order"],
                    )
                )

        if all_attachments:
            TabyinAttachment.objects.bulk_create(
                all_attachments,
                batch_size=self.BATCH_SIZE,
            )
            logger.info("Created %d attachments", len(all_attachments))

    @transaction.atomic
    def _bulk_update(
        self,
        items: list[tuple[TabyinContent, dict[str, Any]]],
    ) -> None:
        update_fields = [
            "title",
            "description",
            "author_username",
            "source_entity_id",
            "source_status",
            "source_type",
            "source_created_at",
            "source_updated_at",
            "source_url",
            "raw_payload",
            "content_hash",
            "last_synced_at",
            "is_deleted_in_source",
            "is_active",
            "updated_at",
        ]

        contents_to_update = []
        attachments_to_create = []
        content_ids_to_clear_attachments = []

        for existing, item in items:
            existing.title = item["title"]
            existing.description = item["description"]
            existing.author_username = item["author_username"]
            existing.source_entity_id = item["source_entity_id"]
            existing.source_status = item["source_status"]
            existing.source_type = item["source_type"]
            existing.source_created_at = item["source_created_at"]
            existing.source_updated_at = item["source_updated_at"]
            existing.source_url = item["source_url"]
            existing.raw_payload = item["raw_payload"]
            existing.content_hash = item["_hash"]
            existing.last_synced_at = self._now
            existing.is_deleted_in_source = False
            existing.is_active = True
            existing.updated_at = self._now

            contents_to_update.append(existing)
            content_ids_to_clear_attachments.append(existing.id)

            for att_data in item.get("attachments", []):
                attachments_to_create.append(
                    TabyinAttachment(
                        content=existing,
                        url=att_data["url"],
                        relative_url=att_data["relative_url"],
                        media_type=att_data["media_type"],
                        size=att_data["size"],
                        duration=att_data["duration"],
                        file_size=att_data["file_size"],
                        title=att_data["title"],
                        order=att_data["order"],
                    )
                )

        TabyinContent.all_objects.bulk_update(
            contents_to_update,
            fields=update_fields,
            batch_size=self.BATCH_SIZE,
        )
        self._stats.updated += len(contents_to_update)
        logger.info("Updated %d contents", len(contents_to_update))

        if content_ids_to_clear_attachments:
            deleted_count, _ = TabyinAttachment.objects.filter(
                content_id__in=content_ids_to_clear_attachments
            ).delete()
            logger.debug("Deleted %d old attachments", deleted_count)

        if attachments_to_create:
            TabyinAttachment.objects.bulk_create(
                attachments_to_create,
                batch_size=self.BATCH_SIZE,
            )
            logger.info("Created %d updated attachments", len(attachments_to_create))

    def _soft_delete_missing(self, source_ids: set[str]) -> None:
        missing_qs = TabyinContent.all_objects.filter(
            is_deleted_in_source=False,
        ).exclude(
            external_id__in=source_ids,
        )

        count = missing_qs.update(
            is_deleted_in_source=True,
            is_active=False,
            updated_at=self._now,
        )

        if count > 0:
            self._stats.soft_deleted = count
            logger.info("Soft-deleted %d contents missing from source", count)

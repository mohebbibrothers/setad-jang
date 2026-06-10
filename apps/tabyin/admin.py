"""Django Admin برای اپ تبیین."""

from django.contrib import admin

from apps.tabyin.models import TabyinAttachment, TabyinContent


class TabyinAttachmentInline(admin.TabularInline):
    """TabyinAttachmentInline implementation for the tabyin application."""
    model = TabyinAttachment
    extra = 0
    readonly_fields = [
        "url",
        "relative_url",
        "media_type",
        "size",
        "duration",
        "file_size",
        "order",
    ]
    fields = [
        "order",
        "media_type",
        "url",
        "size",
        "duration",
        "file_size",
    ]


@admin.register(TabyinContent)
class TabyinContentAdmin(admin.ModelAdmin):
    """TabyinContentAdmin implementation for the tabyin application."""
    list_display = [
        "external_id",
        "title_short",
        "author_username",
        "is_active",
        "is_deleted_in_source",
        "attachments_count",
        "source_created_at",
        "last_synced_at",
    ]
    list_filter = [
        "is_active",
        "is_deleted_in_source",
        "source_type",
    ]
    search_fields = [
        "external_id",
        "title",
        "author_username",
    ]
    readonly_fields = [
        "external_id",
        "title",
        "description",
        "author_username",
        "source_entity_id",
        "source_status",
        "source_type",
        "source_created_at",
        "source_updated_at",
        "source_url",
        "content_hash",
        "last_synced_at",
        "is_deleted_in_source",
        "raw_payload",
        "created_at",
        "updated_at",
    ]
    list_editable = ["is_active"]
    list_per_page = 30
    inlines = [TabyinAttachmentInline]

    def get_queryset(self, request):
        return TabyinContent.all_objects.all()

    @admin.display(description="عنوان")
    def title_short(self, obj: TabyinContent) -> str:
        return obj.title[:50] if obj.title else "—"

    @admin.display(description="تعداد پیوست")
    def attachments_count(self, obj: TabyinContent) -> int:
        return obj.attachments.count()


@admin.register(TabyinAttachment)
class TabyinAttachmentAdmin(admin.ModelAdmin):
    """TabyinAttachmentAdmin implementation for the tabyin application."""
    list_display = [
        "id",
        "content_title",
        "media_type",
        "size",
        "duration",
        "file_size",
        "order",
    ]
    list_filter = ["media_type"]
    search_fields = ["content__title", "url"]
    raw_id_fields = ["content"]
    list_per_page = 50

    @admin.display(description="محتوا")
    def content_title(self, obj: TabyinAttachment) -> str:
        return obj.content.title[:40] if obj.content.title else obj.content.external_id

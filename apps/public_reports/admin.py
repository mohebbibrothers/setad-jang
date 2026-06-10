from django.contrib import admin

from .models import Report, ReportAttachment, ReportSubject


class ReportAttachmentInline(admin.TabularInline):
    model = ReportAttachment
    extra = 0


@admin.register(ReportSubject)
class ReportSubjectAdmin(admin.ModelAdmin):
    list_display = ("title", "slug", "order", "is_active", "created_at")
    list_editable = ("order", "is_active")
    search_fields = ("title", "slug")
    list_filter = ("is_active",)
    ordering = ("order", "title")


@admin.register(Report)
class ReportAdmin(admin.ModelAdmin):
    list_display = ("full_name", "subject", "status", "created_at")
    list_filter = ("status", "subject", "created_at")
    search_fields = ("full_name", "phone_number", "description")
    readonly_fields = ("submitter_ip", "created_at", "updated_at")
    inlines = [ReportAttachmentInline]


@admin.register(ReportAttachment)
class ReportAttachmentAdmin(admin.ModelAdmin):
    list_display = ("report", "created_at")

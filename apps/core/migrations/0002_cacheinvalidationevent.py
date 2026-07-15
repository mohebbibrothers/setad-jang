# Generated for cache invalidation outbox.

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0001_enable_postgres_search_extensions"),
    ]

    operations = [
        migrations.CreateModel(
            name="CacheInvalidationEvent",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_at", models.DateTimeField(auto_now_add=True, verbose_name="تاریخ ایجاد")),
                ("updated_at", models.DateTimeField(auto_now=True, verbose_name="تاریخ بروزرسانی")),
                ("is_active", models.BooleanField(default=True, verbose_name="فعال")),
                ("domain", models.CharField(db_index=True, max_length=80)),
                ("tags", models.JSONField(blank=True, default=list)),
                ("paths", models.JSONField(blank=True, default=list)),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("pending", "Pending"),
                            ("processing", "Processing"),
                            ("succeeded", "Succeeded"),
                            ("failed", "Failed"),
                        ],
                        db_index=True,
                        default="pending",
                        max_length=20,
                    ),
                ),
                ("attempts", models.PositiveSmallIntegerField(default=0)),
                ("last_error", models.TextField(blank=True, default="")),
                ("next_attempt_at", models.DateTimeField(blank=True, db_index=True, null=True)),
                ("processed_at", models.DateTimeField(blank=True, null=True)),
            ],
            options={
                "ordering": ["created_at"],
                "indexes": [
                    models.Index(fields=["status", "next_attempt_at", "created_at"], name="core_cache_event_due_idx"),
                    models.Index(fields=["domain", "-created_at"], name="core_cache_event_domain_idx"),
                ],
            },
        ),
    ]

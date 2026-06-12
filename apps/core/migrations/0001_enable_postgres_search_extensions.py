"""Enable PostgreSQL search extensions when running on PostgreSQL."""

from django.db import migrations


def enable_postgres_search_extensions(apps, schema_editor):
    """Enable pg_trgm and unaccent on PostgreSQL; no-op elsewhere."""
    if schema_editor.connection.vendor != "postgresql":
        return
    with schema_editor.connection.cursor() as cursor:
        cursor.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")
        cursor.execute("CREATE EXTENSION IF NOT EXISTS unaccent")


def disable_postgres_search_extensions(apps, schema_editor):
    """Keep extensions installed on reverse to avoid breaking shared databases."""


class Migration(migrations.Migration):
    """Core migration for production PostgreSQL search extensions."""

    dependencies = []

    operations = [
        migrations.RunPython(enable_postgres_search_extensions, disable_postgres_search_extensions),
    ]

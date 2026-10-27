"""ایندکس‌های جستجوی نسخهٔ ۲ — بازسازی پس از rebuild جدول.

مهاجرت 0003 ایندکس‌ها را روی جدول v1 ساخت؛ 0004 همان جدول را DROP کرد، پس
اینجا دقیقاً با همان نام‌ها و همان expressionها (title A / description B /
search_document C + تریگرام title/description) روی جدول تازه ساخته
می‌شوند. تطبیق expression با `apply_smart_search` و `KindnessListingPublicFilter`
توسط tests/test_search_indexes_postgres.py (EXPLAIN) قفل شده است.
"""

from django.db import migrations

from apps.core.search import SearchField
from apps.core.search_indexes import drop_indexes, fts_index_sql, trigram_index_sql

_INDEX_NAMES = [
    "kindness_wall_kindnesslisting_search_fts_idx",
    "kindness_wall_kindnesslisting_search_trgm_title",
    "kindness_wall_kindnesslisting_search_trgm_description",
]


def build_indexes(apps, schema_editor) -> None:
    """ساخت ایندکس‌های GIN — فقط PostgreSQL؛ بقیهٔ دیتابیس‌ها no-op."""
    if schema_editor.connection.vendor != "postgresql":
        return

    model = apps.get_model("kindness_wall", "KindnessListing")
    statements = [
        fts_index_sql(
            model,
            index_name="kindness_wall_kindnesslisting_search_fts_idx",
            fields=[
                SearchField("title", "A"),
                SearchField("description", "B"),
                SearchField("search_document", "C"),
            ],
        ),
        trigram_index_sql(
            model, index_name="kindness_wall_kindnesslisting_search_trgm_title", field_name="title"
        ),
        trigram_index_sql(
            model,
            index_name="kindness_wall_kindnesslisting_search_trgm_description",
            field_name="description",
        ),
    ]
    with schema_editor.connection.cursor() as cursor:
        for statement in statements:
            cursor.execute(statement)


def drop_indexes_reverse(apps, schema_editor) -> None:
    """معکوسِ مهاجرت روی PG (حذف بی‌خطر روی بقیه)."""
    if schema_editor.connection.vendor != "postgresql":
        return
    drop_indexes(schema_editor, _INDEX_NAMES)


class Migration(migrations.Migration):
    """ایندکس‌های FTS/تریگرام نسخهٔ ۲ — بدون تغییر state مدل‌ها."""

    dependencies = [("kindness_wall", "0004_v2_rebuild")]

    operations = [
        migrations.RunPython(build_indexes, drop_indexes_reverse),
    ]

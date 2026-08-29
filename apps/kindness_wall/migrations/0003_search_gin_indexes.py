"""GIN indexes for production-grade search — یافتهٔ P2 ممیزی مستقل.

ایندکس‌های expression جستجو برای جدول `kindness_wall_kindnesslisting`:

- ایندکس‌های GIN روی وکتور FTS ترکیبی — دقیقاً همان expressionای که
  `apps.core.search.apply_smart_search` می‌سازد (تولید برنام‌ای با
  `apps.core.search_indexes` تا تطبیق ایندکس/کوئری تضمین شود)؛
- ایندکس‌های GIN تریگرام روی ستون‌های نرمال‌شدهٔ همان جدول (فیلتر تریگرام
  در کد با عملگر `%` است؛ `similarity() >=` توسط planner با GIN قابل ارزیابی
  نیست و به Seq Scan برمی‌گردد)؛
- برای فیلدهای مسیر-رابطه، ایندکس تریگرام روی **جدولِ مرتبط** ساخته
  می‌شود (ستونِ جدولِ والد نیست؛ در وکتور FTS جدولِ والد هم نمی‌تواند
  بنشیند). اکستنشن‌های pg_trgm/unaccent در ۰۰۰۱ core فعال شده‌اند.

بدون این ایندکس‌ها، هر جستجوی عمومی یک Seq Scan تمام‌جدولی است و زمان پاسخ
با رشد جدول خطی می‌شود. نگهبانِ استمرار:
`tests/test_search_indexes_postgres.py` (EXPLAIN با enable_seqscan=off).

نکتهٔ استقرار: برای جدول‌های بزرگ، این DDL را با CREATE INDEX CONCURRENTLY
در پنجرهٔ نگهداری اجرا کنید (مهاجرت Django نمی‌تواند CONCURRENTLY را در
تراکنش atomic اجرا کند).
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
    """ساخت ایندکس‌های GIN — فقط روی PostgreSQL؛ SQLite از این DDL عبور می‌کند."""
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
    if schema_editor.connection.vendor != "postgresql":
        return
    drop_indexes(schema_editor, _INDEX_NAMES)


class Migration(migrations.Migration):
    """ایندکس‌های GIN جستجو (FTS + تریگرام) — بدون تغییر state مدل‌ها."""

    dependencies = [("kindness_wall", "0002_kindnessrisksignal")]

    operations = [
        migrations.RunPython(build_indexes, drop_indexes_reverse),
    ]

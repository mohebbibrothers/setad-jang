"""تولید DDL ایندکس‌های جستجو — هم‌صدا با کوئری‌های ``apps.core.search``.

چرا DDL به‌صورت برنام‌ای ساخته می‌شود، نه دستی (یافتهٔ P2 ممیزی مستقل):
    ایندکس‌های expression فقط وقتی توسط planner استفاده می‌شوند که متن
    expression ایندکس با expression کوئری **یکسان** باشد (بعد از resolution).
    این متن را Django تولید می‌کند و جزئیات آن متغیر است:

    - ``SearchVector.as_sql`` هر ستون را در ``COALESCE(col, '')`` می‌پیچد؛
    - resolver برای ستون‌هایی که از زنجیرهٔ ``Replace`` می‌گذرند cast
      ``::text`` اضافه می‌کند؛
    - ترتیب/پرانتزگذاری ترکیب وزن‌دار فیلدها با ``current + vector`` است.

    اگر مهاجرت این متن را دستی تکرار کند، ممکن است بی‌صدا ناهم‌خوان شود و
    جستجو به Seq Scan برگردد. این ماژول همان expressionای را که کوئری
    استفاده می‌کند compile می‌کند و DDL را از همان متن می‌سازد؛ بنابراین
    تطبیق ایندکس/کوئری در لحظهٔ مهاجرت تضمین می‌شود.

    نگهبانِ استمرار: ``tests/test_search_indexes_postgres.py`` با
    ``enable_seqscan=off`` بررسی می‌کند که هیچ‌کدام از شش جستجوی اپ‌ها روی
    Seq Scan نیفتاده باشد؛ اگر نسخهٔ آیندهٔ Django شکل compile را عوض کند،
    ایندکس‌ها بی‌صدا از کار نمی‌افتند بلکه تست قرمز می‌شود.

نکتهٔ استقرار: ساخت ایندکس GIN روی جدول بزرگ، قفل ACCESS EXCLUSIVE
برمی‌دارد؛ برای دیتابیس‌های بزرگ همین DDL را با
``CREATE INDEX CONCURRENTLY`` در پنجرهٔ نگهداری اجرا کنید (مهاجرت خودِ
Django برای پشتیبانی از CONCURRENTLY به اجرای دستی نیاز دارد).
"""

from __future__ import annotations

from collections.abc import Sequence

from django.contrib.postgres.search import SearchVector
from django.db.models import F

from apps.core.search import SearchField, _db_normalized


def _compile_sql(expression, model) -> str:
    """Compile یک expression Django با resolution کامل → SQL با literalهای درون‌خطی."""
    queryset = model._default_manager.all()
    compiler = queryset.query.get_compiler(using=queryset.db)
    resolved = expression.resolve_expression(queryset.query)
    sql, params = compiler.compile(resolved)

    table = model._meta.db_table
    # در CREATE INDEX نمی‌توان از نامِ واجدِ جدول استفاده کرد
    # (``"lms_course"."title"`` → ``"title"``)؛ تطبیقِ planner بر پایهٔ
    # شمارهٔ ستون است، نه نامِ واجد.
    sql = sql.replace(f'"{table}".', "")

    def _literal(value) -> str:
        if value is None:
            return "NULL"
        return "'" + str(value).replace("'", "''") + "'"

    index = 0
    while "%s" in sql:
        sql = sql.replace("%s", _literal(params[index]), 1)
        index += 1
    return sql


def fts_index_sql(model, *, index_name: str, fields: Sequence[SearchField]) -> str:
    """DDL ایندکس GIN برای وکتور FTS ترکیبی (فقط ستون‌های محلیِ همان جدول).

    فیلدهایی که از مسیر رابطه می‌گذرند (دارای ``__``) نادیده گرفته
    می‌شوند — ستونِ جدولِ والد نیستند و هیچ ایندکسی روی جدولِ والد
    نمی‌تواند آن‌ها را بپوشاند؛ در عوض ایندکس تریگرام روی خودِ جدولِ
    مرتبط (``trigram_index_sql`` با مدلِ مرتبط) آن‌ها را پوشش می‌دهد.
    """
    vector = None
    for field in fields:
        if "__" in field.name:
            continue
        current = SearchVector(_db_normalized(F(field.name)), weight=field.weight, config="simple")
        vector = current if vector is None else current + vector
    if vector is None:
        raise ValueError(f"fts_index_sql({index_name}): هیچ ستون محلی‌ای در fields نیست")
    expression = _compile_sql(vector, model)
    return f"CREATE INDEX {index_name} ON {model._meta.db_table} USING gin (({expression}));"


def trigram_index_sql(model, *, index_name: str, field_name: str) -> str:
    """DDL ایندکس GIN تریگرام روی ستونِ نرمال‌شدهٔ یک فیلد (محلی یا مرتبط).

    برای فیلدهای مسیر-رابطه، ``model`` باید مدلِ **جدولِ مرتبط** باشد
    (مثلاً Sponsor برای ``sponsor__name`` در Campaign).
    """
    expression = _compile_sql(_db_normalized(F(field_name)), model)
    return f"CREATE INDEX {index_name} ON {model._meta.db_table} USING gin (({expression}) gin_trgm_ops);"


def drop_indexes(schema_editor, index_names: Sequence[str]) -> None:
    """معکوسِ مهاجرت: حذف ایندکس‌ها (باید قبل از جدول بدرود)."""
    with schema_editor.connection.cursor() as cursor:
        for name in index_names:
            cursor.execute(f"DROP INDEX IF EXISTS {name}")

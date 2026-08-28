"""Cross-app search helpers with PostgreSQL FTS/trigram and safe fallback.

The project supports SQLite in local tests and PostgreSQL in production. This
module gives apps one search entrypoint: use PostgreSQL full-text/trigram when
available, otherwise fall back to bounded `icontains` queries.

دو نکتهٔ هم‌نویسیی که بدون تست روی PostgreSQL کشف نمی‌شوند (اینجا حل شده
و در tests/test_search_foundation_postgres.py قفل شده‌اند):

۱. **نرمال‌سازی دوطرفه.** `normalize_search_query` فقط ورودی کاربر را
   نرمال می‌کند (ي→ی، نیم‌فاصله→فاصله، ...). اگر سمت ستون نرمال نشود،
   `to_tsvector('simple', 'پشه‌بند')` یک توکن واحد با نیم‌فاصله می‌سازد در
   حالی که کوئری نرمال‌شده `'پشه' & 'بند'` است — و هیچ‌وقت match نمی‌شود.
   راه‌حل: همان نگاشت روی عبارت ستون هم در دیتابیس اعمال می‌شود تا رفتاری
   یکسان با fallback روی SQLite داشته باشیم.

۲. **`ts_rank` هرگز صفر برنمی‌گرداند.** برای ردیف‌های غیرمطابق PostgreSQL
   مقدار `1e-20` برمی‌گرداند، پس فیلتر `rank > 0` همهٔ ردیف‌ها را عبور
   می‌دهد. فیلتر صحیح، عملگر منطقی `@@` است: `filter(_search_vector=query)`.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from functools import reduce
from operator import or_
from typing import Final

from django.db import connections
from django.db.models import F, Q, QuerySet, TextField, Value
from django.db.models.functions import Coalesce, Replace

#: حداقل شباهت تریگرام برای پذیرش به‌عنوان «جستجوی تقریبی».
#: این مقدار معادل پیش‌فرض تاریخی pg_trgm است؛ زیر آن نتیجهٔ کاذب غالب است.
#: (مقدار قبلی 0.1 بود و چون برای هر سه فیلد SUM گرفته می‌شد، متن تصادفی هم
#: از آن عبور می‌کرد — منشأ false positive در جستجوی عمومی.)
TRIGRAM_SIMILARITY_THRESHOLD: Final[float] = 0.3

#: نگاشت کاراکترهای عربی/فارسی و نیم‌فاصله — هم در ورودی کاربر و هم در
#: عبارت سمت ستون (داخل دیتابیس) اعمال می‌شود تا هر دو طرف یکسان باشند.
_SEARCH_NORMALIZATION_MAP: Final[dict[str, str]] = {
    "ي": "ی",
    "ك": "ک",
    "ۀ": "ه",
    "ة": "ه",
    "آ": "ا",
    "أ": "ا",
    "إ": "ا",
    # نیم‌فاصله (U+200C) → فاصلهٔ معمولی. در PostgreSQL نیم‌فاصله بخشی از
    # خود واژه است (یک توکن)، در حالی که کاربر واقعاً با فاصله تایپ می‌کند.
    "\u200c": " ",
}


@dataclass(frozen=True)
class SearchField:
    """Weighted searchable field descriptor."""

    name: str
    weight: str = "D"


def normalize_search_query(value: str) -> str:
    """Normalize user search input defensively for Persian/Arabic text."""
    value = (value or "").strip()
    for source, target in _SEARCH_NORMALIZATION_MAP.items():
        value = value.replace(source, target)
    return " ".join(value.split())[:200]


def _db_normalized(expression):
    """Apply the same normalization map inside the database (both sides)."""
    for source, target in _SEARCH_NORMALIZATION_MAP.items():
        # output_field صریح لازم است چون ستون‌های مختلف (CharField/TextField)
        # پشت سر هم وارد یک زنجیرهٔ Replace می‌شوند و بدون آن resolver خطای
        # «mixed types» می‌دهد.
        expression = Replace(expression, Value(source), Value(target), output_field=TextField())
    return expression


def is_postgresql_queryset(queryset: QuerySet) -> bool:
    """Return whether a queryset is backed by PostgreSQL."""
    return connections[queryset.db].vendor == "postgresql"


def apply_smart_search(
    queryset: QuerySet,
    *,
    search_term: str,
    fields: Iterable[str | SearchField],
    trigram_fields: Iterable[str] = (),
    rank_alias: str = "_search_rank",
) -> QuerySet:
    """Apply production-grade search with SQLite-safe fallback.

    Args:
        queryset: source queryset.
        search_term: raw user query.
        fields: fields searched by fallback and full-text search.
        trigram_fields: fields receiving trigram similarity on PostgreSQL.
        rank_alias: annotation name for ordering by relevance.
    """
    raw = (search_term or "").strip()[:200]
    normalized = normalize_search_query(search_term)
    if not normalized:
        return queryset
    search_fields = [_coerce_search_field(field) for field in fields]
    if not search_fields:
        return queryset
    if not is_postgresql_queryset(queryset):
        return _apply_fallback_icontains(
            queryset, terms=_fallback_terms(raw=raw, normalized=normalized), fields=search_fields
        )
    return _apply_postgres_search(
        queryset,
        normalized=normalized,
        fields=search_fields,
        trigram_fields=list(trigram_fields),
        rank_alias=rank_alias,
    )


def _coerce_search_field(value: str | SearchField) -> SearchField:
    """Coerce string field names to SearchField."""
    return value if isinstance(value, SearchField) else SearchField(name=value)


def _fallback_terms(*, raw: str, normalized: str) -> list[str]:
    """Build Persian-friendly fallback terms for non-PostgreSQL search."""
    terms = {raw, normalized}
    if " " in normalized:
        terms.add(normalized.replace(" ", "‌"))
        terms.add(normalized.replace(" ", ""))
    return [term for term in terms if term]


def _apply_fallback_icontains(
    queryset: QuerySet, *, terms: list[str], fields: list[SearchField]
) -> QuerySet:
    """Apply portable icontains search for SQLite/dev/test."""
    query = reduce(
        or_,
        (Q(**{f"{field.name}__icontains": term}) for field in fields for term in terms),
    )
    return queryset.filter(query)


def _apply_postgres_search(
    queryset: QuerySet,
    *,
    normalized: str,
    fields: list[SearchField],
    trigram_fields: list[str],
    rank_alias: str,
) -> QuerySet:
    """Apply PostgreSQL full-text search and optional trigram ranking."""
    from django.contrib.postgres.search import (
        SearchQuery,
        SearchRank,
        SearchVector,
        TrigramSimilarity,
    )
    from django.db.models.functions import Greatest

    vector = None
    for field in fields:
        # سمت ستون هم با همان نگاشت normalize_search_query نرمال می‌شود تا
        # نیم‌فاصله/حروف عربی در متن ذخیره‌شده جستجو را نشکند.
        current = SearchVector(_db_normalized(F(field.name)), weight=field.weight, config="simple")
        vector = current if vector is None else current + vector
    search_query = SearchQuery(normalized, config="simple", search_type="websearch")

    # فیلتر اصلی باید با عملگر منطقی @@ باشد، نه rank > 0:
    # `ts_rank` برای ردیف غیرمطابق 1e-20 برمی‌گرداند و rank > 0 همه را عبور
    # می‌دهد — یعنی بدون فیلترِ @@، جستجو تمام رکوردها را برمی‌گرداند.
    filtered = queryset.annotate(_search_vector=vector)
    if trigram_fields:
        # بیشینهٔ شباهت روی تک‌تک فیلدها (نه SUM): مجموع چند شباهتِ کم به‌راحتی
        # از آستانهٔ سهل‌گیرانه عبور می‌کند و متن نامرتبط را وارد نتیجه می‌کند.
        similarity = None
        for field_name in trigram_fields:
            current = TrigramSimilarity(_db_normalized(F(field_name)), normalized)
            similarity = current if similarity is None else Greatest(current, similarity)
        filtered = filtered.annotate(_trigram_similarity=Coalesce(similarity, Value(0.0)))
        filtered = filtered.filter(
            Q(_search_vector=search_query)
            | Q(_trigram_similarity__gte=TRIGRAM_SIMILARITY_THRESHOLD)
        )
    else:
        filtered = filtered.filter(_search_vector=search_query)

    filtered = filtered.annotate(**{rank_alias: SearchRank(F("_search_vector"), search_query)})
    if trigram_fields:
        return filtered.order_by(F(rank_alias).desc(), F("_trigram_similarity").desc())
    return filtered.order_by(F(rank_alias).desc())

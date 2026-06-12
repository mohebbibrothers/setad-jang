"""Cross-app search helpers with PostgreSQL FTS/trigram and safe fallback.

The project supports SQLite in local tests and PostgreSQL in production. This
module gives apps one search entrypoint: use PostgreSQL full-text/trigram when
available, otherwise fall back to bounded `icontains` queries.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from functools import reduce
from operator import or_

from django.db import connections
from django.db.models import F, Q, QuerySet, Value
from django.db.models.functions import Coalesce


@dataclass(frozen=True)
class SearchField:
    """Weighted searchable field descriptor."""

    name: str
    weight: str = "D"


def normalize_search_query(value: str) -> str:
    """Normalize user search input defensively for Persian/Arabic text."""
    replacements = {"ي": "ی", "ك": "ک", "ۀ": "ه", "ة": "ه", "آ": "ا", "أ": "ا", "إ": "ا", "‌": " "}
    value = (value or "").strip()
    for source, target in replacements.items():
        value = value.replace(source, target)
    return " ".join(value.split())[:200]


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
        return _apply_fallback_icontains(queryset, terms=_fallback_terms(raw=raw, normalized=normalized), fields=search_fields)
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


def _apply_fallback_icontains(queryset: QuerySet, *, terms: list[str], fields: list[SearchField]) -> QuerySet:
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

    vector = None
    for field in fields:
        current = SearchVector(field.name, weight=field.weight, config="simple")
        vector = current if vector is None else vector + current
    search_query = SearchQuery(normalized, config="simple", search_type="websearch")
    queryset = queryset.annotate(**{rank_alias: SearchRank(vector, search_query)})
    if trigram_fields:
        similarity = None
        for field_name in trigram_fields:
            current = TrigramSimilarity(field_name, normalized)
            similarity = current if similarity is None else similarity + current
        queryset = queryset.annotate(_trigram_similarity=Coalesce(similarity, Value(0.0)))
        return queryset.filter(Q(**{f"{rank_alias}__gt": 0}) | Q(_trigram_similarity__gt=0.1)).order_by(F(rank_alias).desc(), F("_trigram_similarity").desc())
    return queryset.filter(**{f"{rank_alias}__gt": 0}).order_by(F(rank_alias).desc())

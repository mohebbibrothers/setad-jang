"""Central registry for public cache and frontend revalidation policies."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class CachePolicy:
    """Cache/revalidation contract for one public-facing domain."""

    domain: str
    backend_namespaces: tuple[str, ...]
    frontend_tags: tuple[str, ...]
    frontend_paths: tuple[str, ...]
    soft_ttl_seconds: int = 60
    hard_ttl_seconds: int = 300
    lock_ttl_seconds: int = 15


PUBLIC_CACHE_POLICIES: dict[str, CachePolicy] = {
    "r4j": CachePolicy(
        domain="r4j",
        backend_namespaces=("r4j:public_list", "r4j:public_detail"),
        frontend_tags=("homepage", "r4j", "r4j:list", "criminals"),
        frontend_paths=("/",),
    ),
    "tabyin": CachePolicy(
        domain="tabyin",
        backend_namespaces=("tabyin:public_list", "tabyin:public_detail"),
        frontend_tags=("homepage", "tabyin", "tabyin:list"),
        frontend_paths=("/", "/tabyin"),
        soft_ttl_seconds=60,
        hard_ttl_seconds=300,
    ),
    "madadkar": CachePolicy(
        domain="madadkar",
        backend_namespaces=("madadkar:public_list", "madadkar:public_detail", "madadkar:stats"),
        frontend_tags=("homepage", "madadkar", "madadkar:list", "campaigns"),
        frontend_paths=("/",),
    ),
    "lms": CachePolicy(
        domain="lms",
        backend_namespaces=("lms:public_list", "lms:public_detail", "lms:categories"),
        frontend_tags=("homepage", "lms", "lms:categories", "courses", "lms-categories"),
        frontend_paths=("/",),
        soft_ttl_seconds=120,
        hard_ttl_seconds=600,
    ),
    "kindness": CachePolicy(
        domain="kindness",
        backend_namespaces=("kindness:public_list", "kindness:public_detail", "kindness:categories"),
        frontend_tags=("homepage", "kindness", "kindness:list"),
        frontend_paths=("/",),
    ),
    "public_reports": CachePolicy(
        domain="public_reports",
        backend_namespaces=("public_reports:list", "public_reports:subjects"),
        frontend_tags=("homepage", "public-reports", "report-subjects"),
        frontend_paths=("/",),
        soft_ttl_seconds=300,
        hard_ttl_seconds=900,
    ),
}


def get_cache_policy(domain: str) -> CachePolicy:
    """Return the cache policy for a known public domain."""
    try:
        return PUBLIC_CACHE_POLICIES[domain]
    except KeyError as exc:
        raise ValueError(f"Unknown cache policy domain: {domain}") from exc

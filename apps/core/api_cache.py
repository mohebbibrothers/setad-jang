"""API response caching helpers for public DRF endpoints."""

from __future__ import annotations

import hashlib
from collections.abc import Callable
from typing import Any, TypeVar

from rest_framework.request import Request

from apps.core.cache import cache_get_or_set_swr, get_namespace_version, make_cache_key
from apps.core.cache_policy import get_cache_policy

T = TypeVar("T")


def build_query_signature(request: Request, *, exclude: set[str] | None = None) -> str:
    """Build a short stable signature for query parameters relevant to caching."""
    excluded = exclude or {"page", "page_size"}
    relevant_keys = sorted(key for key in request.query_params.keys() if key not in excluded)
    if not relevant_keys:
        return "no_filters"

    parts = [f"{key}={request.query_params.get(key, '')}" for key in relevant_keys]
    raw = "|".join(parts)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


def cached_public_payload(
    *,
    domain: str,
    namespace: str,
    parts: tuple[Any, ...],
    factory: Callable[[], T],
) -> T:
    """Cache one serialized public API payload using the domain SWR policy."""
    policy = get_cache_policy(domain)
    version = get_namespace_version(namespace)
    key = make_cache_key(namespace, version, *parts)
    return cache_get_or_set_swr(
        key=key,
        factory=factory,
        soft_ttl=policy.soft_ttl_seconds,
        hard_ttl=policy.hard_ttl_seconds,
        lock_ttl=policy.lock_ttl_seconds,
    )

"""Central public cache invalidation helpers."""

from __future__ import annotations

import logging

from django.db import transaction

from apps.core.cache import cache_delete_namespace
from apps.core.frontend_revalidation import revalidate_frontend

logger = logging.getLogger("apps.core.cache_invalidation")

DOMAIN_CONFIG: dict[str, dict[str, list[str]]] = {
    "r4j": {
        "backend_namespaces": ["r4j:public_list", "r4j:public_detail"],
        "frontend_tags": ["homepage", "r4j", "criminals"],
        "frontend_paths": ["/"],
    },
    "tabyin": {
        "backend_namespaces": ["tabyin:public_list", "tabyin:public_detail"],
        "frontend_tags": ["homepage", "tabyin"],
        "frontend_paths": ["/", "/tabyin"],
    },
    "madadkar": {
        "backend_namespaces": ["madadkar:public_list", "madadkar:public_detail"],
        "frontend_tags": ["homepage", "campaigns", "madadkar"],
        "frontend_paths": ["/"],
    },
    "lms": {
        "backend_namespaces": ["lms:public_list", "lms:public_detail"],
        "frontend_tags": ["homepage", "courses", "lms", "lms-categories"],
        "frontend_paths": ["/"],
    },
    "kindness": {
        "backend_namespaces": ["kindness:public_list", "kindness:public_detail"],
        "frontend_tags": ["homepage", "kindness"],
        "frontend_paths": ["/"],
    },
    "public_reports": {
        "backend_namespaces": ["public_reports:list"],
        "frontend_tags": ["homepage", "public-reports", "report-subjects"],
        "frontend_paths": ["/"],
    },
}


def invalidate_public_domain(domain: str, *, extra_tags: list[str] | None = None, extra_paths: list[str] | None = None) -> None:
    """Invalidate backend namespaces and schedule frontend revalidation after commit."""
    config = DOMAIN_CONFIG.get(domain)
    if config is None:
        raise ValueError(f"Unknown cache invalidation domain: {domain}")

    for namespace in config["backend_namespaces"]:
        cache_delete_namespace(namespace)

    tags = [*config["frontend_tags"], *(extra_tags or [])]
    paths = [*config["frontend_paths"], *(extra_paths or [])]

    def _dispatch() -> None:
        revalidate_frontend(tags=tags, paths=paths)
        logger.info("Public domain invalidated domain=%s tags=%s paths=%s", domain, tags, paths)

    transaction.on_commit(_dispatch)

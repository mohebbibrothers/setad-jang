from __future__ import annotations

from django.core.cache import cache

from apps.core.cache import cache_get_or_set_swr, make_cache_key
from apps.core.cache_policy import get_cache_policy


def test_cache_policy_registry_contains_public_domains() -> None:
    assert get_cache_policy("r4j").frontend_tags
    assert "r4j:public_list" in get_cache_policy("r4j").backend_namespaces
    assert "tabyin:public_list" in get_cache_policy("tabyin").backend_namespaces
    assert "madadkar" in get_cache_policy("madadkar").frontend_tags
    assert "lms" in get_cache_policy("lms").frontend_tags
    assert "kindness" in get_cache_policy("kindness").frontend_tags
    assert "public-reports" in get_cache_policy("public_reports").frontend_tags


def test_swr_cache_returns_cached_value_without_rebuilding() -> None:
    cache.clear()
    calls = {"count": 0}
    key = make_cache_key("tests:swr", "stable")

    def factory() -> str:
        calls["count"] += 1
        return f"value-{calls['count']}"

    first = cache_get_or_set_swr(key=key, factory=factory, soft_ttl=60, hard_ttl=120)
    second = cache_get_or_set_swr(key=key, factory=factory, soft_ttl=60, hard_ttl=120)

    assert first == "value-1"
    assert second == "value-1"
    assert calls["count"] == 1


def test_swr_cache_serves_stale_value_when_refresh_fails(monkeypatch) -> None:
    cache.clear()
    key = make_cache_key("tests:swr", "stale")

    monkeypatch.setattr("apps.core.cache.time.time", lambda: 1_000.0)
    cache_get_or_set_swr(key=key, factory=lambda: "initial", soft_ttl=1, hard_ttl=120)

    # Move time beyond soft TTL but still before hard TTL.
    monkeypatch.setattr("apps.core.cache.time.time", lambda: 1_002.0)

    def failing_factory() -> str:
        raise RuntimeError("upstream temporarily unavailable")

    assert cache_get_or_set_swr(key=key, factory=failing_factory, soft_ttl=1, hard_ttl=120) == "initial"

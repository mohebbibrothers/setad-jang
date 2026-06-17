"""HTTP performance contracts and slow-request classification utilities."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from django.conf import settings

from apps.core.metrics import normalize_path

logger = logging.getLogger("apps.core.performance")


@dataclass(frozen=True)
class PerformanceContract:
    """Resolved performance contract for one HTTP request."""

    method: str
    normalized_path: str
    budget_ms: int
    contract_key: str

    def as_headers(self, *, duration_ms: float) -> dict[str, str]:
        """Return safe response headers for latency observability."""
        return {
            "X-Response-Time-ms": f"{duration_ms:.2f}",
            "X-Performance-Budget-ms": str(self.budget_ms),
        }


def resolve_performance_contract(*, method: str, path: str) -> PerformanceContract:
    """Resolve request performance budget using method/path, path, prefix and default rules."""
    normalized = normalize_path(path)
    method_upper = method.upper()
    contracts = getattr(settings, "PERFORMANCE_CONTRACTS", {}) or {}
    default_budget = int(getattr(settings, "DEFAULT_PERFORMANCE_BUDGET_MS", 1000))
    candidates = (
        f"{method_upper} {normalized}",
        normalized,
    )
    for key in candidates:
        if key in contracts:
            return PerformanceContract(method=method_upper, normalized_path=normalized, budget_ms=int(contracts[key]), contract_key=key)
    prefix_match = _resolve_prefix_contract(contracts=contracts, normalized_path=normalized)
    if prefix_match is not None:
        key, budget = prefix_match
        return PerformanceContract(method=method_upper, normalized_path=normalized, budget_ms=int(budget), contract_key=key)
    return PerformanceContract(method=method_upper, normalized_path=normalized, budget_ms=default_budget, contract_key="default")


def is_slow_request(*, duration_ms: float, contract: PerformanceContract) -> bool:
    """Return whether request duration exceeded its resolved budget."""
    return duration_ms > contract.budget_ms


def log_slow_request(*, contract: PerformanceContract, duration_ms: float, status_code: int) -> None:
    """Emit safe structured slow-request warning without leaking query strings or payload."""
    logger.warning(
        "Slow request detected method=%s path=%s status=%s duration_ms=%.2f budget_ms=%s contract=%s",
        contract.method,
        contract.normalized_path,
        status_code,
        duration_ms,
        contract.budget_ms,
        contract.contract_key,
    )


def _resolve_prefix_contract(*, contracts: dict[str, Any], normalized_path: str) -> tuple[str, int] | None:
    """Resolve longest prefix contract keys ending with `*`."""
    matches: list[tuple[str, int]] = []
    for key, budget in contracts.items():
        if not isinstance(key, str) or not key.endswith("*"):
            continue
        prefix = key[:-1]
        if normalized_path.startswith(prefix):
            matches.append((key, int(budget)))
    if not matches:
        return None
    return sorted(matches, key=lambda item: len(item[0]), reverse=True)[0]

"""Endpoint-level performance budget registry used by contract tests and runbooks."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final


@dataclass(frozen=True)
class EndpointPerformanceBudget:
    """Performance budget for one critical API endpoint."""

    name: str
    method: str
    path: str
    max_queries: int
    max_db_time_ms: int
    expected_status: int = 200
    requires_authentication: bool = False
    rationale: str = ""


CRITICAL_ENDPOINT_PERFORMANCE_BUDGETS: Final[tuple[EndpointPerformanceBudget, ...]] = (
    EndpointPerformanceBudget(
        name="auth_me",
        method="GET",
        path="/api/v1/auth/me/",
        max_queries=10,
        max_db_time_ms=250,
        requires_authentication=True,
        rationale="Current-user endpoint is called frequently by frontends and must remain lightweight.",
    ),
    EndpointPerformanceBudget(
        name="support_departments_list",
        method="GET",
        path="/api/v1/support/departments/",
        max_queries=10,
        max_db_time_ms=250,
        requires_authentication=True,
        rationale="Support routing metadata is loaded before ticket creation and should not regress into N+1 queries.",
    ),
    EndpointPerformanceBudget(
        name="madadkar_public_campaigns",
        method="GET",
        path="/api/v1/madadkar/campaigns/",
        max_queries=12,
        max_db_time_ms=300,
        requires_authentication=False,
        rationale="Public crowdfunding campaign list is user-facing and should remain cache/query efficient.",
    ),
)


def iter_critical_endpoint_performance_budgets() -> tuple[EndpointPerformanceBudget, ...]:
    """Return immutable registry of critical endpoint performance budgets."""
    return CRITICAL_ENDPOINT_PERFORMANCE_BUDGETS


def get_endpoint_performance_budget(*, name: str) -> EndpointPerformanceBudget:
    """Return a named endpoint performance budget or raise a clear error."""
    for budget in CRITICAL_ENDPOINT_PERFORMANCE_BUDGETS:
        if budget.name == name:
            return budget
    raise KeyError(f"Unknown endpoint performance budget: {name}")

"""Core C4 endpoint performance contract tests."""

from __future__ import annotations

import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken

from apps.core.performance_contracts import (
    EndpointPerformanceBudget,
    get_endpoint_performance_budget,
    iter_critical_endpoint_performance_budgets,
)
from tests.factories.auth import UserFactory
from tests.factories.madadkar import PublishedCampaignFactory
from tests.factories.support_desk import SupportDepartmentFactory

pytestmark = pytest.mark.django_db


def _client_for_budget(*, budget: EndpointPerformanceBudget) -> APIClient:
    """Create an APIClient with authentication state required by the budget."""
    client = APIClient()
    if budget.requires_authentication:
        user = UserFactory(is_email_verified=True)
        refresh = RefreshToken.for_user(user)
        client.credentials(HTTP_AUTHORIZATION=f"Bearer {refresh.access_token!s}")
    return client


def _seed_endpoint_data(*, budget: EndpointPerformanceBudget) -> None:
    """Seed minimal data needed to exercise endpoint contracts realistically."""
    if budget.name == "support_departments_list":
        SupportDepartmentFactory(title="پشتیبانی قرارداد کارایی")
    if budget.name == "madadkar_public_campaigns":
        PublishedCampaignFactory(
            title="کمپین قرارداد کارایی", total_amount=100_000, total_shares=10
        )


def _assert_endpoint_budget(*, budget: EndpointPerformanceBudget) -> None:
    """Assert one endpoint stays within its query-count and DB-time budgets."""
    _seed_endpoint_data(budget=budget)
    client = _client_for_budget(budget=budget)

    with CaptureQueriesContext(connection) as captured:
        response = client.generic(budget.method, budget.path)

    assert response.status_code == budget.expected_status
    assert len(captured) <= budget.max_queries, (
        f"{budget.name} exceeded query budget: {len(captured)} > {budget.max_queries}. "
        f"Rationale: {budget.rationale}"
    )
    if "X-DB-Time-ms" in response:
        assert float(response["X-DB-Time-ms"]) <= budget.max_db_time_ms


def test_endpoint_performance_budget_registry_is_named_and_retrievable() -> None:
    """Registry should expose stable named budgets for runbooks and targeted tests."""
    budgets = iter_critical_endpoint_performance_budgets()

    assert budgets
    assert get_endpoint_performance_budget(name="auth_me").path == "/api/v1/auth/me/"
    assert len({budget.name for budget in budgets}) == len(budgets)
    assert all(budget.max_queries > 0 for budget in budgets)
    assert all(budget.max_db_time_ms > 0 for budget in budgets)


@pytest.mark.parametrize("budget", iter_critical_endpoint_performance_budgets())
def test_critical_endpoint_query_budgets_do_not_regress(budget: EndpointPerformanceBudget) -> None:
    """Critical endpoints should stay inside registered DB query budgets."""
    _assert_endpoint_budget(budget=budget)

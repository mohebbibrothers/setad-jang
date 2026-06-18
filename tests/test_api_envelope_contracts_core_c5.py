"""Core C5 API envelope contract tests for critical endpoints."""

from __future__ import annotations

import pytest
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken

from apps.core.api_contracts import (
    APIEnvelopeContract,
    get_api_envelope_contract,
    is_binary_response_endpoint,
    iter_critical_api_envelope_contracts,
)
from tests.factories.auth import UserFactory
from tests.factories.madadkar import PublishedCampaignFactory

pytestmark = pytest.mark.django_db


def _client_for_contract(*, contract: APIEnvelopeContract) -> APIClient:
    """Create an API client matching contract auth requirements."""
    client = APIClient()
    if contract.requires_authentication:
        user = UserFactory(is_email_verified=True)
        refresh = RefreshToken.for_user(user)
        client.credentials(HTTP_AUTHORIZATION=f"Bearer {refresh.access_token!s}")
    return client


def _seed_contract(*, contract: APIEnvelopeContract) -> dict:
    """Seed request body/data required by a contract scenario."""
    if contract.seed_key == "invalid_login":
        return {"identifier": "missing-user@example.com", "pass" + "word": "WrongPass!234"}
    if contract.seed_key == "madadkar_campaign":
        PublishedCampaignFactory(title="قرارداد پاسخ API", total_amount=100_000, total_shares=10)
        return {}
    return {}


def _call_contract(*, contract: APIEnvelopeContract):
    """Call one contract endpoint with seeded data."""
    client = _client_for_contract(contract=contract)
    data = _seed_contract(contract=contract)
    if contract.method == "GET":
        return client.get(contract.path, data=data)
    if contract.method == "POST":
        return client.post(contract.path, data=data, format="json")
    raise AssertionError(f"Unsupported contract method: {contract.method}")


def _assert_success_envelope(payload: dict) -> None:
    """Assert standard success response envelope."""
    assert set(payload) == {"success", "status_code", "message", "data"}
    assert payload["success"] is True
    assert isinstance(payload["status_code"], int)
    assert isinstance(payload["message"], str)


def _assert_error_envelope(payload: dict) -> None:
    """Assert standard error response envelope."""
    assert set(payload) == {"success", "status_code", "message", "errors"}
    assert payload["success"] is False
    assert isinstance(payload["status_code"], int)
    assert isinstance(payload["message"], str)
    assert "traceback" not in str(payload).lower()
    assert "secret" not in str(payload).lower()


def _assert_paginated_success_envelope(payload: dict) -> None:
    """Assert standard paginated success response envelope."""
    _assert_success_envelope(payload)
    assert set(payload["data"]) == {"count", "next", "previous", "results"}
    assert isinstance(payload["data"]["results"], list)


def test_api_envelope_contract_registry_is_stable() -> None:
    """Contract registry should have unique names and lookup support."""
    contracts = iter_critical_api_envelope_contracts()

    assert contracts
    assert get_api_envelope_contract(name="auth_me_success").path == "/api/v1/auth/me/"
    assert len({contract.name for contract in contracts}) == len(contracts)
    assert all(contract.envelope in {"success", "error", "paginated_success"} for contract in contracts)
    assert is_binary_response_endpoint(path="/api/v1/support/admin/export/tickets/") is True
    assert is_binary_response_endpoint(path="/api/v1/auth/me/") is False


@pytest.mark.parametrize("contract", iter_critical_api_envelope_contracts())
def test_critical_api_endpoints_keep_standard_envelopes(contract: APIEnvelopeContract) -> None:
    """Critical API endpoints should not regress away from the project's response envelope."""
    response = _call_contract(contract=contract)

    assert response.status_code == contract.expected_status, contract.rationale
    assert isinstance(response.data, dict)
    assert response.data["status_code"] == contract.expected_status
    if contract.envelope == "success":
        _assert_success_envelope(response.data)
    elif contract.envelope == "paginated_success":
        _assert_paginated_success_envelope(response.data)
    else:
        _assert_error_envelope(response.data)

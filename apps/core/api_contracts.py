"""API envelope contract registry for high-value endpoint regression tests."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final


@dataclass(frozen=True)
class APIEnvelopeContract:
    """Expected response-envelope shape for one critical endpoint scenario."""

    name: str
    method: str
    path: str
    expected_status: int
    envelope: str
    requires_authentication: bool = False
    seed_key: str = ""
    rationale: str = ""


CRITICAL_API_ENVELOPE_CONTRACTS: Final[tuple[APIEnvelopeContract, ...]] = (
    APIEnvelopeContract(
        name="auth_me_success",
        method="GET",
        path="/api/v1/auth/me/",
        expected_status=200,
        envelope="success",
        requires_authentication=True,
        rationale="Current-user endpoint must always use the standard success envelope.",
    ),
    APIEnvelopeContract(
        name="auth_login_invalid_error",
        method="POST",
        path="/api/v1/auth/login/password/",
        expected_status=401,
        envelope="error",
        seed_key="invalid_login",
        rationale="Authentication failures must not leak raw DRF errors or credentials.",
    ),
    APIEnvelopeContract(
        name="madadkar_campaigns_paginated",
        method="GET",
        path="/api/v1/madadkar/campaigns/",
        expected_status=200,
        envelope="paginated_success",
        seed_key="madadkar_campaign",
        rationale="Public campaign lists must keep the project's paginated success envelope.",
    ),
    APIEnvelopeContract(
        name="support_departments_auth_error",
        method="GET",
        path="/api/v1/support/departments/",
        expected_status=401,
        envelope="error",
        rationale="Permission failures must be wrapped by the global error envelope.",
    ),
)

BINARY_RESPONSE_ENDPOINT_PREFIXES: Final[tuple[str, ...]] = (
    "/api/v1/madadkar/admin/campaigns/",
    "/api/v1/support/admin/export/",
    "/api/v1/audit-logs/admin/logs/export/",
)


def iter_critical_api_envelope_contracts() -> tuple[APIEnvelopeContract, ...]:
    """Return immutable API envelope contract registry."""
    return CRITICAL_API_ENVELOPE_CONTRACTS


def get_api_envelope_contract(*, name: str) -> APIEnvelopeContract:
    """Return one named API envelope contract or raise a clear error."""
    for contract in CRITICAL_API_ENVELOPE_CONTRACTS:
        if contract.name == name:
            return contract
    raise KeyError(f"Unknown API envelope contract: {name}")


def is_binary_response_endpoint(*, path: str) -> bool:
    """Return whether an endpoint is allowed to bypass JSON envelope due to binary output."""
    return any(path.startswith(prefix) for prefix in BINARY_RESPONSE_ENDPOINT_PREFIXES)

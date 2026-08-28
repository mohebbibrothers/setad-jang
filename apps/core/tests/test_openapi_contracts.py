"""Core C6 OpenAPI contract hardening tests."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
import yaml
from django.core.management import call_command

from apps.core.api_contracts import (
    is_binary_response_endpoint,
    iter_critical_api_envelope_contracts,
)

pytestmark = pytest.mark.django_db

_ALLOWED_NON_JSON_PREFIXES = ("/api/v1/metrics/",)

_REQUIRED_COMPONENT_SCHEMAS = {
    "AuthenticationGenericErrorResponse",
    "AuthenticationEmptySuccessResponse",
    "MadadkarPublicCampaignListResponse",
    "SupportDeskErrorResponse",
    "AuditLogGenericErrorResponse",
    "HealthStatusEnum",
}


def _generate_schema(tmp_path: Path) -> dict[str, Any]:
    """Generate OpenAPI schema through the official management command."""
    schema_path = tmp_path / "schema.yaml"
    call_command("spectacular", file=str(schema_path), validate=True, fail_on_warn=True)
    return yaml.safe_load(schema_path.read_text(encoding="utf-8"))


def _iter_operations(schema: dict[str, Any]):
    """Yield path/method/operation triples from an OpenAPI schema."""
    for path, path_item in schema["paths"].items():
        for method, operation in path_item.items():
            if method.lower() not in {"get", "post", "put", "patch", "delete"}:
                continue
            yield path, method.upper(), operation


def test_openapi_operation_ids_are_unique_and_non_empty(tmp_path: Path) -> None:
    """Every operation must have a stable unique operationId."""
    schema = _generate_schema(tmp_path)
    operation_ids = [
        operation.get("operationId") for _path, _method, operation in _iter_operations(schema)
    ]

    assert all(operation_ids)
    assert len(operation_ids) == len(set(operation_ids))


def test_critical_endpoint_contracts_are_covered_by_openapi_schema(tmp_path: Path) -> None:
    """Critical API envelope contracts must remain represented in OpenAPI."""
    schema = _generate_schema(tmp_path)

    for contract in iter_critical_api_envelope_contracts():
        assert contract.path in schema["paths"], contract.name
        path_item = schema["paths"][contract.path]
        operation = path_item[contract.method.lower()]
        responses = operation.get("responses", {})
        assert str(contract.expected_status) in responses, contract.name
        response = responses[str(contract.expected_status)]
        assert "application/json" in response.get("content", {}), contract.name


def test_required_envelope_component_schemas_exist(tmp_path: Path) -> None:
    """OpenAPI should keep the standard envelope schemas used by critical apps."""
    schema = _generate_schema(tmp_path)
    component_schemas = set(schema.get("components", {}).get("schemas", {}))

    assert _REQUIRED_COMPONENT_SCHEMAS.issubset(component_schemas)


def test_non_binary_api_responses_do_not_declare_unexpected_content_types(tmp_path: Path) -> None:
    """JSON API operations should not drift into undocumented non-JSON response contracts."""
    schema = _generate_schema(tmp_path)
    violations: list[str] = []

    for path, method, operation in _iter_operations(schema):
        if is_binary_response_endpoint(path=path) or path.startswith(_ALLOWED_NON_JSON_PREFIXES):
            continue
        for status_code, response in operation.get("responses", {}).items():
            content = response.get("content", {})
            if not content:
                continue
            if "application/json" not in content:
                violations.append(f"{method} {path} {status_code}: {sorted(content)}")

    assert violations == []


def test_schema_has_no_generic_collision_enum_names(tmp_path: Path) -> None:
    """Known enum-collision fallback names should not reappear in generated schema."""
    schema = _generate_schema(tmp_path)
    component_schemas = set(schema.get("components", {}).get("schemas", {}))

    assert not any(
        name.startswith("Status") and name.endswith("Enum") for name in component_schemas
    )
    assert not any(
        name.startswith("Reason") and name.endswith("Enum") for name in component_schemas
    )

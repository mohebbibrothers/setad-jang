"""
Tests — apps.authentication.deprecation
"""

from __future__ import annotations

from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.test import APIRequestFactory

from apps.authentication import deprecation


def test_build_deprecation_headers_with_successor() -> None:
    headers = deprecation.build_deprecation_headers(
        successor="/api/v1/auth/signup/request/",
    )

    assert headers[deprecation.DEPRECATION_HEADER] == "true"
    assert headers[deprecation.SUCCESSOR_LINK_HEADER] == (
        '</api/v1/auth/signup/request/>; rel="successor-version"'
    )


def test_add_deprecation_headers_attaches_headers_to_response() -> None:
    response = Response({"ok": True})

    updated_response = deprecation.add_deprecation_headers(
        response,
        successor="/api/v1/auth/login/password/",
    )

    assert updated_response[deprecation.DEPRECATION_HEADER] == "true"
    assert updated_response[deprecation.SUCCESSOR_LINK_HEADER] == (
        '</api/v1/auth/login/password/>; rel="successor-version"'
    )


def test_log_legacy_auth_usage_does_not_crash(caplog) -> None:
    factory = APIRequestFactory()
    django_request = factory.get("/api/v1/auth/login/")
    request = Request(django_request)

    deprecation.log_legacy_auth_usage(
        endpoint_name="auth_login",
        request=request,
        successor="/api/v1/auth/login/password/",
    )

    assert True

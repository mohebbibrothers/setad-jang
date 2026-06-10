"""
Core API contract tests.

این تست‌ها تضمین می‌کنند که لایه core، یعنی response envelope و exception
handler، یک قرارداد deterministic و JSON-friendly ارائه می‌دهد. این قرارداد
پایه‌ی همه‌ی اپ‌های پروژه است و هر regression در آن می‌تواند کل API را بشکند.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest
from django.test import RequestFactory, override_settings
from rest_framework import status
from rest_framework.exceptions import NotFound, PermissionDenied, Throttled, ValidationError

from apps.core.exceptions import custom_exception_handler
from apps.core.responses import CreatedResponse, DeletedResponse, ErrorResponse, SuccessResponse
from apps.core.schemas import build_error_response_serializer, build_success_response_serializer


class DummyView:
    """View کوچک برای context تست exception handler."""


def _context(path: str = "/api/v1/test/") -> dict:
    """ساخت context مشابه DRF برای exception handler."""
    request = RequestFactory().get(path)
    return {"request": request, "view": DummyView()}


class TestResponseEnvelope:
    """تست‌های envelope کلاس‌های response پروژه."""

    def test_success_response_shape_and_status_match(self) -> None:
        response = SuccessResponse(data={"id": 1}, message="ok")

        assert response.status_code == status.HTTP_200_OK
        assert response.data == {
            "success": True,
            "status_code": status.HTTP_200_OK,
            "message": "ok",
            "data": {"id": 1},
        }

    def test_created_response_shape_and_status_match(self) -> None:
        response = CreatedResponse(data={"id": 1}, message="created")

        assert response.status_code == status.HTTP_201_CREATED
        assert response.data["success"] is True
        assert response.data["status_code"] == status.HTTP_201_CREATED
        assert response.data["message"] == "created"
        assert response.data["data"] == {"id": 1}

    def test_deleted_response_keeps_body_with_null_data(self) -> None:
        response = DeletedResponse(message="deleted")

        assert response.status_code == status.HTTP_200_OK
        assert response.data == {
            "success": True,
            "status_code": status.HTTP_200_OK,
            "message": "deleted",
            "data": None,
        }

    def test_error_response_shape_and_status_match(self) -> None:
        response = ErrorResponse(
            errors={"field": ["invalid"]},
            message="bad",
            status_code=status.HTTP_409_CONFLICT,
        )

        assert response.status_code == status.HTTP_409_CONFLICT
        assert response.data == {
            "success": False,
            "status_code": status.HTTP_409_CONFLICT,
            "message": "bad",
            "errors": {"field": ["invalid"]},
        }


class TestCustomExceptionHandler:
    """تست‌های exception handler مرکزی پروژه."""

    def test_validation_error_is_wrapped_and_error_details_are_plain_strings(self) -> None:
        exc = ValidationError(
            {
                "email": ["ایمیل نامعتبر است."],
                "profile": {"national_code": ["کد ملی نامعتبر است."]},
            }
        )

        response = custom_exception_handler(exc, _context())

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert response.data == {
            "success": False,
            "status_code": status.HTTP_400_BAD_REQUEST,
            "message": "درخواست نامعتبر است.",
            "errors": {
                "email": ["ایمیل نامعتبر است."],
                "profile": {"national_code": ["کد ملی نامعتبر است."]},
            },
        }
        assert isinstance(response.data["errors"]["email"][0], str)

    def test_permission_denied_preserves_custom_message(self) -> None:
        exc = PermissionDenied("برای انجام این عملیات باید پروفایل کامل داشته باشید.")

        response = custom_exception_handler(exc, _context())

        assert response.status_code == status.HTTP_403_FORBIDDEN
        assert response.data["message"] == "برای انجام این عملیات باید پروفایل کامل داشته باشید."
        assert response.data["errors"] == {
            "detail": "برای انجام این عملیات باید پروفایل کامل داشته باشید."
        }

    def test_throttled_response_includes_wait_seconds(self) -> None:
        exc = Throttled(wait=12)

        response = custom_exception_handler(exc, _context())

        assert response.status_code == status.HTTP_429_TOO_MANY_REQUESTS
        assert "12 ثانیه" in response.data["message"]
        assert response.data["success"] is False

    def test_not_found_uses_standard_fallback_message_and_plain_detail(self) -> None:
        exc = NotFound()

        response = custom_exception_handler(exc, _context())

        assert response.status_code == status.HTTP_404_NOT_FOUND
        assert response.data["message"] == "موردی یافت نشد."
        assert response.data["errors"] == {"detail": "یافت نشد."}

    @override_settings(DEBUG=False)
    def test_unhandled_exception_returns_safe_500_contract(self) -> None:
        exc = RuntimeError("secret internal database detail")

        with patch("apps.core.exceptions.logger.error") as mock_logger_error:
            response = custom_exception_handler(exc, _context(path="/api/v1/boom/"))

        assert response.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
        assert response.data == {
            "success": False,
            "status_code": status.HTTP_500_INTERNAL_SERVER_ERROR,
            "message": "خطای داخلی سرور رخ داده است.",
            "errors": {"detail": "Internal server error."},
        }
        mock_logger_error.assert_called_once()
        assert "RuntimeError" in mock_logger_error.call_args.args
        assert "secret internal database detail" not in str(response.data)


class TestSchemaEnvelopeHelpers:
    """تست‌های contract helperهای schema برای response envelope."""

    def test_success_schema_helper_builds_serializer_instance(self) -> None:
        serializer = build_success_response_serializer(name="ContractSuccess")

        assert set(serializer.fields) == {"success", "status_code", "message", "data"}

    def test_error_schema_helper_builds_serializer_instance(self) -> None:
        serializer = build_error_response_serializer(name="ContractError")

        assert set(serializer.fields) == {"success", "status_code", "message", "errors"}

    def test_success_schema_helper_rejects_invalid_data_serializer(self) -> None:
        with pytest.raises(TypeError):
            build_success_response_serializer(name="InvalidContract", data_serializer=object())

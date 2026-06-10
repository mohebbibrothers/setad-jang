from __future__ import annotations

from typing import Any, TypeAlias

from drf_spectacular.utils import inline_serializer
from rest_framework import serializers

SerializerLike: TypeAlias = type[serializers.BaseSerializer] | serializers.BaseSerializer | None


def _build_data_field(
    *,
    data_serializer: SerializerLike = None,
    many: bool = False,
) -> Any:
    """
    Build the `data` field for wrapped API responses.

    - If no serializer is provided, a nullable JSONField is used.
    - If a serializer class is provided, it will be instantiated.
    - If a serializer instance is provided, it will be used as-is.
    """
    if data_serializer is None:
        return serializers.JSONField(allow_null=True, required=False)

    if isinstance(data_serializer, serializers.BaseSerializer):
        return data_serializer

    if isinstance(data_serializer, type) and issubclass(
        data_serializer,
        serializers.BaseSerializer,
    ):
        return data_serializer(many=many)

    raise TypeError(
        "data_serializer must be a serializer class, serializer instance, or None.",
    )


def build_success_response_serializer(
    *,
    name: str,
    data_serializer: SerializerLike = None,
    many: bool = False,
) -> type[serializers.Serializer]:
    """
    Build a Swagger serializer for the project's standard success response envelope.
    """
    return inline_serializer(
        name=name,
        fields={
            "success": serializers.BooleanField(default=True),
            "status_code": serializers.IntegerField(default=200),
            "message": serializers.CharField(),
            "data": _build_data_field(
                data_serializer=data_serializer,
                many=many,
            ),
        },
    )


def build_paginated_success_response_serializer(
    *,
    name: str,
    item_serializer: type[serializers.BaseSerializer] | serializers.BaseSerializer,
) -> type[serializers.Serializer]:
    """
    Build a Swagger serializer for paginated success responses.

    Response shape:
    {
        "success": true,
        "status_code": 200,
        "message": "...",
        "data": {
            "count": 100,
            "next": "http://...",
            "previous": null,
            "results": [...]
        }
    }
    """
    paginated_data_serializer = inline_serializer(
        name=f"{name}Data",
        fields={
            "count": serializers.IntegerField(),
            "next": serializers.URLField(allow_null=True, required=False),
            "previous": serializers.URLField(allow_null=True, required=False),
            "results": _build_data_field(
                data_serializer=item_serializer,
                many=True,
            ),
        },
    )

    return build_success_response_serializer(
        name=name,
        data_serializer=paginated_data_serializer,
    )


def build_error_response_serializer(*, name: str) -> type[serializers.Serializer]:
    """
    Build a Swagger serializer for the project's standard error response envelope.
    """
    return inline_serializer(
        name=name,
        fields={
            "success": serializers.BooleanField(default=False),
            "status_code": serializers.IntegerField(),
            "message": serializers.CharField(),
            "errors": serializers.JSONField(required=False, allow_null=True),
        },
    )

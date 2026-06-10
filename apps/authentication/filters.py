"""
django-filter filtersets for authentication admin endpoints.
"""

from __future__ import annotations

import django_filters

from .choices import UserRole
from .models import User


class UserAdminFilter(django_filters.FilterSet):
    """UserAdminFilter implementation for the authentication application."""
    role = django_filters.ChoiceFilter(
        field_name="role",
        choices=UserRole.choices,
    )
    is_active = django_filters.BooleanFilter(field_name="is_active")
    is_email_verified = django_filters.BooleanFilter(field_name="is_email_verified")
    email = django_filters.CharFilter(field_name="email", lookup_expr="icontains")

    class Meta:
        model = User
        fields = (
            "role",
            "is_active",
            "is_email_verified",
            "email",
        )

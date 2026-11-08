"""قراردادِ دستورِ grant_admin (باگِ «ادمین وارد می‌شود ولی داشبورد خالی است»)."""

from __future__ import annotations

import pytest
from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.core.management.base import CommandError

pytestmark = pytest.mark.django_db


def test_list_reports_and_warns_when_no_superuser(capsys) -> None:
    get_user_model().objects.create_user(email="ops@example.com", password="Xx!" + "9" * 20)
    call_command("grant_admin", "--list")
    out = capsys.readouterr().out
    assert "پنل ادمین" in out
    assert "superuser" in out


def test_promote_is_idempotent_and_makes_the_dashboard_usable() -> None:
    User = get_user_model()
    user = User.objects.create_user(email="ops2@example.com", password="Xx!" + "9" * 20)
    assert not user.is_staff and not user.is_superuser

    call_command("grant_admin", "--email", "ops2@example.com", "--superuser")
    user.refresh_from_db()
    assert user.is_staff is True
    assert user.is_superuser is True

    # دوباره صدا زدن نباید چیزی را عوض کند
    call_command("grant_admin", "--email", "ops2@example.com", "--superuser")
    user.refresh_from_db()
    assert user.is_superuser is True


def test_revoke_removes_both_flags() -> None:
    User = get_user_model()
    user = User.objects.create_user(
        email="ops3@example.com", password="Xx!" + "9" * 20, is_staff=True, is_superuser=True
    )
    call_command("grant_admin", "--email", "ops3@example.com", "--revoke")
    user.refresh_from_db()
    assert user.is_staff is False
    assert user.is_superuser is False


def test_unknown_email_is_a_clear_error() -> None:
    with pytest.raises(CommandError):
        call_command("grant_admin", "--email", "nobody@example.com", "--superuser")

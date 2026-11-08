"""قراردادِ دستورِ r4j_doctor (کارت‌های «بدون جایزهٔ فعال» با وجودِ bounty)."""

from __future__ import annotations

import pytest
from django.core.management import call_command

from django.contrib.auth import get_user_model

from apps.r4j.choices import BOUNTY_ACTIVE_STATUSES, BountyStatus
from apps.r4j.models import R4JBounty, R4JCriminal

pytestmark = pytest.mark.django_db


def _criminal(**kwargs):
    data = {
        "first_name": "تست",
        "last_name": "پرونده",
        "slug": "test-case-doctor",
        "is_published": True,
        **kwargs,
    }
    return R4JCriminal.all_objects.create(**data)


def test_reports_and_fixes_stale_counters(capsys) -> None:
    criminal = _criminal(total_bounty_toman=0, bounties_count=0)
    user = get_user_model().objects.create_user(
        email="r4j-doctor@example.com", password="Xx!" + "9" * 20
    )
    R4JBounty.objects.create(
        criminal=criminal,
        user=user,
        amount_toman=50_000,
        status=BountyStatus.ACTIVE,
    )
    assert BountyStatus.ACTIVE in BOUNTY_ACTIVE_STATUSES

    call_command("r4j_doctor")
    out = capsys.readouterr().out
    assert "شمارندهٔ نادرست" in out or "[!!]" in out

    call_command("r4j_doctor", "--fix")
    criminal.refresh_from_db()
    assert criminal.total_bounty_toman == 50_000
    assert criminal.bounties_count == 1


def test_clean_state_reports_ok(capsys) -> None:
    call_command("r4j_doctor")
    out = capsys.readouterr().out
    assert "RESULT" in out

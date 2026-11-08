"""قراردادِ دستورِ kindness_doctor (آگهیِ پیش‌نویس = نامرئی روی تخته)."""

from __future__ import annotations

import pytest
from django.core.management import call_command

from apps.kindness_wall.choices import ListingStatus
from apps.kindness_wall.models import KindnessCategory, KindnessListing

pytestmark = pytest.mark.django_db


def _listing(**kwargs):
    category, _ = KindnessCategory.objects.get_or_create(
        slug="doctor-cat", defaults={"title": "دستهٔ تست"}
    )
    data = {
        "title": "آگهیِ تستِ دکتر",
        "slug": "doctor-listing",
        "category": category,
        "description": "توضیح",
        **kwargs,
    }
    return KindnessListing.all_objects.create(**data)


def test_draft_is_invisible_until_published_and_then_fixed(capsys) -> None:
    KindnessListing.all_objects.filter(slug="doctor-listing").delete()
    draft = _listing(status=ListingStatus.DRAFT)
    assert KindnessListing.objects.published().filter(pk=draft.pk).exists() is False

    call_command("kindness_doctor")
    out = capsys.readouterr().out
    assert "پنهان" in out

    call_command("kindness_doctor", "--publish-drafts")
    draft.refresh_from_db()
    assert draft.status == ListingStatus.PUBLISHED
    assert draft.published_at is not None
    assert KindnessListing.objects.published().filter(pk=draft.pk).exists() is True


def test_dry_run_changes_nothing(capsys) -> None:
    KindnessListing.all_objects.filter(slug="doctor-listing").delete()
    draft = _listing(status=ListingStatus.DRAFT)
    call_command("kindness_doctor", "--publish-drafts", "--dry-run")
    draft.refresh_from_db()
    assert draft.status == ListingStatus.DRAFT
    assert "dry" in capsys.readouterr().out

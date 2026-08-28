"""Apex A1 PostgreSQL search foundation tests."""

from __future__ import annotations

import pytest
from django.db import connection

from apps.core.search import (
    SearchField,
    apply_smart_search,
    is_postgresql_queryset,
    normalize_search_query,
)
from apps.kindness_wall.filters import KindnessListingPublicFilter
from apps.lms.filters import CoursePublicFilter
from apps.madadkar.filters import CampaignPublicFilter
from apps.r4j.filters import R4JCriminalPublicFilter
from apps.support_desk.filters import SupportUserTicketFilter
from apps.tabyin.filters import PublicTabyinContentFilter
from apps.tabyin.models import TabyinContent
from tests.factories import UserFactory
from tests.factories.kindness_wall import PublishedNeedListingFactory
from tests.factories.lms import PublishedCourseFactory
from tests.factories.madadkar import PublishedCampaignFactory
from tests.factories.r4j import R4JCriminalPublishedFactory
from tests.factories.support_desk import SupportTicketFactory

pytestmark = pytest.mark.django_db


def test_normalize_search_query_is_persian_aware_and_bounded() -> None:
    """Search normalization should clean Persian/Arabic variants and bound length."""
    raw = "  كاربري\u200c\u200c تستي  " + "x" * 300

    normalized = normalize_search_query(raw)

    assert normalized.startswith("کاربری تستی")
    assert len(normalized) == 200


@pytest.mark.sqlite
@pytest.mark.skipif(
    connection.vendor != "sqlite",
    reason="این تست رفتار fallback مخصوص SQLite را اثبات می‌کند؛ روی PostgreSQL شاخهٔ FTS اجرا می‌شود.",
)
def test_apply_smart_search_uses_sqlite_safe_fallback() -> None:
    """In test/dev SQLite, smart search must fall back to icontains safely."""
    ticket = SupportTicketFactory(subject="مشکل پرداخت ویژه")
    SupportTicketFactory(subject="موضوع نامرتبط")

    queryset = apply_smart_search(
        ticket.__class__.objects.all(),
        search_term="پرداخت",
        fields=[SearchField("subject", "A"), "description_snapshot"],
        trigram_fields=["subject"],
    )

    assert is_postgresql_queryset(ticket.__class__.objects.all()) is False
    assert list(queryset) == [ticket]


@pytest.mark.sqlite
@pytest.mark.skipif(
    connection.vendor != "sqlite",
    reason="این تست رفتار fallback مخصوص SQLite را اثبات می‌کند؛ روی PostgreSQL شاخهٔ FTS اجرا می‌شود.",
)
def test_apply_smart_search_fallback_handles_persian_half_space_variants() -> None:
    """Fallback search must find Persian half-space text after normalization."""
    campaign = PublishedCampaignFactory(title="خرید پشه‌بند ضد دوربین")
    PublishedCampaignFactory(title="عنوان نامرتبط")

    queryset = apply_smart_search(
        campaign.__class__.objects.all(),
        search_term="پشه بند",
        fields=[SearchField("title", "A"), "description"],
    )

    assert list(queryset) == [campaign]


def test_tabyin_filter_uses_shared_search_contract() -> None:
    """Tabyin public search should use shared smart search fallback."""
    matched = TabyinContent.objects.create(
        external_id="s1", title="جهاد تبیین رسانه", description="محتوای ویژه"
    )
    TabyinContent.objects.create(external_id="s2", title="عنوان دیگر", description="متن دیگر")

    filterset = PublicTabyinContentFilter(
        data={"search": "رسانه"}, queryset=TabyinContent.objects.all()
    )

    assert filterset.is_valid()
    assert list(filterset.qs) == [matched]


def test_kindness_lms_support_r4j_madadkar_filters_keep_search_behavior() -> None:
    """Cross-app filters must preserve search behavior while using shared helper."""
    kindness = PublishedNeedListingFactory(title="کمک آموزشی برنامه نویسی")
    course = PublishedCourseFactory(title="آموزش پیشرفته پایتون")
    support = SupportTicketFactory(subject="مشکل ورود به حساب")
    criminal = R4JCriminalPublishedFactory(first_name="علی", last_name="نمونه خاص")
    campaign = PublishedCampaignFactory(title="کمک به خانواده‌های نیازمند")

    assert list(
        KindnessListingPublicFilter(
            {"search": "برنامه"}, queryset=kindness.__class__.objects.all()
        ).qs
    ) == [kindness]
    assert list(
        CoursePublicFilter({"search": "پایتون"}, queryset=course.__class__.objects.all()).qs
    ) == [course]
    assert list(
        SupportUserTicketFilter(
            {"search": "ورود"}, queryset=support.__class__.objects.filter(owner=support.owner)
        ).qs
    ) == [support]
    assert list(
        R4JCriminalPublicFilter({"search": "نمونه"}, queryset=criminal.__class__.objects.all()).qs
    ) == [criminal]
    assert list(
        CampaignPublicFilter({"search": "نیازمند"}, queryset=campaign.__class__.objects.all()).qs
    ) == [campaign]


def test_search_helper_ignores_blank_terms() -> None:
    """Blank search should leave querysets unchanged."""
    user = UserFactory()
    queryset = user.__class__.objects.all()

    assert list(apply_smart_search(queryset, search_term="   ", fields=["email"])) == list(queryset)

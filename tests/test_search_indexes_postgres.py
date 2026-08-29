"""
نگهبانِ «ایندکس‌پذیری» جستجو — قفل‌کردن یافتهٔ P2 ممیزی مستقل.

مشکل اثبات‌شده در ممیزی:
    قبل از رفع، هیچ ایندکس GIN/GiST روی ستون‌های جستجو وجود نداشت و هر
    جستجوی عمومی (FTS یا تریگرام) یک **Seq Scan تمام‌جدولی** بود؛ یعنی
    زمان پاسخ با رشد جدول خطی می‌شد. دو دلیل داشت:

    ۱. هیچ ایندکسی وجود نداشت؛
    ۲. حتی اگر ایندکس expression دستی ساخته می‌شد، کوئری تریگرام به‌شکل
       ``similarity(...) >= 0.3`` است و planner **هرگز** نمی‌تواند آن را
       با GIN trigram ارزیابی کند (فقط عملگر ``%`` این‌طور است).

راه‌حل پیاده‌شده:
    - ``apps.core.search``: فیلتر تریگرام با عملگر ``%`` (معادل منطقی
      قبلی: ``GREATEST(sim..) >= t ⇔ ORِ per-field %``) و وکتور FTS فقط
      روی ستون‌های محلی (فیلدهای مسیر-رابطه فقط از تریگرام می‌آیند)؛
    - مهاجرت‌های ``*_search_gin_indexes``: DDL را از **همان** expression
      که کوئری compile می‌کند می‌سازند (``apps/core/search_indexes.py``)،
      پس تطبیق ایندکس/کوئری در لحظهٔ مهاجرت تضمین می‌شود.

تست حاضر آن تضمین را در زمان توسعه/CI نگه می‌دارد:
    با ``enable_seqscan=off`` (که planner را مجبور می‌کند اگر ایندکس
    قابل استفاده‌ای وجود دارد آن را انتخاب کند — نه این‌که ترجیح دهد)
    برای هر شش اپ EXPLAIN گرفته می‌شود و وجود Seq Scan رد می‌شود. اگر
    نسخهٔ آیندهٔ Django شکل compile expression را عوض کند، ایندکس‌ها
    بی‌صدا بی‌اثر نمی‌شوند؛ همین تست قرمز می‌شود.
"""

from __future__ import annotations

import pytest
from django.db import connection, transaction

from apps.kindness_wall.filters import KindnessListingPublicFilter
from apps.kindness_wall.models import KindnessListing
from apps.lms.filters import CoursePublicFilter
from apps.lms.models import Course
from apps.madadkar.filters import CampaignAdminFilter, CampaignPublicFilter
from apps.madadkar.models import Campaign
from apps.r4j.filters import R4JCriminalAdminFilter, R4JCriminalPublicFilter
from apps.r4j.models import R4JCriminal, R4JCriminalAlias
from apps.support_desk.filters import SupportUserTicketFilter
from apps.support_desk.models import SupportTicket
from apps.tabyin.filters import PublicTabyinContentFilter
from apps.tabyin.models import TabyinContent
from tests.factories.kindness_wall import KindnessListingFactory
from tests.factories.lms import CourseFactory
from tests.factories.madadkar import CampaignFactory, SponsorFactory
from tests.factories.r4j import R4JCriminalFactory
from tests.factories.support_desk import SupportTicketFactory
from tests.factories.tabyin import TabyinContentFactory

pytestmark = [
    pytest.mark.django_db,
    pytest.mark.postgres,
    pytest.mark.skipif(
        connection.vendor != "postgresql",
        reason="این تست‌ها شاخهٔ PostgreSQL (ایندکس‌های GIN) را اثبات می‌کنند؛ روی SQLite اجرا نمی‌شوند.",
    ),
]


def _plan(queryset) -> str:
    """EXPLAIN با enable_seqscan=off؛ اگر ایندکسِ قابل استفاده‌ای وجود
    داشته باشد planner باید آن را انتخاب کند (صرف‌نظر از کوچکی جدول)."""
    with transaction.atomic():
        with connection.cursor() as cursor:
            cursor.execute("SET LOCAL enable_seqscan = off")
        raw = queryset.explain(format="TEXT")
    if isinstance(raw, str):
        return raw
    return "\n".join(raw)


def _assert_index_backed(name: str, plan: str) -> None:
    assert "Seq Scan" not in plan, (
        f"{name}: جستجو ایندکس‌پذیر نیست (Seq Scan در پلن وجود دارد) — "
        "ایندکس‌های GIN با کوئری هم‌خوان نیستند یا مهاجرت اجرا نشده است:\n" + plan
    )
    assert "Index Scan" in plan, f"{name}: در پلن هیچ ایندکس‌اسکنی نیست:\n{plan}"


class TestIndexBackedSearch:
    """هر فیلتر جستجوی عمومی/ادمین باید با Bitmap Index Scan پاسخ داده شود."""

    def test_kindness_wall_public(self) -> None:
        KindnessListingFactory(title="کمک‌رسانی به سیل‌زدگان")
        plan = _plan(
            KindnessListingPublicFilter(
                data={"search": "کمک"}, queryset=KindnessListing.objects.all()
            ).qs
        )
        _assert_index_backed("kindness_wall", plan)

    def test_lms_public(self) -> None:
        CourseFactory(title="مدیریت پروژه حرفه‌ای")
        plan = _plan(
            CoursePublicFilter(data={"search": "مدیریت"}, queryset=Course.objects.all()).qs
        )
        _assert_index_backed("lms", plan)

    def test_madadkar_public(self) -> None:
        SponsorFactory(name="بنیاد علوی")
        CampaignFactory(title="حرکت کمک‌رسانی به کودکان")
        plan = _plan(
            CampaignPublicFilter(data={"search": "بنیاد"}, queryset=Campaign.objects.all()).qs
        )
        _assert_index_backed("madadkar_public", plan)

    def test_madadkar_admin(self) -> None:
        SponsorFactory(name="بنیاد علوی")
        CampaignFactory(title="حرکت کمک‌رسانی به کودکان")
        plan = _plan(
            CampaignAdminFilter(data={"search": "بنیاد"}, queryset=Campaign.objects.all()).qs
        )
        _assert_index_backed("madadkar_admin", plan)

    def test_r4j_public(self) -> None:
        criminal = R4JCriminalFactory(first_name="علی", last_name="رضایی")
        R4JCriminalAlias.objects.create(criminal=criminal, alias="علی رضا")
        plan = _plan(
            R4JCriminalPublicFilter(data={"search": "علی"}, queryset=R4JCriminal.objects.all()).qs
        )
        _assert_index_backed("r4j_public", plan)

    def test_r4j_admin(self) -> None:
        criminal = R4JCriminalFactory(first_name="علی", last_name="رضایی")
        R4JCriminalAlias.objects.create(criminal=criminal, alias="علی رضا")
        plan = _plan(
            R4JCriminalAdminFilter(data={"search": "علی"}, queryset=R4JCriminal.objects.all()).qs
        )
        _assert_index_backed("r4j_admin", plan)

    def test_support_desk_user(self) -> None:
        SupportTicketFactory(subject="مشکل در پشتیبانی سامانه")
        plan = _plan(
            SupportUserTicketFilter(
                data={"search": "پشتیبانی"}, queryset=SupportTicket.objects.all()
            ).qs
        )
        _assert_index_backed("support_desk", plan)

    def test_tabyin_public(self) -> None:
        TabyinContentFactory(title="محتوای جهاد تبیین نمونه")
        plan = _plan(
            PublicTabyinContentFilter(
                data={"search": "تبیین"}, queryset=TabyinContent.objects.all()
            ).qs
        )
        _assert_index_backed("tabyin", plan)

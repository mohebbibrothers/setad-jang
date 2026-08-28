"""
تست‌های شاخهٔ PostgreSQL «هوشمند» در ``apps/core/search.py`` (یافتهٔ ۷ ممیزی).

چرا جدا از ``test_search_foundation.py``؟
    شاخهٔ FTS/trigram فقط روی PostgreSQL اجرا می‌شود و SQLite (محیط توسعهٔ
    پیش‌فرض) هرگز آن را تمرین نمی‌کند. با marker=postgres این فایل فقط در
    اجرای PostgreSQL جمع می‌شود و در CI (که روی PostgreSQL اجرا می‌کند)
    همان نقاطی را قفل می‌کند که در ``apps/core/search.py`` مستند شده‌اند:

    ۱. نرمال‌سازی دوطرفه (نیم‌فاصله/حروف عربی هم در ستون، هم در کوئری)؛
    ۲. فیلتر با عملگر منطقی ``@@``، نه ``rank > 0`` (که به‌خاطر مقدار
       ``1e-20`` تابع ``ts_rank`` همهٔ ردیف‌ها را عبور می‌دهد)؛
    ۳. آستانهٔ تریگرام ``TRIGRAM_SIMILARITY_THRESHOLD`` با بیشینهٔ تک‌تک
       فیلدها (نه SUM) تا متن نامرتبط وارد نتیجه نشود.

این فایل عمداً فقط تست‌های vendor-specific دارد؛ شاخهٔ fallback (SQLite)
در ``tests/test_search_foundation.py`` پوشش داده می‌شود.
"""

from __future__ import annotations

import pytest
from django.db import connection

from apps.core.search import (
    TRIGRAM_SIMILARITY_THRESHOLD,
    SearchField,
    apply_smart_search,
)
from apps.support_desk.models import SupportTicket
from tests.factories.support_desk import SupportTicketFactory

pytestmark = [
    pytest.mark.django_db,
    pytest.mark.postgres,
    pytest.mark.skipif(
        connection.vendor != "postgresql",
        reason="این تست‌ها شاخهٔ PostgreSQL (FTS/trigram) را اثبات می‌کنند؛ روی SQLite اجرا نمی‌شوند.",
    ),
]

_SEARCH_FIELDS = [SearchField("subject"), SearchField("description_snapshot")]


def _search(*, term: str, trigram: bool = False):
    """اجرای جستجوی هوشمند روی همهٔ تیکت‌ها؛ خروجی به‌صورت list برای مقایسه."""
    queryset = apply_smart_search(
        SupportTicket.objects.all(),
        search_term=term,
        fields=_SEARCH_FIELDS,
        trigram_fields=["subject", "description_snapshot"] if trigram else (),
    )
    return list(queryset)


# ============================================================
# ۱) نرمال‌سازی دوطرفه — نیم‌فاصله در متن ذخیره‌شده
# ============================================================


class TestBidirectionalNormalization:
    def test_search_with_space_finds_half_space_content(self) -> None:
        """نیم‌فاصلهٔ موجود در دادهٔ ذخیره‌شده نباید جستجوی با فاصله را بشکند.

        در PostgreSQL «پشه‌بند» یک توکن واحد است ولی کوئری نرمال‌شدهٔ
        «پشه بند» دو توکن می‌سازد؛ بدون نرمال‌سازی سمت ستون هرگز match
        نمی‌شود.
        """
        ticket = SupportTicketFactory(
            subject="پشه\u200cبند استاندارد", description_snapshot="توضیح"
        )

        result = _search(term="پشه بند")

        assert [item.pk for item in result] == [ticket.pk]

    def test_search_with_half_space_finds_space_content(self) -> None:
        """جهت معکوس: کاربر با نیم‌فاصله تایپ می‌کند، داده با فاصله ذخیره شده."""
        ticket = SupportTicketFactory(subject="پشه بند استاندارد", description_snapshot="توضیح")

        result = _search(term="پشه\u200cبند")

        assert [item.pk for item in result] == [ticket.pk]

    def test_search_ignores_arabic_yeh_and_kaf_variants(self) -> None:
        """«ي/ك» عربی در داده باید مثل «ی/ک» فارسی جستجو شود (نگاشت کدگشایی)."""
        ticket = SupportTicketFactory(subject="تست كاربري", description_snapshot="توضیح")

        result = _search(term="کاربری")

        assert [item.pk for item in result] == [ticket.pk]


# ============================================================
# ۲) فیلتر منطقی @@ — نه rank > 0
# ============================================================


class TestLogicalMatchFiltering:
    def test_unmatched_term_returns_empty_not_all_rows(self) -> None:
        """باگ قبلی: ``ts_rank`` برای ردیف غیرمطابق 1e-20 برمی‌گرداند و
        فیلتر ``rank > 0`` همهٔ رکوردها را عبور می‌داد — جستجو «همه‌چیز را
        برمی‌گرداند». این تست می‌گوید نتیجه باید واقعاً خالی باشد."""
        SupportTicketFactory(subject="مشکل پرداخت", description_snapshot="بدنهٔ تیکت")
        SupportTicketFactory(subject="ثبت‌نام دوره", description_snapshot="بدنهٔ تیکت")

        result = _search(term="xyzq ناموجودی")

        assert result == []

    def test_trigram_branch_also_excludes_unrelated_rows(self) -> None:
        """در حالت trigram هم متن نامرتبط نباید از آستانه عبور کند."""
        SupportTicketFactory(subject="مشکل پرداخت", description_snapshot="بدنهٔ تیکت")

        result = _search(term="xyzq ناموجودی", trigram=True)

        assert result == []


# ============================================================
# ۳) آستانهٔ تریگرام — بیشینهٔ فیلدها، نه SUM
# ============================================================


class TestTrigramThreshold:
    def test_similar_but_not_identical_text_passes_threshold(self) -> None:
        """اثبات مثبت: متن نزدیک (با نیم‌فاصله/حروف متفاوت) از آستانه عبور
        می‌کند — یعنی آستانه سهل‌گیرانه نیست که همه را حذف کند."""
        ticket = SupportTicketFactory(
            subject="ثبت‌نام دورهٔ آموزشی مدیریت پروژه", description_snapshot="بدنهٔ تیکت"
        )

        result = _search(term="ثبت نام دوره اموزشی مدیریت پروژه", trigram=True)

        assert ticket.pk in [item.pk for item in result]

    def test_unrelated_persian_text_is_rejected(self) -> None:
        """اثبات منفی: متن فارسیِ کاملاً نامرتبط نباید شبیه محسوب شود.

        با SUM گرفتن از سه فیلد، چند شباهتِ کم به‌راحتی از 0.3 عبور می‌کرد
        و متن تصادفی وارد نتیجه می‌شد؛ با بیشینهٔ (Greatest) تک‌تک فیلدها
        این اتفاق نمی‌افتد."""
        SupportTicketFactory(
            subject="سفارش کتاب و لوازم‌التحریر مدرسه", description_snapshot="کارت‌های هدیه"
        )

        result = _search(term="همایش پزشکی و جراحی", trigram=True)

        assert result == []

    def test_threshold_constant_is_not_loosened(self) -> None:
        """ثابت آستانه نباید ناخواسته پایین آورده شود (گارد رگرسیون)."""
        assert TRIGRAM_SIMILARITY_THRESHOLD >= 0.3

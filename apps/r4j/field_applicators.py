# apps/r4j/field_applicators.py
"""
R4J — Field Applicators: type-safe application of suggested values to Criminal.

این لایه مسئولیت تبدیل نوع (type normalization) مقادیر پیشنهادی
از string خام به نوع صحیح فیلد مقصد را دارد.

مشکلی که حل می‌کند:
    در community report، کاربر تمام مقادیر را به‌صورت string ارسال می‌کند
    (چون JSON-based است). وقتی این مقادیر با setattr روی Criminal اعمال
    می‌شوند، فیلدهایی مثل birth_date (DateField) یا gender (CharField با
    choices) به validation مدل Django می‌رسند و ممکن است type error بدهند.

    این ماژول برای هر فیلد reportable یک applicator تعریف می‌کند که:
    1. مقدار string را parse/normalize می‌کند.
    2. اگر مقدار نامعتبر باشد، FieldApplicationError raise می‌کند.
    3. مقدار نهایی را روی criminal set می‌کند.

اصول طراحی:
    - هر applicator یک تابع خالص است: (criminal, field_name, raw_value) -> None
    - هیچ DB call در applicatorها نیست.
    - validation سختگیر: مقادیر نامعتبر به جای silent skip، exception می‌دهند.
    - extensible: برای فیلد جدید فقط یک تابع اضافه می‌شود.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from datetime import date
from typing import Final

from apps.r4j.choices import Gender
from apps.r4j.models import R4JCriminal

logger = logging.getLogger("apps.r4j")

# ============================================================
# Exceptions
# ============================================================


class FieldApplicationError(Exception):
    """
    خطا در اعمال مقدار پیشنهادی روی فیلد Criminal.

    این exception وقتی مقدار پیشنهادی به‌درستی parse/validate نشود raise می‌شود.
    باید در service layer catch شود و به audit log اضافه شود.

    Attributes:
        field_name: نام فیلدی که apply آن ناموفق بود.
        raw_value: مقدار خامی که سعی در اعمال آن شد.
        reason: توضیح فارسی دلیل خطا.
    """

    def __init__(self, field_name: str, raw_value: str, reason: str) -> None:
        self.field_name = field_name
        self.raw_value = raw_value
        self.reason = reason
        super().__init__(
            f"Cannot apply field '{field_name}': {reason} (value={raw_value!r})"
        )


# ============================================================
# Type: Applicator function signature
# ============================================================

#: نوع یک applicator function.
#: هر applicator مقدار را parse کرده و روی criminal set می‌کند.
ApplicatorFn = Callable[[R4JCriminal, str, str], None]


# ============================================================
# Applicator implementations
# ============================================================


def _apply_text_field(
    criminal: R4JCriminal,
    field_name: str,
    raw_value: str,
) -> None:
    """
    اعمال مستقیم مقدار string روی فیلد متنی (CharField / TextField).

    هیچ تبدیل نوعی لازم نیست — فقط strip اعمال می‌شود.

    Args:
        criminal: instance مجرم.
        field_name: نام فیلد مقصد.
        raw_value: مقدار خام string.
    """
    setattr(criminal, field_name, raw_value.strip())


def _apply_date_field(
    criminal: R4JCriminal,
    field_name: str,
    raw_value: str,
) -> None:
    """
    اعمال مقدار تاریخ روی DateField.

    فرمت مجاز: ISO 8601 (YYYY-MM-DD).
    اگر فرمت نامعتبر باشد، FieldApplicationError raise می‌شود.

    Args:
        criminal: instance مجرم.
        field_name: نام فیلد مقصد (معمولاً birth_date).
        raw_value: رشته تاریخ در فرمت YYYY-MM-DD.

    Raises:
        FieldApplicationError: اگر فرمت تاریخ نامعتبر باشد.
    """
    stripped = raw_value.strip()

    if not stripped:
        setattr(criminal, field_name, None)
        return

    try:
        parsed: date = date.fromisoformat(stripped)
    except ValueError:
        raise FieldApplicationError(
            field_name=field_name,
            raw_value=raw_value,
            reason="فرمت تاریخ باید YYYY-MM-DD باشد.",
        ) from None

    setattr(criminal, field_name, parsed)


def _apply_gender_field(
    criminal: R4JCriminal,
    field_name: str,
    raw_value: str,
) -> None:
    """
    اعمال مقدار جنسیت — باید از Gender choices معتبر باشد.

    Args:
        criminal: instance مجرم.
        field_name: نام فیلد (gender).
        raw_value: مقدار رشته‌ای (مثل "male", "female", "unknown").

    Raises:
        FieldApplicationError: اگر مقدار از choices مجاز نباشد.
    """
    stripped = raw_value.strip().lower()
    valid_values = {choice[0] for choice in Gender.choices}

    if stripped not in valid_values:
        raise FieldApplicationError(
            field_name=field_name,
            raw_value=raw_value,
            reason=(
                f"مقدار جنسیت نامعتبر است. "
                f"مقادیر مجاز: {', '.join(sorted(valid_values))}"
            ),
        )

    setattr(criminal, field_name, stripped)


def _apply_national_code_field(
    criminal: R4JCriminal,
    field_name: str,
    raw_value: str,
) -> None:
    """
    اعمال کد ملی با validation فرمت.

    کد ملی باید دقیقاً ۱۰ رقم باشد یا خالی (برای مجرمین غیرایرانی).

    Args:
        criminal: instance مجرم.
        field_name: نام فیلد (national_code).
        raw_value: رشته کد ملی.

    Raises:
        FieldApplicationError: اگر فرمت نامعتبر باشد.
    """
    stripped = raw_value.strip()

    if not stripped:
        setattr(criminal, field_name, None)
        return

    if not stripped.isdigit() or len(stripped) != 10:
        raise FieldApplicationError(
            field_name=field_name,
            raw_value=raw_value,
            reason="کد ملی باید دقیقاً ۱۰ رقم عددی باشد.",
        )

    setattr(criminal, field_name, stripped)


# ============================================================
# Applicator registry
# ============================================================

#: نگاشت field_name به applicator function مخصوص آن فیلد.
#:
#: هر فیلد reportable باید اینجا ثبت شود.
#: اگر field_name در این map نباشد، _apply_text_field به‌عنوان
#: default fallback استفاده می‌شود.
_FIELD_APPLICATORS: Final[dict[str, ApplicatorFn]] = {
    "first_name": _apply_text_field,
    "last_name": _apply_text_field,
    "national_code": _apply_national_code_field,
    "birth_date": _apply_date_field,
    "gender": _apply_gender_field,
    "country": _apply_text_field,
    "province": _apply_text_field,
    "city": _apply_text_field,
    "description": _apply_text_field,
    "crimes_summary": _apply_text_field,
    "other_info": _apply_text_field,
}


# ============================================================
# Public API
# ============================================================


def apply_field_to_criminal(
    *,
    criminal: R4JCriminal,
    field_name: str,
    raw_value: str,
) -> None:
    """
    اعمال type-safe یک مقدار پیشنهادی روی فیلد criminal.

    این تابع applicator مناسب را از registry پیدا کرده و اجرا می‌کند.
    اگر field_name در registry نباشد، به _apply_text_field fallback می‌کند.

    Args:
        criminal: instance مجرم که باید به‌روز شود.
        field_name: نام فیلد مقصد.
        raw_value: مقدار خام string از گزارش کاربر.

    Raises:
        FieldApplicationError: اگر مقدار قابل تبدیل به نوع مقصد نباشد.

    Example:
        >>> apply_field_to_criminal(
        ...     criminal=some_criminal,
        ...     field_name="birth_date",
        ...     raw_value="1990-05-15",
        ... )
    """
    applicator = _FIELD_APPLICATORS.get(field_name, _apply_text_field)

    logger.debug(
        "R4J applying field field=%s applicator=%s criminal=%s",
        field_name,
        applicator.__name__,
        criminal.pk,
    )

    applicator(criminal, field_name, raw_value)

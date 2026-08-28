"""Reusable list/pagination plumbing for service-backed API views.

چرا این ماژول وجود دارد:
    در سراسر پروژه ۵۹ بار دقیقاً همین بلوک تکرار شده بود::

        queryset = selectors.get_...()
        filterset = XFilter(request.query_params, queryset=queryset)
        if filterset.is_valid():
            queryset = filterset.qs
        paginator = StandardPagination()
        page = paginator.paginate_queryset(queryset, request, view=self)
        serializer = XSerializer(page, many=True, context={"request": request})
        return paginator.get_paginated_response(serializer.data, message="...")

    ریشهٔ این تکرار یک قانون معماری بود که `serializer.save()` را در
    `views.py` ممنوع می‌کرد و عملاً استفاده از `generics.*` و `ModelViewSet`
    را غیرممکن کرده بود. آن قانون اصلاح شد (به «ویو نباید مستقیماً روی
    manager مدل بنویسد» تغییر کرد) و این ماژول نیمهٔ دوم راه‌حل است:
    الگوی بالا یک‌بار اینجا پیاده می‌شود.

    نکتهٔ مهم دربارهٔ سبک مهاجرت: عمداً دو مسیر ارائه شده است.

    ``paginated_list_response`` یک تابع ساده است و می‌تواند داخل همان
    ویوهای موجود صدا زده شود، بدون تغییر سلسله‌مراتب کلاس‌ها. برای
    مهاجرت تدریجی و کم‌ریسک ۵۹ نقطه، این مسیر مناسب‌تر است.

    ``ServiceBackedListAPIView`` برای ویوهای جدید است که فقط یک لیست
    برمی‌گردانند و کل بدنهٔ ``get`` را حذف می‌کند.

    هیچ‌کدام رفتار قابل مشاهدهٔ API را تغییر نمی‌دهند: همان paginator،
    همان قرارداد پاسخ و همان رفتار فیلترِ نامعتبر (بازگشت به queryset پایه).
"""

from __future__ import annotations

from typing import Any

from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.core.pagination import StandardPagination


def apply_filterset(
    *,
    filterset_class: Any,
    request: Request,
    queryset: Any,
) -> Any:
    """Apply a django-filter FilterSet, falling back to the base queryset.

    رفتار عمداً با کد قبلی یکسان است: اگر پارامترهای فیلتر نامعتبر باشند،
    queryset پایه برگردانده می‌شود و درخواست ۴۰۰ نمی‌گیرد.
    """
    if filterset_class is None:
        return queryset
    filterset = filterset_class(request.query_params, queryset=queryset)
    if filterset.is_valid():
        return filterset.qs
    return queryset


def paginated_list_response(
    *,
    request: Request,
    view: APIView,
    queryset: Any,
    serializer_class: Any,
    pagination_class: Any = StandardPagination,
    filterset_class: Any = None,
    serializer_context: dict[str, Any] | None = None,
    message: str | None = None,
) -> Response:
    """Filter, paginate and serialize a queryset in one call.

    این تابع همان نه خطی است که ۵۹ بار کپی شده بود.

    Args:
        request: درخواست جاری DRF.
        view: نمونهٔ ویو (paginator برای ساخت لینک‌ها به آن نیاز دارد).
        queryset: queryset پایه، معمولاً از لایهٔ selectors.
        serializer_class: سریالایزر آیتم‌های لیست.
        pagination_class: کلاس صفحه‌بندی؛ پیش‌فرض ``StandardPagination``.
        filterset_class: FilterSet اختیاری.
        serializer_context: کانتکست اضافی؛ ``request`` همیشه اضافه می‌شود.
        message: پیام اختیاری پاسخ، اگر paginator پشتیبانی کند.

    Returns:
        پاسخ صفحه‌بندی‌شدهٔ استاندارد پروژه.
    """
    queryset = apply_filterset(
        filterset_class=filterset_class,
        request=request,
        queryset=queryset,
    )

    paginator = pagination_class()
    page = paginator.paginate_queryset(queryset, request, view=view)

    context: dict[str, Any] = {"request": request}
    if serializer_context:
        context.update(serializer_context)

    data = serializer_class(page, many=True, context=context).data

    if message is None:
        return paginator.get_paginated_response(data)
    return paginator.get_paginated_response(data, message=message)


class ServiceBackedListAPIView(APIView):
    """Base view for read-only list endpoints backed by the selectors layer.

    زیرکلاس فقط ``get_list_queryset`` و ``list_serializer_class`` را تعریف
    می‌کند؛ فیلتر، صفحه‌بندی و سریالایز کردن اینجا انجام می‌شود.

    این کلاس عمداً از ``generics.ListAPIView`` ارث نمی‌برد. آن کلاس مفهوم
    ``get_queryset`` را با فرض دسترسی مستقیم به مدل می‌آورد، در حالی که
    قرارداد این پروژه این است که ویو داده را از لایهٔ selectors بگیرد.
    """

    list_serializer_class: Any = None
    list_pagination_class: Any = StandardPagination
    list_filterset_class: Any = None
    list_response_message: str | None = None

    def get_list_queryset(self, request: Request, *args: Any, **kwargs: Any) -> Any:
        """Return the base queryset for this endpoint (usually from selectors)."""
        raise NotImplementedError("زیرکلاس باید get_list_queryset را پیاده‌سازی کند.")

    def get_list_serializer_context(self, request: Request) -> dict[str, Any]:
        """Extra serializer context; ``request`` is always included."""
        return {}

    def get(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        """Return the filtered, paginated and serialized list."""
        if self.list_serializer_class is None:
            raise NotImplementedError("زیرکلاس باید list_serializer_class را تعریف کند.")
        return paginated_list_response(
            request=request,
            view=self,
            queryset=self.get_list_queryset(request, *args, **kwargs),
            serializer_class=self.list_serializer_class,
            pagination_class=self.list_pagination_class,
            filterset_class=self.list_filterset_class,
            serializer_context=self.get_list_serializer_context(request),
            message=self.list_response_message,
        )

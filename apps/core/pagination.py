"""
Pagination classes that preserve the project response envelope.
"""

from __future__ import annotations

from typing import Any

from rest_framework.pagination import PageNumberPagination
from rest_framework.response import Response

from apps.core.responses import SuccessResponse

DEFAULT_PAGINATED_MESSAGE = "لیست با موفقیت دریافت شد."


class BaseWrappedPagination(PageNumberPagination):
    """
    Base pagination class that returns paginated responses
    using the project's standard response envelope.
    """

    page_size_query_param = "page_size"
    max_page_size = 100

    def get_paginated_data(self, data: list[Any]) -> dict[str, Any]:
        return {
            "count": self.page.paginator.count,
            "next": self.get_next_link(),
            "previous": self.get_previous_link(),
            "results": data,
        }

    def get_paginated_response(
        self,
        data: list[Any],
        *,
        message: str = DEFAULT_PAGINATED_MESSAGE,
    ) -> Response:
        return SuccessResponse(
            data=self.get_paginated_data(data),
            message=message,
        )


class StandardPagination(BaseWrappedPagination):
    """StandardPagination implementation for the core application."""

    page_size = 20
    max_page_size = 100


# نکته: پیش‌تر دو کلاس `SmallPagination` و `LargePagination` هم اینجا تعریف
# شده بودند و هیچ‌جای پروژه استفاده نمی‌شدند. کلاس صفحه‌بندی بلااستفاده صرفاً
# کد مرده نیست؛ گمراه‌کننده هم هست، چون خواننده فرض می‌کند بخشی از API از آن
# استفاده می‌کند و باید هنگام تغییر رفتار صفحه‌بندی در نظرش بگیرد. اگر بعداً
# واقعاً لازم شدند، افزودنشان دو خط کار است.

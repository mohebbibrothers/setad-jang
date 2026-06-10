"""
Provider Pattern — اینترفیس پایه برای منابع داده تبیین.

اگر روزی منبع داده عوض شود (مثلاً از محتوانگار به سیستم دیگری)،
فقط یک Provider جدید می‌نویسیم بدون تغییر در sync engine.
"""

from abc import ABC, abstractmethod
from typing import Any


class BaseTabyinProvider(ABC):
    """اینترفیس انتزاعی برای provider منبع داده."""

    @abstractmethod
    def fetch_page(self, page: int, page_size: int = 30) -> dict[str, Any] | None:
        """دریافت یک صفحه از لیست محتواها."""
        ...

    @abstractmethod
    def fetch_detail(self, content_id: str) -> dict[str, Any] | None:
        """دریافت جزئیات یک محتوا."""
        ...

    @abstractmethod
    def get_total_pages(self, page_size: int = 30) -> int:
        """تعداد کل صفحات."""
        ...

    @abstractmethod
    def close(self) -> None:
        """آزادسازی منابع."""
        ...

    def __enter__(self) -> BaseTabyinProvider:
        return self

    def __exit__(self, *args: object) -> None:
        self.close()

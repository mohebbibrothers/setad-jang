"""
Package initialization برای config پروژه.

با import شدن celery_app در اینجا، اطمینان حاصل می‌شود
که هنگام bootstrap شدن Django، اپلیکیشن Celery نیز
به‌درستی load شود.
"""

from .celery import app as celery_app

__all__ = ("celery_app",)

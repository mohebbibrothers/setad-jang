"""
Celery application bootstrap برای پروژه ستاد جنگ.

این فایل نقطه ورود Celery در سطح پروژه است.

وظایف:
- ساخت Celery app instance
- بارگذاری تنظیمات از Django settings (با namespace CELERY)
- auto-discover کردن taskها از تمام appهای نصب‌شده
- ثبت signal handlers برای monitoring و logging

اصول طراحی:
- این فایل intentionally سبک نگه داشته می‌شود.
- business logic نباید وارد این فایل شود.
- منطق اصلی taskها داخل apps/<app>/tasks.py قرار می‌گیرد.
- تنظیمات Celery (broker, backend, beat, routing, limits) در
  config/settings/base.py تعریف شده‌اند.

Docker compatibility:
- docker-compose service `worker` و `madadkar-worker` و `beat` هر دو از این
  فایل به‌عنوان entrypoint استفاده می‌کنند (تفکیک صف‌ها — یافتهٔ ممیزی ۵.۲):
    worker:          celery -A config worker -l info -Q default,tabyin_sync
    madadkar-worker: celery -A config worker -l info -Q madadkar
    beat:            celery -A config beat -l info
"""

from __future__ import annotations

import logging
import os
import time

from celery import Celery
from celery.signals import (
    task_failure,
    task_postrun,
    task_prerun,
    worker_ready,
    worker_shutting_down,
)

# ============================================================
# Django settings module
# ============================================================

os.environ.setdefault(
    "DJANGO_SETTINGS_MODULE",
    "config.settings.development",
)

# ============================================================
# Celery app instance
# ============================================================

app = Celery("setad_jang")

#: بارگذاری تنظیمات از Django settings.
#: تمام keyهای با پیشوند CELERY_ در settings به‌صورت خودکار خوانده می‌شوند.
app.config_from_object(
    "django.conf:settings",
    namespace="CELERY",
)

#: کشف خودکار taskها از تمام INSTALLED_APPS.
#: هر app که فایل tasks.py داشته باشد، taskهایش شناسایی می‌شوند.
app.autodiscover_tasks()

# ============================================================
# Logger
# ============================================================

logger = logging.getLogger("celery")
_TASK_START_TIMES: dict[str, float] = {}

# ============================================================
# Signal handlers — Lifecycle monitoring
# ============================================================


@worker_ready.connect
def on_worker_ready(sender, **kwargs):
    """لاگ هنگام آماده شدن worker — مفید برای monitoring و health check."""
    logger.info(
        "Celery worker ready hostname=%s",
        getattr(sender, "hostname", "unknown"),
    )


@worker_shutting_down.connect
def on_worker_shutting_down(sender, sig, how, exitcode, **kwargs):
    """لاگ هنگام shutdown شدن worker — برای graceful shutdown tracking."""
    logger.info(
        "Celery worker shutting down hostname=%s signal=%s how=%s exitcode=%s",
        getattr(sender, "hostname", "unknown"),
        sig,
        how,
        exitcode,
    )


@task_prerun.connect
def on_task_prerun(sender, task_id, task, args, kwargs, **kw):
    """لاگ قبل از اجرای هر task — برای trace و debug."""
    _TASK_START_TIMES[task_id] = time.monotonic()
    logger.info(
        "Task starting task=%s id=%s",
        task.name,
        task_id,
    )


@task_postrun.connect
def on_task_postrun(sender, task_id, task, args, kwargs, retval, state, **kw):
    """لاگ بعد از اتمام هر task — شامل state نهایی و metrics."""
    from apps.core.metrics import CELERY_TASK_DURATION_SECONDS, CELERY_TASKS_TOTAL

    task_name = task.name
    CELERY_TASKS_TOTAL.labels(task=task_name, state=state).inc()
    started_at = _TASK_START_TIMES.pop(task_id, None)
    if started_at is not None:
        CELERY_TASK_DURATION_SECONDS.labels(task=task_name).observe(time.monotonic() - started_at)
    logger.info(
        "Task completed task=%s id=%s state=%s",
        task.name,
        task_id,
        state,
    )


@task_failure.connect
def on_task_failure(sender, task_id, exception, args, kwargs, traceback, einfo, **kw):
    """لاگ هنگام failure یک task — برای alerting و debugging."""
    logger.error(
        "Task failed task=%s id=%s exception=%s",
        sender.name,
        task_id,
        exception,
        exc_info=True,
    )


# ============================================================
# Debug task
# ============================================================


@app.task(bind=True, ignore_result=True)
def debug_task(self) -> None:
    """
    تسک دیباگ برای بررسی صحت اتصال Celery.

    این تسک صرفاً برای تست bootstrap شدن Celery مفید است و
    در production usage نقشی در business flow ندارد.

    Usage:
        # از Django shell:
        from config.celery import debug_task
        debug_task.delay()

        # یا از command line:
        celery -A config call config.celery.debug_task
    """
    logger.info("Debug task executed request=%r", self.request)

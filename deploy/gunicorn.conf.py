"""Gunicorn configuration for Setad Jang.

تنها مسئولیت این فایل: hygiene عمرِ متریک‌ها در حالت prometheus multiprocess
(یافتهٔ P1 فاز ۷). gunicorn با `--max-requests` workerها را می‌چرخاند؛ هر
workerِ مرده فایل mmap خودش را در `PROMETHEUS_MULTIPROC_DIR` جا می‌گذارد و
اگر پاک نشود، آن شمارش‌های «زامبی» تا ابد در aggregate اسکرپ‌ها باقی
می‌مانند و متریک را به‌آرامی نادرست می‌کنند. هوک `child_exit` دقیقاً همین‌جا
تمیزکاری می‌کند.

چرا هوک عمداً «بلعندهٔ خطا» است:
    این یک hook ناظر-محور است؛ شکستِ آن نباید master گانیکورن را هنگام
    خروجِ worker بکشد — یک warning در لاگ کافی است.
"""

from __future__ import annotations

import os


def child_exit(server, worker) -> None:
    """Mark a recycled/dead worker's prometheus mmap files as dead."""
    if not os.environ.get("PROMETHEUS_MULTIPROC_DIR"):
        return
    try:
        from prometheus_client.multiprocess import mark_process_dead

        mark_process_dead(worker.pid)
    except Exception:  # observability hook must never crash the master
        server.log.warning("failed to mark prometheus multiproc files dead for pid=%s", worker.pid)

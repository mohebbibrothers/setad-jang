"""Structured logging helpers for production observability."""

from __future__ import annotations

import json
import logging
import traceback
from datetime import UTC, datetime
from typing import Any

from apps.core.middleware import get_current_request_id


class JSONLogFormatter(logging.Formatter):
    """JSON log formatter with request correlation and safe exception fields."""

    def format(self, record: logging.LogRecord) -> str:
        """Format a log record as compact JSON."""
        payload: dict[str, Any] = {
            "timestamp": datetime.fromtimestamp(record.created, tz=UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "request_id": getattr(record, "request_id", None) or get_current_request_id(),
            "module": record.module,
            "function": record.funcName,
            "line": record.lineno,
        }
        if record.exc_info:
            exc_type, exc_value, exc_tb = record.exc_info
            payload["exception"] = {
                "type": getattr(exc_type, "__name__", str(exc_type)),
                "message": str(exc_value),
                "stacktrace": "".join(traceback.format_exception(exc_type, exc_value, exc_tb))[-6000:],
            }
        return json.dumps(payload, ensure_ascii=False, separators=(",", ":"))

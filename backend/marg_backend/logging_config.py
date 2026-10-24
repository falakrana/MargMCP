"""Structured, secret-scrubbed operational logging (Phase 9).

* ``install_scrubbing()`` wraps the log-record factory so *every* record in the
  process (ours, uvicorn's, third-party) has secret-looking substrings removed
  from its message and from its formatted traceback before any handler sees it.
* ``JsonFormatter`` emits one JSON object per line with a UTC timestamp, level,
  logger, message and the current request id, for log aggregation.
* Request ids are generated server-side only (a client-supplied id is never
  trusted, which also prevents log injection through that header).
"""
from __future__ import annotations

import contextvars
import json
import logging
import sys
import traceback
from datetime import datetime, timezone
from typing import Optional

from marg_backend.config import Settings
from marg_backend.redact import scrub_text

request_id_var: contextvars.ContextVar[Optional[str]] = contextvars.ContextVar(
    "agentops_request_id", default=None
)

_installed = False


def install_scrubbing() -> None:
    """Idempotently scrub secrets from all log records."""
    global _installed
    if _installed:
        return
    previous = logging.getLogRecordFactory()

    def factory(*args, **kwargs) -> logging.LogRecord:
        record = previous(*args, **kwargs)
        try:
            if record.name == "uvicorn.access" and isinstance(record.args, tuple):
                record.args = tuple(
                    scrub_text(str(a)) if isinstance(a, str) else a for a in record.args
                )
            else:
                record.msg = scrub_text(record.getMessage())
                record.args = None
            if record.exc_info and not record.exc_text and record.exc_info[0] is not None:
                record.exc_text = scrub_text("".join(traceback.format_exception(*record.exc_info)))
        except Exception:  # noqa: BLE001 - logging must never raise
            pass
        return record

    logging.setLogRecordFactory(factory)
    _installed = True


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "ts": datetime.fromtimestamp(record.created, tz=timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": scrub_text(record.getMessage()),
        }
        request_id = request_id_var.get()
        if request_id:
            payload["request_id"] = request_id
        if record.exc_info and not record.exc_text:
            record.exc_text = scrub_text(self.formatException(record.exc_info))
        if record.exc_text:
            payload["exception"] = record.exc_text
        return json.dumps(payload, ensure_ascii=False)


def resolve_log_format(settings: Settings) -> str:
    fmt = settings.log_format.lower()
    if fmt == "auto":
        return "text" if settings.env == "development" else "json"
    return fmt if fmt in {"text", "json"} else "text"


def configure_logging(settings: Settings) -> None:
    install_scrubbing()
    root = logging.getLogger()
    root.setLevel(settings.log_level.upper())
    if root.handlers:
        return  # the host (uvicorn, pytest, ...) already configured handlers
    handler = logging.StreamHandler(sys.stderr)
    if resolve_log_format(settings) == "json":
        handler.setFormatter(JsonFormatter())
    else:
        handler.setFormatter(logging.Formatter("%(levelname)s:%(name)s:%(message)s"))
    root.addHandler(handler)

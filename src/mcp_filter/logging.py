"""Logging helpers for the MCP tool filter."""

from __future__ import annotations

import logging
from contextvars import ContextVar
from typing import Any, Dict

from rich.logging import RichHandler

LOG_CONTEXT: ContextVar[Dict[str, Any]] = ContextVar("log_context", default={})


class _ContextFilter(logging.Filter):
    """Inject contextual fields into every log record."""

    def filter(self, record: logging.LogRecord) -> bool:
        context = LOG_CONTEXT.get()
        for key, value in context.items():
            setattr(record, key, value)
        return True


class _StructuredFormatter(logging.Formatter):
    """Render structured fields after the log message."""

    STRUCTURED_KEYS = ("server_name", "upstream_transport", "allowed_tools")

    def format(self, record: logging.LogRecord) -> str:
        message = super().format(record)
        extras = {
            key: getattr(record, key)
            for key in self.STRUCTURED_KEYS
            if hasattr(record, key)
        }
        if not extras:
            return message
        structured = " ".join(f"{key}={value}" for key, value in extras.items())
        return f"{message} | {structured}"


def setup_logging(
    level: str,
    *,
    show_time: bool = True,
    show_path: bool = False,
    rich_tracebacks: bool = True,
) -> None:
    """Configure global logging using Rich."""

    handler = RichHandler(
        show_time=show_time,
        show_path=show_path,
        markup=False,
        rich_tracebacks=rich_tracebacks,
    )
    formatter = _StructuredFormatter("%(message)s")
    handler.setFormatter(formatter)
    handler.addFilter(_ContextFilter())

    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(getattr(logging, level.upper(), logging.INFO))


def set_log_context(**kwargs: Any) -> None:
    """Update the contextual fields for subsequent log records."""

    context = dict(LOG_CONTEXT.get())
    context.update(kwargs)
    LOG_CONTEXT.set(context)

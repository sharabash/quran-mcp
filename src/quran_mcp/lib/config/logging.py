from __future__ import annotations

import logging
import os
import threading
from typing import Mapping

from fastmcp.utilities.logging import configure_logging

_STATIC_PREFIXES = (
    "/screenshots/",
    "/icons/",
    "/icon.",
    "/og-image.",
    "/shared-theme.",
    "/documentation/assets/",
    "/documentation/data.json",
    "/sitemap.xml",
    "/favicon",
)


class _StaticAssetFilter(logging.Filter):
    """Drop uvicorn access log entries for static asset requests."""

    def filter(self, record: logging.LogRecord) -> bool:
        msg = record.getMessage()
        return not any(prefix in msg for prefix in _STATIC_PREFIXES)


class _ExtraAwareFormatter(logging.Formatter):
    """Append LogRecord extras (from logger.debug(..., extra={...})) to the rendered message."""

    _RESERVED_KEYS = {
        "name",
        "msg",
        "args",
        "levelname",
        "levelno",
        "pathname",
        "filename",
        "module",
        "exc_info",
        "exc_text",
        "stack_info",
        "lineno",
        "funcName",
        "created",
        "msecs",
        "relativeCreated",
        "thread",
        "threadName",
        "processName",
        "process",
        "message",
        "asctime",
        "color_message",  # injected by RichHandler
    }

    def format(self, record: logging.LogRecord) -> str:
        rendered = super().format(record)
        extras = {
            key: value
            for key, value in record.__dict__.items()
            if key not in self._RESERVED_KEYS
        }
        if not extras:
            return rendered
        serialized = " ".join(f"{key}={value!r}" for key, value in sorted(extras.items()))
        return f"{rendered} | {serialized}"


def setup_logging(overrides: Mapping[str, str] | None = None) -> None:
    """
    Configure project logging using FastMCP defaults + extra field rendering.

    Args:
        overrides: optional mapping of env var names to values (handy for tests).
    """

    def _getenv(name: str) -> str | None:
        if overrides and name in overrides:
            return overrides[name]
        return os.getenv(name)

    level_names = logging.getLevelNamesMapping()
    level = next(
        (
            level_value
            for env_var in ("FASTMCP_LOG_LEVEL", "LOG_LEVEL")
            if (raw := _getenv(env_var))
            and isinstance(level_value := level_names.get(raw.strip().upper()), int)
        ),
        logging.INFO,  # Keep INFO default so middleware/tool logs are visible by default
    )

    # HTTP debug middleware is independent from global log level
    # It only controls HttpDebugMiddleware, not the entire logging system
    # If you want DEBUG level globally, set LOG_LEVEL=DEBUG explicitly

    level_name = next((name for name, value in level_names.items() if value == level), level)

    root_logger = logging.getLogger()
    configure_logging(
        level=level_name,
        logger=root_logger,
        enable_rich_tracebacks=True,
    )
    root_logger.setLevel(level)

    formatter = _ExtraAwareFormatter("%(message)s")
    for handler in root_logger.handlers:
        handler.setFormatter(formatter)

    # Suppress uvicorn access logs for static assets (images, CSS, JS, etc.)
    # to reduce noise from browser requests loading the landing page.
    uvicorn_access = logging.getLogger("uvicorn.access")
    uvicorn_access.addFilter(_StaticAssetFilter())


_request_counter = 0
_request_lock = threading.Lock()


def get_request_id() -> str:
    """Generate unique request ID for correlation.

    Returns:
        Sequential request ID (e.g., "req_1", "req_2").
    """
    global _request_counter
    with _request_lock:
        _request_counter += 1
        return f"req_{_request_counter}"

"""Sentry SDK initialization and event filtering."""

from __future__ import annotations

import logging
from importlib.metadata import version as _metadata_version
from typing import Any

_logger = logging.getLogger(__name__)

# Keys to redact from Sentry event payloads (case-insensitive comparison).
_SENSITIVE_KEYS = frozenset({
    "authorization",
    "api_key",
    "api-key",
    "apikey",
    "dsn",
    "password",
    "secret",
    "token",
    "cookie",
})


def _is_sensitive(key: str) -> bool:
    """Check if a header/key name looks sensitive."""
    return key.lower() in _SENSITIVE_KEYS


def _scrub_dict(d: dict[str, Any]) -> dict[str, Any]:
    """Redact values for keys that look sensitive."""
    return {
        k: "[Filtered]" if _is_sensitive(k) else v
        for k, v in d.items()
    }


def before_send(event: dict[str, Any], hint: dict[str, Any]) -> dict[str, Any] | None:
    """Scrub sensitive data from Sentry events before transmission."""
    request = event.get("request")
    if request:
        if "headers" in request and isinstance(request["headers"], dict):
            request["headers"] = _scrub_dict(request["headers"])
        if "data" in request and isinstance(request["data"], dict):
            request["data"] = _scrub_dict(request["data"])
    return event


def init_sentry(settings: Any) -> None:
    """Initialize Sentry SDK if DSN is configured and enabled.

    Args:
        settings: A SentrySettings instance with dsn, enabled,
                  traces_sample_rate, environment, release, send_default_pii.
    """
    dsn = settings.dsn.get_secret_value()
    if not dsn or not settings.enabled:
        _logger.debug("Sentry disabled (dsn=%s, enabled=%s)", bool(dsn), settings.enabled)
        return

    try:
        import sentry_sdk

        sentry_sdk.init(
            dsn=dsn,
            traces_sample_rate=settings.traces_sample_rate,
            environment=settings.environment,
            release=settings.release or _get_release(),
            send_default_pii=settings.send_default_pii,
            before_send=before_send,
        )
        _logger.info(
            "Sentry initialized (environment=%s, traces_sample_rate=%.1f%%)",
            settings.environment,
            settings.traces_sample_rate * 100,
        )
    except Exception:
        _logger.warning("Failed to initialize Sentry", exc_info=True)


def _get_release() -> str:
    """Derive a release string from the package version."""
    try:
        return f"quran-mcp@{_metadata_version('quran-mcp')}"
    except Exception:
        return "quran-mcp@unknown"

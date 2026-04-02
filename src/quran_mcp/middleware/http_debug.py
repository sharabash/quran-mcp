"""HTTP debug middleware for inbound MCP requests."""

from __future__ import annotations

import json
import logging
from typing import Any

from fastmcp.server.dependencies import get_http_request
from fastmcp.server.middleware import Middleware, MiddlewareContext
from fastmcp.server.middleware.middleware import CallNext

from quran_mcp.lib.config.settings import get_settings

logger = logging.getLogger(__name__)


def _is_http_debug_enabled() -> bool:
    """Check if HTTP debug logging is enabled via centralized Settings."""
    return get_settings().logging.debug


def _sanitize_header_value(key: str, value: str) -> str:
    """Sanitize sensitive header values to show only first 4 and last 4 characters."""
    sensitive_keys = {
        "authorization",
        "x-auth-token",
        "x-api-key",
        "cookie",
        "set-cookie",
    }

    if key.lower() in sensitive_keys and len(value) > 8:
        return f"{value[:4]}...{value[-4:]}"
    return value


def _format_headers(headers: dict[str, str]) -> dict[str, str]:
    """Format headers with sensitive values sanitized."""
    return {key: _sanitize_header_value(key, value) for key, value in headers.items()}


class HttpDebugMiddleware(Middleware):
    """Log inbound MCP-over-HTTP request and response metadata when enabled."""

    async def on_message(
        self,
        context: MiddlewareContext,
        call_next: CallNext,
    ) -> Any:
        """Log HTTP request details before processing and response after."""
        if not _is_http_debug_enabled():
            return await call_next(context)

        http_request = None
        try:
            http_request = get_http_request()
        except (RuntimeError, LookupError):
            logger.debug("HTTP request not available in current context", exc_info=True)

        if http_request:
            sanitized_headers = _format_headers(dict(http_request.headers))
            logger.info(
                "🔵 MCP Client → Server | %s %s",
                http_request.method,
                http_request.url.path,
                extra={
                    "http_method": http_request.method,
                    "http_url": str(http_request.url),
                    "http_headers": sanitized_headers,
                    "client_ip": http_request.client.host if http_request.client else None,
                    "mcp_method": context.method,
                    "mcp_type": context.type,
                },
            )
        else:
            logger.info(
                "🔵 MCP Message | %s",
                context.method,
                extra={
                    "mcp_method": context.method,
                    "mcp_source": context.source,
                    "mcp_type": context.type,
                },
            )

        try:
            result = await call_next(context)
        except Exception as exc:
            logger.error(
                "🔴 MCP Request Error | %s: %s",
                type(exc).__name__,
                exc,
                extra={
                    "mcp_method": context.method,
                    "error_type": type(exc).__name__,
                    "error_message": str(exc),
                },
                exc_info=True,
            )
            raise

        result_info: dict[str, Any] = {
            "mcp_method": context.method,
            "status": "success",
        }
        try:
            result_json = json.dumps(result, default=str)
            if len(result_json) <= 500:
                result_info["response_preview"] = result_json
            else:
                result_info["response_size"] = len(result_json)
                result_info["response_preview"] = result_json[:500] + "..."
        except (TypeError, ValueError):
            result_info["response_type"] = type(result).__name__

        logger.info("🟢 Server → MCP Client | Response", extra=result_info)
        return result

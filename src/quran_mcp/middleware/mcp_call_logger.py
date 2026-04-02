"""Unified MCP call logger middleware.

Replaces StructuredLoggingMiddleware, TimingMiddleware, McpRichMetadataMiddleware,
and Rich decorators with a single clear line per MCP call.

Supports two output formats:
- "pretty": Human-friendly colored output (default, for dev terminals)
- "json": Structured JSON per call (for CI/production log aggregation)

Verbosity levels (from settings.logging.log_level):
- minimal: Errors only (omit request args from minimal error logs)
- normal: Single summary line per call
- verbose: Summary + 256-char response preview
- debug: Summary + preview + request_id + client_ip
"""

from __future__ import annotations

import asyncio
import json
import logging
import sys
import time
from typing import Any

from fastmcp.server.middleware import Middleware, MiddlewareContext
from fastmcp.server.middleware.middleware import CallNext

from quran_mcp.lib.config.logging import get_request_id
from quran_mcp.lib.context.request import get_http_headers, resolve_client_identity
from quran_mcp.lib.presentation.client_hint import detect_client_hint

logger = logging.getLogger("quran_mcp.mcp_calls")

# Cap serialization to avoid O(n) overhead on large payloads (e.g., mushaf pages)
_MAX_SERIALIZE_BYTES = 65536


def _safe_serialize(obj: Any) -> tuple[str, int | None]:
    """Serialize an object to JSON string, capped at _MAX_SERIALIZE_BYTES.

    Returns:
        Tuple of (serialized_string, approximate_size_bytes).
        Size is None if serialization fails.
    """
    try:
        raw = json.dumps(obj, default=str)
        if len(raw) <= _MAX_SERIALIZE_BYTES:
            return raw, len(raw)
        return raw[:_MAX_SERIALIZE_BYTES], None  # Truncated — exact size unknown
    except (TypeError, ValueError, OverflowError):
        return "", None


def _format_size(size_bytes: int | None) -> str:
    """Format byte size as human-readable string."""
    if size_bytes is None:
        return ">64KB"
    if size_bytes < 1024:
        return f"{size_bytes}B"
    return f"{size_bytes / 1024:.1f}KB"


def _truncate_args(args: dict[str, Any] | None, max_per_param: int = 80) -> str:
    """Format arguments as a compact string with per-param truncation.

    Args:
        args: Tool/prompt arguments dict, or None.
        max_per_param: Max characters per parameter value.

    Returns:
        Formatted string like: ayahs="2:255", editions=["quran-uthmani"]
    """
    if not args:
        return ""
    parts = []
    for key, value in args.items():
        val_str = json.dumps(value, default=str) if not isinstance(value, str) else f'"{value}"'
        if len(val_str) > max_per_param:
            val_str = val_str[: max_per_param - 3] + "..."
        parts.append(f"{key}={val_str}")
    return ", ".join(parts)


def _extract_client_ip(context: MiddlewareContext) -> str | None:
    """Extract client IP from FastMCP context, if available."""
    fmcp_ctx = context.fastmcp_context
    if fmcp_ctx is None:
        return None
    if hasattr(fmcp_ctx, "request_context") and hasattr(fmcp_ctx.request_context, "client"):
        client_tuple = fmcp_ctx.request_context.client
        if client_tuple and len(client_tuple) > 0:
            return client_tuple[0]
    return None


class McpCallLoggerMiddleware(Middleware):
    """Unified middleware for logging all MCP calls.

    Produces one clear line per tool/resource/prompt call with:
    - Component type tag ([TOOL], [RESOURCE], [PROMPT], [META])
    - Name and arguments (truncated)
    - Status (OK/ERROR), response size, duration
    - Optional response preview (verbose+) and request ID (debug)
    """

    def __init__(self, verbosity: str = "normal", fmt: str = "pretty") -> None:
        self._verbosity = verbosity if verbosity in ("minimal", "normal", "verbose", "debug") else "normal"
        self._fmt = fmt if fmt in ("pretty", "json") else "pretty"

    # ------------------------------------------------------------------
    async def _wrap_call(
        self,
        tag: str,
        label: str,
        name: str,
        args: dict[str, Any] | None,
        context: MiddlewareContext,
        call_next: CallNext,
    ) -> Any:
        """Shared try/time/serialize/log pattern for tool, resource, and prompt hooks."""
        start = time.monotonic()
        try:
            result = await call_next(context)
            duration_ms = (time.monotonic() - start) * 1000
            if self._verbosity != "minimal":
                loop = asyncio.get_running_loop()
                serialized, size_bytes = await loop.run_in_executor(None, _safe_serialize, result)
                self._log_call(tag, label, name, args, "ok", size_bytes, duration_ms, context, serialized)
            return result
        except Exception as exc:
            duration_ms = (time.monotonic() - start) * 1000
            self._log_error(tag, label, name, args, exc, duration_ms, context)
            raise

    async def on_call_tool(self, context: MiddlewareContext, call_next: CallNext) -> Any:
        name = getattr(context.message, "name", "<unknown>")
        args = getattr(context.message, "arguments", None) or {}
        return await self._wrap_call("TOOL", "tool", name, args, context, call_next)

    async def on_read_resource(self, context: MiddlewareContext, call_next: CallNext) -> Any:
        uri = str(getattr(context.message, "uri", "<unknown>"))
        return await self._wrap_call("RESOURCE", "resource", uri, None, context, call_next)

    async def on_get_prompt(self, context: MiddlewareContext, call_next: CallNext) -> Any:
        name = getattr(context.message, "name", "<unknown>")
        args = getattr(context.message, "arguments", None) or {}
        return await self._wrap_call("PROMPT", "prompt", name, args, context, call_next)

    # ------------------------------------------------------------------
    # Metadata discovery (list calls)
    # ------------------------------------------------------------------
    async def on_list_tools(self, context: MiddlewareContext, call_next: CallNext) -> Any:
        return await self._log_list("tools/list", "tools", context, call_next)

    async def on_list_resources(self, context: MiddlewareContext, call_next: CallNext) -> Any:
        return await self._log_list("resources/list", "resources", context, call_next)

    async def on_list_prompts(self, context: MiddlewareContext, call_next: CallNext) -> Any:
        return await self._log_list("prompts/list", "prompts", context, call_next)

    async def on_list_resource_templates(self, context: MiddlewareContext, call_next: CallNext) -> Any:
        return await self._log_list("resources/templates/list", "resource_templates", context, call_next)

    async def _log_list(
        self,
        method: str,
        label: str,
        context: MiddlewareContext,
        call_next: CallNext,
    ) -> Any:
        """Shared logic for metadata discovery hooks."""
        if self._verbosity == "minimal":
            return await call_next(context)

        start = time.monotonic()
        try:
            result = await call_next(context)
        except Exception as exc:
            duration_ms = (time.monotonic() - start) * 1000
            self._log_error("META", "meta", method, None, exc, duration_ms, context)
            raise
        duration_ms = (time.monotonic() - start) * 1000
        count = len(result) if isinstance(result, (list, tuple)) else 0

        if self._fmt == "json":
            record = {
                "type": "meta",
                "method": method,
                "count": count,
                "duration_ms": round(duration_ms),
            }
            print(json.dumps(record), file=sys.stderr)
        else:
            line = f"[META]     {method} → {count} {label} ({duration_ms:.0f}ms)"
            logger.info(line)

        return result

    # ------------------------------------------------------------------
    # Client identification
    # ------------------------------------------------------------------
    def _build_client_dict(self, context: MiddlewareContext) -> dict[str, str | None]:
        """Build client identification dict from request context."""
        fastmcp_ctx = context.fastmcp_context
        hint = detect_client_hint(fastmcp_ctx)
        headers = get_http_headers()
        client_id = resolve_client_identity(headers=headers)
        ip = headers.get("cf-connecting-ip") if headers else None
        return {
            "host": hint.get("host", "unknown"),
            "platform": hint.get("platform", "unknown"),
            "ip": ip,
            "id": client_id,
        }

    # ------------------------------------------------------------------
    # Internal formatting
    # ------------------------------------------------------------------
    def _log_call(
        self,
        tag: str,
        type_str: str,
        name: str,
        args: dict[str, Any] | None,
        status: str,
        size_bytes: int | None,
        duration_ms: float,
        context: MiddlewareContext,
        serialized: str = "",
    ) -> None:
        """Log a successful MCP call.

        Note: Callers already gate on verbosity != "minimal" before calling,
        so this method assumes it will not be called at minimal verbosity.
        """
        request_id = get_request_id()
        size_str = _format_size(size_bytes)

        if self._fmt == "json":
            record: dict[str, Any] = {
                "type": type_str,
                "name": name,
                "status": status,
                "size_bytes": size_bytes,
                "duration_ms": round(duration_ms),
                "request_id": request_id,
            }
            if args:
                record["args"] = args
            if self._verbosity in ("verbose", "debug") and serialized:
                record["preview"] = serialized[:256]
            if self._verbosity == "debug":
                client_ip = _extract_client_ip(context)
                if client_ip:
                    record["client_ip"] = client_ip
            if tag == "TOOL":
                record["client"] = self._build_client_dict(context)
            print(json.dumps(record, default=str), file=sys.stderr)
            return

        # Pretty format
        if tag == "TOOL":
            client_json = json.dumps(self._build_client_dict(context))
            logger.info(f"[TOOL]     client: {client_json}")

        args_str = _truncate_args(args) if args else ""
        call_sig = f"{name}({args_str})" if args_str else name
        line = f"[{tag}]     {call_sig} → OK ({size_str}, {duration_ms:.0f}ms)"

        if self._verbosity == "debug":
            client_ip = _extract_client_ip(context)
            extras = f" [{request_id}]"
            if client_ip:
                extras += f" {client_ip}"
            line += extras

        logger.info(line)

        # Verbose/debug: append 256-char response preview on a second line
        if self._verbosity in ("verbose", "debug") and serialized:
            preview = serialized[:256]
            if len(serialized) > 256:
                preview += "..."
            logger.info(f"           ╰─ {preview}")

    def _log_error(
        self,
        tag: str,
        type_str: str,
        name: str,
        args: dict[str, Any] | None,
        exc: Exception,
        duration_ms: float,
        context: MiddlewareContext,
    ) -> None:
        """Log a failed MCP call. Always shown (even at minimal verbosity)."""
        request_id = get_request_id()
        error_str = f"{type(exc).__name__}: {exc}"

        if self._fmt == "json":
            record: dict[str, Any] = {
                "type": type_str,
                "name": name,
                "status": "error",
                "error": error_str,
                "duration_ms": round(duration_ms),
                "request_id": request_id,
            }
            if args and self._verbosity != "minimal":
                record["args"] = args
            if self._verbosity == "debug":
                client_ip = _extract_client_ip(context)
                if client_ip:
                    record["client_ip"] = client_ip
            if tag == "TOOL":
                record["client"] = self._build_client_dict(context)
            print(json.dumps(record, default=str), file=sys.stderr)
            return

        # Pretty format
        if tag == "TOOL":
            client_json = json.dumps(self._build_client_dict(context))
            logger.error(f"[TOOL]     client: {client_json}")

        args_str = _truncate_args(args) if args and self._verbosity != "minimal" else ""
        call_sig = f"{name}({args_str})" if args_str else name
        line = f"[{tag}]     {call_sig} → ERROR ({duration_ms:.0f}ms) {error_str}"

        if self._verbosity == "debug":
            client_ip = _extract_client_ip(context)
            extras = f" [{request_id}]"
            if client_ip:
                extras += f" {client_ip}"
            line += extras

        logger.error(line)

        # Verbose/debug: include stack trace
        if self._verbosity in ("verbose", "debug"):
            logger.error("           ╰─ Stack trace:", exc_info=exc)

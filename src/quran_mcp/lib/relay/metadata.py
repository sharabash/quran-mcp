"""Result metadata extraction for relay tool-call logging.

Pure function — no middleware, database, or I/O dependency.
"""

from __future__ import annotations

import logging
from typing import Any, TYPE_CHECKING

if TYPE_CHECKING:
    from mcp.types import CallToolResult

logger = logging.getLogger(__name__)


def extract_result_metadata(result: CallToolResult | None) -> dict[str, Any]:
    """Extract lightweight metadata from a tool result.

    Never raises — returns defaults on any error.
    """
    try:
        content = result.content if result else []
        is_error = getattr(result, "isError", False)
        count = len(content) if content else 0

        summary_parts: list[str] = []
        for item in content or []:
            text = getattr(item, "text", None)
            if text:
                summary_parts.append(text[:200])
            if len(summary_parts) >= 3:
                break
        summary = " | ".join(summary_parts)[:500] if summary_parts else None

        structured = getattr(result, "structuredContent", None)
        result_keys = list(structured.keys())[:20] if isinstance(structured, dict) else None

        return {
            "success": not is_error,
            "result_count": count,
            "result_keys": result_keys,
            "result_summary": summary,
        }
    except (TypeError, AttributeError, ValueError) as exc:
        logger.debug("Failed to extract result metadata: %s", exc)
        return {
            "success": None,
            "result_count": None,
            "result_keys": None,
            "result_summary": None,
        }

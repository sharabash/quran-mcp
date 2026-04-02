"""Turn identity diagnostic logging for relay.

Pure function — writes to a JSONL file, no middleware dependency.
"""

from __future__ import annotations

import json as _json
import logging
from typing import Any

logger = logging.getLogger(__name__)

# Headers safe to log — no auth tokens, no PII beyond IP/country
HEADER_ALLOWLIST = frozenset({
    "traceparent",
    "baggage",
    "x-openai-session",
    "user-agent",
    "mcp-session-id",
    "mcp-protocol-version",
    "content-type",
    "cf-connecting-ip",
    "cf-ipcountry",
})


def write_turn_identity_diagnostic_event(
    *,
    diagnostic_payload: dict[str, Any],
) -> None:
    """Write turn correlation diagnostic to .logs/turn_identity_diagnostic.jsonl."""
    try:
        from pathlib import Path

        log_dir = Path(__file__).resolve().parents[3] / ".logs"
        log_dir.mkdir(exist_ok=True)
        log_file = log_dir / "turn_identity_diagnostic.jsonl"
        with open(log_file, "a") as f:
            f.write(_json.dumps(diagnostic_payload, default=str) + "\n")
    except OSError:
        # Intentional: diagnostic logging is best-effort, don't crash the request
        logger.warning("Failed to write turn identity diagnostic", exc_info=True)

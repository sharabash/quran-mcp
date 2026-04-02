"""DB helpers for runtime_config table.

Provides:
- load_runtime_config / save_runtime_config — generic scope/key JSONB store
"""
from __future__ import annotations

import json
import logging
from typing import Any

import asyncpg

logger = logging.getLogger(__name__)


async def load_runtime_config(pool: asyncpg.Pool, scope: str) -> dict[str, Any]:
    """Load all runtime_config entries for a given scope.

    Returns a dict mapping key -> JSON value.
    """
    rows = await pool.fetch(
        "SELECT key, value FROM quran_mcp.runtime_config WHERE scope = $1",
        scope,
    )
    return {row["key"]: row["value"] for row in rows}


async def save_runtime_config(
    pool: asyncpg.Pool,
    scope: str,
    key: str,
    value: Any,
    updated_by: str | None = None,
) -> None:
    """Upsert a runtime_config entry (scope + key unique constraint)."""
    await pool.execute(
        """
        INSERT INTO quran_mcp.runtime_config (scope, key, value, updated_by, updated_at)
        VALUES ($1, $2, $3::jsonb, $4, NOW())
        ON CONFLICT (scope, key) DO UPDATE
        SET value = EXCLUDED.value, updated_by = EXCLUDED.updated_by, updated_at = NOW()
        """,
        scope,
        key,
        json.dumps(value),
        updated_by,
    )

"""Database infrastructure for the relay system.

Provides asyncpg connection pool management, schema migrations,
and retention cleanup. Graceful degradation: everything is optional.
"""

from quran_mcp.lib.db.pool import create_pool, close_pool

__all__ = ["create_pool", "close_pool"]
